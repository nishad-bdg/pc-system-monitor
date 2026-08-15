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

export type RealtimeEvent = {
  type: string;
  report?: import("@/lib/api").Report;
  ts?: number;
};

type RealtimeContextValue = {
  connected: boolean;
  wsUrl: string;
};

const RealtimeContext = createContext<RealtimeContextValue>({
  connected: false,
  wsUrl: "",
});

/**
 * Opens one secure WebSocket to the API and, on `report.created` events,
 * invalidates the reports queries so the fleet/printers update in realtime.
 * Reconnects with capped exponential backoff.
 */
export function RealtimeProvider({ children }: { children: React.ReactNode }) {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const wsUrl = buildWsUrl(API_URL);

  const onEvent = useCallback(
    (event: RealtimeEvent) => {
      if (event.type === "report.created") {
        queryClient.invalidateQueries({ queryKey: ["reports"] });
        queryClient.invalidateQueries({ queryKey: ["reports-browse"] });
        queryClient.invalidateQueries({ queryKey: ["report-pc"] });
      }
    },
    [queryClient],
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

  return (
    <RealtimeContext.Provider value={{ connected, wsUrl }}>
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