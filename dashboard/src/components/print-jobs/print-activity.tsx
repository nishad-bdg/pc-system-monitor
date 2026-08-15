"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchPrintJobs,
  fetchPrintSummary,
  fmtRelative,
  PrintJob,
} from "@/lib/api";
import { DashboardShell } from "@/components/dashboard/shell";
import { useRealtime } from "@/components/realtime-provider";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export function PrintActivity() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const { connected } = useRealtime();

  const { data: jobsResp, isLoading, isError } = useQuery({
    queryKey: ["print-jobs"],
    queryFn: () => fetchPrintJobs(API_URL, apiToken ?? "", 100),
    enabled: !!apiToken,
    refetchInterval: 60_000,
  });

  const { data: summary } = useQuery({
    queryKey: ["print-summary"],
    queryFn: () => fetchPrintSummary(API_URL, apiToken ?? "", 24),
    enabled: !!apiToken,
    refetchInterval: 60_000,
  });

  const jobs = jobsResp?.jobs ?? [];

  const totalPages = useMemo(
    () =>
      jobs.reduce((sum, j) => sum + (j.pages && j.pages > 0 ? j.pages : 0), 0),
    [jobs],
  );

  const distinctPrinters = useMemo(
    () => new Set(jobs.map((j) => j.printer).filter(Boolean)).size,
    [jobs],
  );

  const byPc = useMemo(() => {
    const map = new Map<string, { count: number; last: number | undefined }>();
    for (const j of jobs) {
      const key = j.pc_name || j.device_id || "Unknown PC";
      const entry = map.get(key) ?? { count: 0, last: undefined };
      entry.count += 1;
      if (j.completed_at && (!entry.last || j.completed_at > entry.last)) {
        entry.last = j.completed_at;
      }
      map.set(key, entry);
    }
    return [...map.entries()]
      .map(([name, v]) => ({ name, ...v }))
      .sort((a, b) => b.count - a.count);
  }, [jobs]);

  const sidebar = (
    <>
      <div className="p-4">
        <div className="mb-3 flex items-center justify-between text-xs">
          <span className="font-semibold uppercase tracking-[0.12em] text-slate-400">
            Recent prints
          </span>
          <span
            className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${
              connected
                ? "bg-emerald-500/15 text-emerald-300"
                : "bg-red-500/15 text-red-300"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                connected ? "bg-emerald-400" : "bg-red-400"
              }`}
            />
            {connected ? "LIVE" : "OFFLINE"}
          </span>
        </div>
        {jobs.length === 0 && !isLoading && (
          <p className="text-xs text-slate-500">
            No print jobs recorded yet. Jobs appear here as soon as the desktop
            agent reports them.
          </p>
        )}
        <ul className="space-y-2">
          {jobs.map((j) => (
            <li key={j._id}>
              <div className="rounded-lg bg-slate-900/70 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-xs font-medium text-slate-100">
                    {j.pc_name || j.device_id || "Unknown PC"}
                  </span>
                  <span className="shrink-0 text-[10px] text-slate-500">
                    {fmtRelative(j.completed_at ?? j.created_at)}
                  </span>
                </div>
                <p className="mt-0.5 truncate text-[11px] text-slate-300">
                  {j.printer}
                </p>
                <p className="truncate font-mono text-[10px] text-slate-500">
                  {j.document}
                </p>
                <div className="mt-0.5 flex gap-2 text-[10px] text-slate-500">
                  {j.user ? <span>{j.user}</span> : null}
                  {j.pages ? <span>{j.pages} pages</span> : null}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
      <div className="border-t border-slate-800 p-4">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
          Per PC (recent)
        </p>
        <ul className="space-y-1">
          {byPc.map((row) => (
            <li key={row.name} className="flex items-center justify-between text-xs">
              <span className="truncate text-slate-300">{row.name}</span>
              <span className="ml-2 shrink-0 text-slate-500">
                {row.count} job{row.count === 1 ? "" : "s"}
              </span>
            </li>
          ))}
          {byPc.length === 0 && (
            <li className="text-xs text-slate-500">—</li>
          )}
        </ul>
      </div>
    </>
  );

  const chartData =
    summary?.buckets.map((b) => ({ label: b.hour, prints: b.count })) ?? [];

  return (
    <DashboardShell
      title="Print Activity"
      subtitle="Live & per-hour print jobs"
      nav="prints"
      role={session?.user?.role}
      widthClass="w-80"
      sidebar={sidebar}
      header={
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-6 py-4 backdrop-blur">
          <div>
            <h2 className="text-xl font-semibold tracking-tight text-slate-900">
              <span className="inline-flex items-center gap-2">
                <span
                  className={`h-2 w-2 rounded-full ${
                    connected ? "bg-emerald-500" : "bg-slate-300"
                  }`}
                />
                Live printing
              </span>
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              {jobs.length} prints · {totalPages} pages · {distinctPrinters}{" "}
              printers in the last {fmtRelative(jobs[0]?.created_at)}.
            </p>
          </div>
          <div className="flex gap-3 text-xs text-slate-500">
            <span>
              <b className="text-slate-900">{jobs.length}</b> jobs
            </span>
            <span>
              <b className="text-slate-900">{totalPages}</b> pages
            </span>
            <span>
              <b className="text-slate-900">{distinctPrinters}</b> printers
            </span>
          </div>
        </div>
      }
    >
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {isError && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Failed to load print activity from {API_URL}.
          </div>
        )}

        <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
          <h2 className="text-sm font-medium text-slate-700">
            Print jobs per hour (last 24h)
          </h2>
          {chartData.length > 0 ? (
            <div className="mt-3 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="label"
                    fontSize={10}
                    stroke="#94a3b8"
                    tickFormatter={(v: string) =>
                      v.replace("T", "\n").replace(":00", "")
                    }
                    interval="preserveStartEnd"
                  />
                  <YAxis allowDecimals={false} fontSize={11} stroke="#94a3b8" />
                  <Tooltip
                    formatter={(value) => [
                      `${value} print${value === 1 ? "" : "s"}`,
                      "Jobs",
                    ]}
                    labelFormatter={(label) =>
                      `${String(label).replace("T", " ").replace(":00", ":00")} UTC`
                    }
                  />
                  <Bar dataKey="prints" fill="#2563eb" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-500">
              No prints in the last 24 hours — the chart fills in as the agent
              reports jobs.
            </p>
          )}
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
          <h2 className="text-sm font-medium text-slate-700">Recent prints</h2>
          {jobs.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500">
              Waiting for print jobs…
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-500">
                    <th className="py-2 pr-4 font-medium">When</th>
                    <th className="py-2 pr-4 font-medium">PC</th>
                    <th className="py-2 pr-4 font-medium">Printer</th>
                    <th className="py-2 pr-4 font-medium">Document</th>
                    <th className="py-2 pr-4 font-medium">User</th>
                    <th className="py-2 font-medium">Pages</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j: PrintJob) => (
                    <tr
                      key={j._id}
                      className="border-b border-slate-100 last:border-0 hover:bg-slate-50/80"
                    >
                      <td className="whitespace-nowrap py-2.5 pr-4 text-slate-500">
                        {fmtRelative(j.completed_at ?? j.created_at)}
                      </td>
                      <td className="py-2.5 pr-4 font-medium text-slate-900">
                        {j.pc_name || j.device_id || "—"}
                      </td>
                      <td className="py-2.5 pr-4 text-slate-600">
                        {j.printer || "—"}
                      </td>
                      <td className="max-w-[220px] truncate py-2.5 pr-4 font-mono text-slate-600">
                        {j.document || "—"}
                      </td>
                      <td className="py-2.5 pr-4 text-slate-600">
                        {j.user || "—"}
                      </td>
                      <td className="py-2.5 text-slate-600">
                        {j.pages ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </DashboardShell>
  );
}