"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionProvider } from "next-auth/react";
import { useState } from "react";
import { RealtimeProvider } from "./realtime-provider";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { refetchOnWindowFocus: false, staleTime: 30_000 },
        },
      }),
  );
  return (
    <SessionProvider>
      <QueryClientProvider client={client}>
        <RealtimeProvider>{children}</RealtimeProvider>
      </QueryClientProvider>
    </SessionProvider>
  );
}