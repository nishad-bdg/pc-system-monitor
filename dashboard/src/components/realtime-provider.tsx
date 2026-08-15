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

export type RealtimeEvent = {
  type: string;
  report?: import("@/lib/api").Report;
  presence?: PresenceEntry;
  ts?: number;
};

type RealtimeContextValue = {
  connected: boolean;
  wsUrl: string;
  /** Device -> latest presence (live, Messenger-style). */
  presence: Record<string, PresenceEntry>;
  /** Resolve the live online state for a device_id (true/false/null unknown). */
  isOnline: (deviceId?: string | null) => boolean | null;
  /** Live last-seen for a device, or the fallback when unknown. */
  lastSeenFor: (deviceId?: string | null, fallback?: number) => number | undefined;
};

const RealtimeContext = createContext<RealtimeContextValue>({
  connected: false,
  wsUrl: "",
  presence: {},
  isOnline: () => null,
  lastSeenFor: (): number | undefined => undefined,
});

/**
 * Opens one secure WebSocket to the API and:
 *  - keeps a live presence map from `presence.changed` events (the server
 *    pushes a heartbeat online instantly; the client flips to offline after
 *    ONLINE_TIMEOUT_SECONDS of silence — Messenger-style), and
 *  - invalidates reports queries on `report.created` so the fleet updates.
 * Reconnects with capped exponential backoff and re-seeds presence.
 */
export function RealtimeProvider({ children }: { children: React.ReactNode }) {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [presence, setPresence] = useState<Record<string, PresenceEntry>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const wsUrl = buildWsUrl(API_URL);

  const setEntry = useCallback(
    (entry: PresenceEntry) => {
      if (!entry?.device_id) return;
      setPresence((prev) => ({ ...prev, [entry.device_id]: entry }));
      // Schedule the offline flip if this entry is online: after the timeout
      // window with no new heartbeat, a Messenger-style dot goes red.
      const key = entry.device_id;
      const existing = timersRef.current[key];
      if (existing) clearTimeout(existing);
      if (entry.online && entry.last_seen) {
        const delay = Math.max(
          1000,
          (entry.last_seen + ONLINE_TIMEOUT_SECONDS - Date.now() / 1000) * 1000,
        );
        timersRef.current[key] = setTimeout(() => {
          setPresence((prev) => {
            const cur = prev[key];
            if (!cur?.online) return prev;
            return { ...prev, [key]: { ...cur, online: false } };
          });
          delete timersRef.current[key];
        }, delay);
      }
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
        queryClient.invalidateQueries({ queryKey: ["print-jobs"] });
        queryClient.invalidateQueries({ queryKey: ["print-summary"] });
      }
    },
    [queryClient, setEntry],
  );

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

  // Clear timers on unmount.
  useEffect(() => {
    return () => {
      for (const t of Object.values(timersRef.current)) clearTimeout(t);
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

  return (
    <RealtimeContext.Provider
      value={{ connected, wsUrl, presence, isOnline, lastSeenFor }}
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