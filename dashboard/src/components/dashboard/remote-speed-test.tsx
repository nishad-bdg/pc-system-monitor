"use client";

import { useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import {
  createSpeedTestCommand,
  fetchCommand,
  fmtMbps,
  type DeviceCommand,
} from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const POLL_MS = 2000;
const MAX_WAIT_MS = 5 * 60 * 1000;

type Phase = "idle" | "queued" | "running" | "done" | "failed";

export function RemoteSpeedTest({ deviceId }: { deviceId: string | null }) {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const [phase, setPhase] = useState<Phase>("idle");
  const [command, setCommand] = useState<DeviceCommand | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const startedAt = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  function stopPolling() {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  async function start() {
    if (!deviceId) {
      setError("This PC has no device_id yet. Run the agent once, then retry.");
      setPhase("failed");
      return;
    }
    if (!apiToken) {
      setError("Not signed in.");
      setPhase("failed");
      return;
    }

    stopPolling();
    setError(null);
    setCommand(null);
    setElapsedSec(0);
    startedAt.current = Date.now();
    setPhase("queued");

    try {
      const created = await createSpeedTestCommand(API_URL, apiToken, deviceId);
      setCommand(created);
      timerRef.current = setInterval(async () => {
        const started = startedAt.current ?? Date.now();
        setElapsedSec(Math.floor((Date.now() - started) / 1000));
        if (Date.now() - started > MAX_WAIT_MS) {
          stopPolling();
          setError(
            "Timed out waiting for the PC agent. Is SystemInfoPoll / the agent running?",
          );
          setPhase("failed");
          return;
        }
        try {
          const latest = await fetchCommand(API_URL, apiToken, created._id);
          setCommand(latest);
          if (latest.status === "running") setPhase("running");
          if (latest.status === "done") {
            stopPolling();
            setPhase("done");
          }
          if (latest.status === "failed") {
            stopPolling();
            setError(latest.error || "Speed test failed on the remote PC.");
            setPhase("failed");
          }
        } catch (err) {
          stopPolling();
          setError(err instanceof Error ? err.message : "Poll failed");
          setPhase("failed");
        }
      }, POLL_MS);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to queue test");
      setPhase("failed");
    }
  }

  const waiting = phase === "queued" || phase === "running";
  const download = command?.result?.download_mbps;
  const upload = command?.result?.upload_mbps;

  return (
    <div className="mt-6 rounded-xl border border-slate-100 bg-slate-50/80 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
            Remote PC speed test
          </h3>
          <p className="mt-1 text-xs text-slate-500">
            Queues a full download + upload test on this machine. The agent
            usually picks it up within ~2 minutes (SystemInfoPoll).
          </p>
        </div>
        <button
          type="button"
          onClick={start}
          disabled={waiting || !deviceId}
          className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-40"
        >
          {waiting
            ? "Waiting for PC…"
            : phase === "done"
              ? "Test again"
              : "Test remote download & upload"}
        </button>
      </div>

      {!deviceId && (
        <p className="mt-3 text-sm text-amber-700">
          Missing device_id — run <code className="text-xs">system-info</code>{" "}
          on the PC first.
        </p>
      )}

      {waiting && (
        <p className="mt-3 text-sm text-slate-700">
          Status:{" "}
          <span className="font-medium text-blue-700">
            {phase === "queued" ? "queued" : "running on PC"}
          </span>
          <span className="mx-1.5 text-slate-300">·</span>
          waiting {elapsedSec}s
        </p>
      )}

      {phase === "done" && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-blue-100 bg-blue-50/70 px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              Download
            </p>
            <p className="mt-1 text-2xl font-semibold text-blue-700">
              {fmtMbps(download)}
            </p>
          </div>
          <div className="rounded-lg border border-teal-100 bg-teal-50/70 px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              Upload
            </p>
            <p className="mt-1 text-2xl font-semibold text-teal-800">
              {fmtMbps(upload)}
            </p>
          </div>
        </div>
      )}

      {error && (
        <p className="mt-3 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
