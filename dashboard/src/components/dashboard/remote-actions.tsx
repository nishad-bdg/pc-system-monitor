"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { createPortal } from "react-dom";
import { pingDevice, sendCommand } from "@/lib/api";

const ADMIN_ROLES = new Set(["admin", "super_admin"]);

type ActionType = "restart" | "shutdown";

const ACTION_LABELS: Record<ActionType, { button: string; title: string; body: string }> = {
  restart: {
    button: "Restart",
    title: "Restart this PC?",
    body: "The machine will reboot within a few seconds. Any unsaved work is lost.",
  },
  shutdown: {
    button: "Shut down",
    title: "Shut down this PC?",
    body: "The machine will power off within a few seconds. Unsaved work is lost.",
  },
};

/** Remote Ping / Restart / Shutdown (admin + super_admin). Ping works on any OS. */
export function RemoteActions({
  apiUrl,
  deviceId,
  pcName,
  osSystem,
}: {
  apiUrl: string;
  deviceId: string | null;
  pcName: string;
  osSystem?: string | null;
}) {
  const { data: session } = useSession();
  const role = session?.user?.role ?? "";
  const apiToken = session?.user?.apiToken ?? "";
  const [pending, setPending] = useState<ActionType | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [confirmAction, setConfirmAction] = useState<ActionType | null>(null);

  const isWindows = (osSystem ?? "").toLowerCase().startsWith("win");
  if (!deviceId || !ADMIN_ROLES.has(role)) return null;

  const openConfirm = (action: ActionType) => {
    setMessage(null);
    setConfirmAction(action);
  };

  const runPing = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const res = await pingDevice(apiUrl, apiToken, deviceId);
      if (res.connected) {
        const latency = res.rtt_ms != null ? ` (${res.rtt_ms} ms)` : "";
        setMessage({ ok: true, text: `${pcName} is connected${latency}.` });
      } else {
        setMessage({
          ok: false,
          text: `${pcName} is not connected right now.`,
        });
      }
    } catch (err) {
      setMessage({
        ok: false,
        text: err instanceof Error ? err.message : "Could not ping this PC",
      });
    } finally {
      setBusy(false);
    }
  };

  const run = async (action: ActionType) => {
    setBusy(true);
    setConfirmAction(null);
    setMessage(null);
    try {
      await sendCommand(apiUrl, apiToken, deviceId, action);
      setPending(action);
      setMessage({
        ok: true,
        text: `${ACTION_LABELS[action].button} command sent to ${pcName} — the machine will ${action === "restart" ? "reboot" : "power off"} within seconds.`,
      });
    } catch (err) {
      setMessage({
        ok: false,
        text: err instanceof Error ? err.message : `Could not send the ${action} command`,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={runPing}
          className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
        >
          {busy && !pending ? "Pinging…" : "Ping"}
        </button>
        {isWindows && (
          <>
            <button
              type="button"
              disabled={busy || !!pending}
              onClick={() => openConfirm("restart")}
              className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100 disabled:opacity-50"
            >
              {pending === "restart" ? "Restart sent…" : "Restart"}
            </button>
            <button
              type="button"
              disabled={busy || !!pending}
              onClick={() => openConfirm("shutdown")}
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50"
            >
              {pending === "shutdown" ? "Shutdown sent…" : "Shut down"}
            </button>
          </>
        )}
      </div>
      {busy && <p className="text-xs text-slate-400">{pending ? "Sending command…" : "Pinging…"}</p>}
      {!busy && message && (
        <p
          className={`text-xs ${
            message.ok ? "text-emerald-600" : "text-red-600"
          }`}
        >
          {message.text}
        </p>
      )}

      {confirmAction &&
        createPortal(
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
            <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-xl">
              <h3 className="text-lg font-semibold text-slate-900">
                {ACTION_LABELS[confirmAction].title}
              </h3>
              <p className="mt-1 text-sm text-slate-500">
                {ACTION_LABELS[confirmAction].body}
              </p>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setConfirmAction(null)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => run(confirmAction)}
                  autoFocus
                  className={`rounded-lg px-3 py-1.5 text-sm font-semibold text-white ${
                    confirmAction === "shutdown" ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"
                  }`}
                >
                  {ACTION_LABELS[confirmAction].button}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
