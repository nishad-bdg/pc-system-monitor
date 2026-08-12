"use client";

import { useRef, useState } from "react";
import { fmtMbps } from "@/lib/api";
import {
  LIVE_DOWNLOAD_BYTES,
  LIVE_UPLOAD_BYTES,
  runLiveSpeedTest,
  type SpeedProgress,
} from "@/lib/speed-test";

type Phase = "idle" | "download" | "upload" | "done" | "error";

function fmtProgressBytes(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} MB`;
  if (n >= 1000) return `${(n / 1000).toFixed(0)} KB`;
  return `${n} B`;
}

export function LiveSpeedTest() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [liveMbps, setLiveMbps] = useState(0);
  const [loaded, setLoaded] = useState(0);
  const [total, setTotal] = useState(0);
  const [downloadMbps, setDownloadMbps] = useState<number | null>(null);
  const [uploadMbps, setUploadMbps] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const running = phase === "download" || phase === "upload";

  async function start() {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setError(null);
    setDownloadMbps(null);
    setUploadMbps(null);
    setLiveMbps(0);
    setLoaded(0);
    setTotal(LIVE_DOWNLOAD_BYTES);
    setPhase("download");

    const onProgress = (p: SpeedProgress) => {
      setPhase(p.phase);
      setLiveMbps(p.mbps);
      setLoaded(p.loadedBytes);
      setTotal(p.totalBytes);
    };

    try {
      const result = await runLiveSpeedTest(onProgress, ac.signal);
      setDownloadMbps(result.downloadMbps);
      setUploadMbps(result.uploadMbps);
      setPhase("done");
      setLiveMbps(0);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setPhase("idle");
        return;
      }
      setError(err instanceof Error ? err.message : "Speed test failed");
      setPhase("error");
    }
  }

  function stop() {
    abortRef.current?.abort();
    abortRef.current = null;
    setPhase("idle");
    setLiveMbps(0);
  }

  const pct =
    total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0;

  return (
    <div className="mt-6 rounded-xl border border-slate-100 bg-slate-50/80 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
            Live speed test
          </h3>
          <p className="mt-1 text-xs text-slate-500">
            Full download (~
            {fmtProgressBytes(LIVE_DOWNLOAD_BYTES)}) + upload (~
            {fmtProgressBytes(LIVE_UPLOAD_BYTES)}) from this admin browser — not
            the remote PC.
          </p>
        </div>
        <div className="flex gap-2">
          {running ? (
            <button
              type="button"
              onClick={stop}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
          ) : (
            <button
              type="button"
              onClick={start}
              className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              {phase === "done" ? "Run again" : "Test download & upload"}
            </button>
          )}
        </div>
      </div>

      {running && (
        <div className="mt-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
            <span className="font-medium text-slate-800">
              {phase === "download" ? "Downloading…" : "Uploading…"}{" "}
              <span className="text-blue-700">{fmtMbps(liveMbps)}</span>
            </span>
            <span className="text-xs text-slate-500">
              {fmtProgressBytes(loaded)} / {fmtProgressBytes(total)} ({pct}%)
            </span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-blue-500 transition-[width]"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {(phase === "done" || downloadMbps != null || uploadMbps != null) &&
        !running && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-blue-100 bg-blue-50/70 px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Download
              </p>
              <p className="mt-1 text-2xl font-semibold text-blue-700">
                {fmtMbps(downloadMbps)}
              </p>
            </div>
            <div className="rounded-lg border border-teal-100 bg-teal-50/70 px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Upload
              </p>
              <p className="mt-1 text-2xl font-semibold text-teal-800">
                {fmtMbps(uploadMbps)}
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
