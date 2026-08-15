"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import { broadcastCommand } from "@/lib/api";

/** Super-admin: push an update command to every currently-online desktop app
 * at once. Each agent stages the update and restarts itself with the new
 * binary (WebSocket-delivered, immediate). */
export function UpdateAppsButton({
  apiUrl,
  apiToken,
}: {
  apiUrl: string;
  apiToken: string;
}) {
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const run = async () => {
    setBusy(true);
    setConfirm(false);
    setResult(null);
    try {
      const res = await broadcastCommand(apiUrl, apiToken, "update");
      setResult({
        ok: true,
        text:
          res.total > 0
            ? `Update sent to ${res.total} connected app${res.total === 1 ? "" : "s"}. Each will update and restart itself.`
            : "No desktop apps are connected right now — no update sent.",
      });
    } catch {
      setResult({ ok: false, text: "Could not send the update. Check the API connection." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setResult(null);
          setConfirm(true);
        }}
        disabled={busy}
        className="w-full rounded-lg border border-blue-700 bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
      >
        {busy ? "Updating…" : "Update all apps"}
      </button>
      {!busy && result && (
        <p
          className={`text-xs ${result.ok ? "text-emerald-400" : "text-red-400"}`}
        >
          {result.text}
        </p>
      )}

      {confirm &&
        createPortal(
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
            <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-xl">
              <h3 className="text-lg font-semibold text-slate-900">Update all apps?</h3>
              <p className="mt-1 text-sm text-slate-500">
                Every currently-connected desktop watcher will immediately check
                for a newer release, stage it if one exists, and restart itself
                to apply it. Machines that are offline right now are skipped.
              </p>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setConfirm(false)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => run()}
                  autoFocus
                  className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-700"
                >
                  Update all now
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}