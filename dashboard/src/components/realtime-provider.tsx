"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// Mirrors API `SYSTEM_INFO_ONLINE_TIMEOUT_SECONDS` (default 300).
const ONLINE_TIMEOUT_SECONDS = 300;

export type PresenceEntry = {
  device_id: string;
  online: boolean;
  last_seen?: number;
  pc_name?: string | null;
};

export type LiveProcessRow = {
  pid?: number;
  name?: string;
  username?: string | null;
  cpu_percent?: number;
  memory_rss?: number;
  memory_percent?: number;
  connections?: number;
};

export type LiveProcesses = {
  cpu?: LiveProcessRow[];
  ram?: LiveProcessRow[];
  network?: LiveProcessRow[];
};

export type LiveMetricsSample = {
  device_id: string;
  pc_name?: string | null;
  cpu_percent?: number;
  ram_percent?: number;
  ram_used?: number;
  ram_total?: number;
  bytes_sent?: number;
  bytes_recv?: number;
  send_rate_bps?: number;
  recv_rate_bps?: number;
  eth_name?: string | null;
  eth_kind?: "ethernet" | "wifi" | "other" | string;
  eth_send_rate_bps?: number;
  eth_recv_rate_bps?: number;
  eth_link_mbps?: number;
  cpu_name?: string | null;
  cpu_brand?: string | null;
  processes?: LiveProcesses;
  ts?: number;
};

/** Live CPU/RAM + Ethernet send/receive for the last few minutes. */
export type LiveEthPoint = {
  t: number;
  cpu?: number;
  ram?: number;
  send: number;
  recv: number;
};

export type RealtimeEvent = {
  type: string;
  report?: import("@/lib/api").Report;
  presence?: PresenceEntry;
  job?: {
    device_id?: string;
    pc_name?: string | null;
  };
  metrics?: LiveMetricsSample;
  ts?: number;
};

type PrintingEntry = {
  count: number;
  lastPrintAt: number;
};

type StoredMetrics = LiveMetricsSample & { receivedAt: number };

/** Drop live gauges if the agent misses a few 5s samples. */
const LIVE_METRICS_STALE_MS = 20_000;
/** Keep ~7 minutes of 5s Ethernet samples for the Task Manager-style chart. */
const ETH_HISTORY_MS = 7 * 60 * 1000;
const ETH_HISTORY_MAX = 90;

type RealtimeContextValue = {
  connected: boolean;
  wsUrl: string;
  /** Device -> latest presence (live, Messenger-style). */
  presence: Record<string, PresenceEntry>;
  /** Resolve the live online state for a device_id (true/false/null unknown). */
  isOnline: (deviceId?: string | null) => boolean | null;
  /** Live last-seen for a device, or the fallback when unknown. */
  lastSeenFor: (deviceId?: string | null, fallback?: number) => number | undefined;
  /** Whether a device just printed (live `print.job` push within the window). */
  isPrinting: (deviceId?: string | null) => boolean;
  /** Live count of recent `print.job` events for a device. */
  printingCount: (deviceId?: string | null) => number;
  /** Latest live CPU/RAM/network sample, or null if missing/stale. */
  metricsFor: (deviceId?: string | null) => LiveMetricsSample | null;
  /** Last ~7 minutes of Ethernet send/receive (Mbps) for a live sparkline. */
  metricsHistoryFor: (deviceId?: string | null) => LiveEthPoint[];
  /** Force-refetch every active query (Refresh button). */
  refreshAll: () => void;
};

const RealtimeContext = createContext<RealtimeContextValue>({
  connected: false,
  wsUrl: "",
  presence: {},
  isOnline: () => null,
  lastSeenFor: (): number | undefined => undefined,
  isPrinting: () => false,
  printingCount: () => 0,
  metricsFor: () => null,
  metricsHistoryFor: () => [],
  refreshAll: () => {},
});

/**
 * Opens one secure WebSocket to the API and:
 *  - keeps a live presence map from `presence.changed` events (the server
 *    pushes a heartbeat online instantly; the client flips to offline after
 *    ONLINE_TIMEOUT_SECONDS of silence — Messenger-style), and
 *  - invalidates reports queries on `report.created` so the fleet updates, and
 *  - keeps live CPU/RAM/network gauges and top-process lists from `metrics.sample` (not stored).
 * Reconnects with capped exponential backoff and re-seeds presence.
 */
export function RealtimeProvider({ children }: { children: React.ReactNode }) {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [presence, setPresence] = useState<Record<string, PresenceEntry>>({});
  const [printing, setPrinting] = useState<Record<string, PrintingEntry>>({});
  const [metrics, setMetrics] = useState<Record<string, StoredMetrics>>({});
  const [tick, setTick] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const printTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const ethHistoryRef = useRef<Record<string, LiveEthPoint[]>>({});

  const wsUrl = buildWsUrl(API_URL);

  /** How long a "printing" badge stays lit after the last `print.job`. */
  const PRINT_BADGE_WINDOW_MS = 60_000;

  const setEntry = useCallback(
    (entry: PresenceEntry) => {
      if (!entry?.device_id) return;
      setPresence((prev) => ({ ...prev, [entry.device_id]: entry }));
      // Schedule the offline flip if this entry is online: after the timeout
      // window with no new heartbeat, a Messenger-style dot goes red.
      const key = entry.device_id;
      const existing = timersRef.current[key];
      if (existing) clearTimeout(existing);
      if (entry.online) {
        // Timeout from when we *received* the event, not last_seen vs the
        // browser clock — clock skew otherwise flips a live PC offline in 1s.
        timersRef.current[key] = setTimeout(() => {
          setPresence((prev) => {
            const cur = prev[key];
            if (!cur?.online) return prev;
            return { ...prev, [key]: { ...cur, online: false } };
          });
          delete timersRef.current[key];
        }, ONLINE_TIMEOUT_SECONDS * 1000);
      }
    },
    [],
  );

  const registerPrint = useCallback(
    (deviceId?: string | null) => {
      if (!deviceId) return;
      const key = deviceId;
      setPrinting((prev) => {
        const cur = prev[key] ?? { count: 0, lastPrintAt: 0 };
        return { ...prev, [key]: { count: cur.count + 1, lastPrintAt: Date.now() } };
      });
      const existing = printTimersRef.current[key];
      if (existing) clearTimeout(existing);
      printTimersRef.current[key] = setTimeout(() => {
        setPrinting((prev) => {
          const cur = prev[key];
          if (!cur) return prev;
          if (Date.now() - cur.lastPrintAt >= PRINT_BADGE_WINDOW_MS) {
            const next = { ...prev };
            delete next[key];
            return next;
          }
          return prev;
        });
        delete printTimersRef.current[key];
      }, PRINT_BADGE_WINDOW_MS + 1000);
    },
    [],
  );

  const onEvent = useCallback(
    (event: RealtimeEvent) => {
      if (event.type === "presence.changed" && event.presence) {
        setEntry(event.presence);
      }
      if (event.type === "report.created") {
        queryClient.invalidateQueries({ queryKey: ["reports"] });
        queryClient.invalidateQueries({ queryKey: ["reports-browse"] });
        queryClient.invalidateQueries({ queryKey: ["report-pc"] });
      }
      if (event.type === "print.job") {
        registerPrint(event.job?.device_id);
        queryClient.invalidateQueries({ queryKey: ["print-jobs"] });
        queryClient.invalidateQueries({ queryKey: ["print-summary"] });
      }
      if (event.type === "metrics.sample" && event.metrics?.device_id) {
        const sample = event.metrics;
        const now = Date.now();
        const sendBps = sample.eth_send_rate_bps ?? sample.send_rate_bps ?? 0;
        const recvBps = sample.eth_recv_rate_bps ?? sample.recv_rate_bps ?? 0;
        const point: LiveEthPoint = {
          t: now,
          cpu: sample.cpu_percent,
          ram: sample.ram_percent,
          send: (Math.max(0, sendBps) * 8) / 1_000_000,
          recv: (Math.max(0, recvBps) * 8) / 1_000_000,
        };
        const prev = ethHistoryRef.current[sample.device_id] ?? [];
        ethHistoryRef.current[sample.device_id] = [...prev, point]
          .filter((p) => now - p.t <= ETH_HISTORY_MS)
          .slice(-ETH_HISTORY_MAX);
        setMetrics((prevMetrics) => ({
          ...prevMetrics,
          [sample.device_id]: { ...sample, receivedAt: now },
        }));
      }
    },
    [queryClient, setEntry, registerPrint],
  );

  /** Refresh button: fetch every active query (reports, groups, sub-cats,
   * print jobs, export previews) — regardless of what page is open. */
  const refreshAll = useCallback(() => {
    queryClient.invalidateQueries();
  }, [queryClient]);

  useEffect(() => {
    if (!apiToken) return;
    let disposed = false;
    let retries = 0;

    const connect = () => {
      if (disposed) return;
      const ws = new WebSocket(wsUrl, [apiToken]);
      wsRef.current = ws;

      ws.onopen = () => {
        retries = 0;
        setConnected(true);
      };

      ws.onmessage = (ev) => {
        try {
          onEvent(JSON.parse(ev.data as string) as RealtimeEvent);
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (disposed) return;
        const delay = Math.min(1000 * 2 ** retries, 30_000);
        retries += 1;
        setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();
    return () => {
      disposed = true;
      wsRef.current?.close();
    };
  }, [apiToken, wsUrl, onEvent]);

  // Re-evaluate stale live gauges so "Live" badges drop ~20s after samples stop.
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 5_000);
    return () => clearInterval(id);
  }, []);

  // Clear timers on unmount.
  useEffect(() => {
    return () => {
      for (const t of Object.values(timersRef.current)) clearTimeout(t);
      for (const t of Object.values(printTimersRef.current)) clearTimeout(t);
    };
  }, []);

  const isOnline = useCallback(
    (deviceId?: string | null): boolean | null => {
      if (!deviceId) return null;
      const entry = presence[deviceId];
      if (!entry) return null;
      return entry.online;
    },
    [presence],
  );

  const lastSeenFor = useCallback(
    (deviceId?: string | null, fallback?: number): number | undefined => {
      if (!deviceId) return fallback;
      const entry = presence[deviceId];
      return entry?.last_seen ?? fallback;
    },
    [presence],
  );

  const isPrinting = useCallback(
    (deviceId?: string | null): boolean => {
      if (!deviceId) return false;
      const entry = printing[deviceId];
      if (!entry) return false;
      return Date.now() - entry.lastPrintAt < PRINT_BADGE_WINDOW_MS;
    },
    [printing],
  );

  const printingCount = useCallback(
    (deviceId?: string | null): number => {
      if (!deviceId) return 0;
      const entry = printing[deviceId];
      return entry && Date.now() - entry.lastPrintAt < PRINT_BADGE_WINDOW_MS
        ? entry.count
        : 0;
    },
    [printing],
  );

  const metricsFor = useCallback(
    (deviceId?: string | null): LiveMetricsSample | null => {
      if (!deviceId) return null;
      const entry = metrics[deviceId];
      if (!entry) return null;
      if (Date.now() - entry.receivedAt >= LIVE_METRICS_STALE_MS) return null;
      return entry;
    },
    [metrics, tick],
  );

  const metricsHistoryFor = useCallback(
    (deviceId?: string | null): LiveEthPoint[] => {
      if (!deviceId) return [];
      return ethHistoryRef.current[deviceId] ?? [];
    },
    [metrics, tick],
  );

  return (
    <RealtimeContext.Provider
      value={{
        connected,
        wsUrl,
        presence,
        isOnline,
        lastSeenFor,
        isPrinting,
        printingCount,
        metricsFor,
        metricsHistoryFor,
        refreshAll,
      }}
    >
      {children}
    </RealtimeContext.Provider>
  );
}

export function useRealtime(): RealtimeContextValue {
  return useContext(RealtimeContext);
}

function buildWsUrl(apiUrl: string): string {
  const base = apiUrl.replace(/\/$/, "");
  const wsBase = base.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
  return `${wsBase}/ws`;
}