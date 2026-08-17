"use client";

import { useState } from "react";
import { sendCommandBatch } from "@/lib/api";

/** Admin: ask every targeted PC to reopen `/ws/agent`.
 * Offline agents keep the command pending and reconnect on the next heartbeat
 * if the desktop app is running with internet. */
export function ConnectAllButton({
  apiUrl,
  apiToken,
  deviceIds,
}: {
  apiUrl: string;
  apiToken: string;
  deviceIds: string[];
}) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const run = async () => {
    setBusy(true);
    setResult(null);
    try {
      const res = await sendCommandBatch(apiUrl, apiToken, "reconnect", deviceIds);
      const n = res.total;
      setResult({
        ok: true,
        text:
          n > 0
            ? `Asked ${n} PC${n === 1 ? "" : "s"} to reconnect. If the app is running with internet, they should come online within a minute.`
            : "No PCs in this list have a device id — nothing sent.",
      });
    } catch {
      setResult({
        ok: false,
        text: "Could not send Connect all. Check the API connection.",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={run}
        disabled={busy || deviceIds.length === 0}
        className="w-full rounded-lg border border-violet-700 bg-violet-600 px-3 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
      >
        {busy ? "Connecting…" : "Connect all"}
      </button>
      {!busy && result && (
        <p
          className={`text-xs ${result.ok ? "text-emerald-400" : "text-red-400"}`}
        >
          {result.text}
        </p>
      )}
    </>
  );
}
