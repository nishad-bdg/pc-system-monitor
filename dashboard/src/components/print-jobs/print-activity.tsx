"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchGroups,
  fetchPrintJobs,
  fetchPrintSummary,
  fetchReports,
  fetchSubCategories,
  fmtRelative,
  Group,
  groupMachines,
  groupOf,
  MachineSummary,
  PrintJob,
  SubCategory,
  subCategoryOf,
} from "@/lib/api";
import { DashboardShell } from "@/components/dashboard/shell";
import { PrintingBadge } from "@/components/dashboard/printing-badge";
import { useRealtime } from "@/components/realtime-provider";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const MAX_BAR = "#059669";
const MIN_BAR = "#d97706";
const OTHER_BAR = "#2563eb";

type PcPrintGroup = {
  key: string;
  name: string;
  deviceId?: string;
  jobs: PrintJob[];
  last: number;
};

type PcPrintRow = {
  key: string;
  name: string;
  prints: number;
};

function groupJobsByPc(jobs: PrintJob[]): PcPrintGroup[] {
  const map = new Map<string, PcPrintGroup>();
  for (const j of jobs) {
    const key = j.device_id || j.pc_name || "unknown";
    const name = j.pc_name || j.device_id || "Unknown PC";
    let g = map.get(key);
    if (!g) {
      g = { key, name, deviceId: j.device_id, jobs: [], last: 0 };
      map.set(key, g);
    }
    g.jobs.push(j);
    const t = j.completed_at ?? j.created_at ?? 0;
    if (t > g.last) g.last = t;
  }
  return [...map.values()].sort((a, b) => b.last - a.last);
}

function machineInGroup(
  machine: MachineSummary,
  groupId: string,
  groups: Group[],
  subCategories: SubCategory[],
): boolean {
  if (groupOf(machine, groups)?.id === groupId) return true;
  const sub = subCategoryOf(machine, subCategories);
  return !!sub && sub.group_ids.includes(groupId);
}

function machineForJob(
  job: PrintJob,
  machines: MachineSummary[],
): MachineSummary | null {
  if (job.device_id) {
    const byId = machines.find((m) => m.deviceId === job.device_id);
    if (byId) return byId;
  }
  const name = (job.pc_name || "").trim().toLowerCase();
  if (!name) return null;
  return machines.find((m) => m.name.toLowerCase() === name) ?? null;
}

export function PrintActivity() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const { connected, isPrinting, printingCount } = useRealtime();
  const [openKeys, setOpenKeys] = useState<Record<string, boolean>>({});
  const [groupFilter, setGroupFilter] = useState("");

  const { data: jobsResp, isLoading, isError } = useQuery({
    queryKey: ["print-jobs"],
    queryFn: () => fetchPrintJobs(API_URL, apiToken ?? "", 500),
    enabled: !!apiToken,
    refetchInterval: 60_000,
  });

  const { data: summary } = useQuery({
    queryKey: ["print-summary"],
    queryFn: () => fetchPrintSummary(API_URL, apiToken ?? "", 24),
    enabled: !!apiToken,
    refetchInterval: 60_000,
  });

  const { data: orgGroups = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: () => fetchGroups(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
  });

  const { data: subCategories = [] } = useQuery({
    queryKey: ["sub-categories"],
    queryFn: () => fetchSubCategories(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
  });

  const { data: reportsData } = useQuery({
    queryKey: ["reports"],
    queryFn: () => fetchReports(API_URL, apiToken ?? "", 500),
    enabled: !!apiToken,
    staleTime: 30_000,
  });

  const machines = useMemo(
    () => groupMachines(reportsData?.reports ?? []),
    [reportsData?.reports],
  );

  const jobs = jobsResp?.jobs ?? [];

  const scopedJobs = useMemo(() => {
    if (!groupFilter) return jobs;
    return jobs.filter((j) => {
      const m = machineForJob(j, machines);
      return m
        ? machineInGroup(m, groupFilter, orgGroups, subCategories)
        : false;
    });
  }, [jobs, groupFilter, machines, orgGroups, subCategories]);

  const pcGroups = useMemo(
    () => groupJobsByPc(scopedJobs),
    [scopedJobs],
  );

  const perPcRows = useMemo((): PcPrintRow[] => {
    if (groupFilter) {
      const inGroup = machines.filter((m) =>
        machineInGroup(m, groupFilter, orgGroups, subCategories),
      );
      const counts = new Map<string, number>();
      for (const j of scopedJobs) {
        const m = machineForJob(j, inGroup);
        if (!m) continue;
        counts.set(m.key, (counts.get(m.key) ?? 0) + 1);
      }
      return inGroup
        .map((m) => ({
          key: m.key,
          name: m.name,
          prints: counts.get(m.key) ?? 0,
        }))
        .sort((a, b) => b.prints - a.prints || a.name.localeCompare(b.name));
    }
    return groupJobsByPc(jobs)
      .map((g) => ({
        key: g.key,
        name: g.name,
        prints: g.jobs.length,
      }))
      .sort((a, b) => b.prints - a.prints || a.name.localeCompare(b.name));
  }, [groupFilter, machines, orgGroups, subCategories, scopedJobs, jobs]);

  const maxCount = perPcRows.reduce(
    (n, r) => Math.max(n, r.prints),
    0,
  );
  const minCount = perPcRows.reduce(
    (n, r) => Math.min(n, r.prints),
    perPcRows[0]?.prints ?? 0,
  );
  const maxPcs = perPcRows.filter((r) => r.prints === maxCount);
  const minPcs = perPcRows.filter((r) => r.prints === minCount);
  const sameExtremes = perPcRows.length > 0 && maxCount === minCount;

  const totalPages = useMemo(
    () =>
      scopedJobs.reduce(
        (sum, j) => sum + (j.pages && j.pages > 0 ? j.pages : 0),
        0,
      ),
    [scopedJobs],
  );

  const distinctPrinters = useMemo(
    () => new Set(scopedJobs.map((j) => j.printer).filter(Boolean)).size,
    [scopedJobs],
  );

  const isGroupOpen = (key: string) => openKeys[key] ?? true;

  const toggleGroup = (key: string) => {
    setOpenKeys((prev) => ({
      ...prev,
      [key]: !(prev[key] ?? true),
    }));
  };

  const barColor = (prints: number) => {
    if (sameExtremes) return OTHER_BAR;
    if (prints === maxCount) return MAX_BAR;
    if (prints === minCount) return MIN_BAR;
    return OTHER_BAR;
  };

  const selectedGroupName =
    orgGroups.find((g) => g.id === groupFilter)?.name ?? "All groups";

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
        <label className="sr-only" htmlFor="print-group-filter">
          Filter by group
        </label>
        <select
          id="print-group-filter"
          value={groupFilter}
          onChange={(e) => setGroupFilter(e.target.value)}
          className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
        >
          <option value="">All groups</option>
          {orgGroups.map((g: Group) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        {scopedJobs.length === 0 && !isLoading && (
          <p className="text-xs text-slate-500">
            No print jobs recorded yet. Jobs appear here as soon as the desktop
            agent reports them.
          </p>
        )}
        <ul className="space-y-1">
          {pcGroups.map((g) => {
            const open = isGroupOpen(g.key);
            const printing = isPrinting(g.deviceId);
            const printCount = printingCount(g.deviceId);
            return (
              <li key={g.key} className="rounded-lg bg-slate-900/70">
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => toggleGroup(g.key)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left"
                >
                  <span
                    className={`shrink-0 text-[10px] text-slate-500 transition-transform ${
                      open ? "rotate-90" : ""
                    }`}
                    aria-hidden
                  >
                    ▶
                  </span>
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-slate-100">
                    {g.name}
                  </span>
                  {printing && <PrintingBadge count={printCount} />}
                  <span className="shrink-0 text-[10px] text-slate-500">
                    {g.jobs.length} job{g.jobs.length === 1 ? "" : "s"}
                  </span>
                </button>
                {open && (
                  <ul className="space-y-2 border-t border-slate-800 px-3 py-2">
                    {g.jobs.map((j) => (
                      <li key={j._id}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-[11px] text-slate-300">
                            {j.printer}
                          </span>
                          <span className="shrink-0 text-[10px] text-slate-500">
                            {fmtRelative(j.completed_at ?? j.created_at)}
                          </span>
                        </div>
                        <p className="truncate font-mono text-[10px] text-slate-500">
                          {j.document}
                        </p>
                        <div className="mt-0.5 flex gap-2 text-[10px] text-slate-500">
                          {j.user ? <span>{j.user}</span> : null}
                          {j.pages ? <span>{j.pages} pages</span> : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
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
              {scopedJobs.length} prints · {totalPages} pages · {distinctPrinters}{" "}
              printers
              {groupFilter ? ` · ${selectedGroupName}` : ""}
              {scopedJobs[0]?.created_at
                ? ` in the last ${fmtRelative(scopedJobs[0].created_at)}`
                : ""}
              .
            </p>
          </div>
          <div className="flex gap-3 text-xs text-slate-500">
            <span>
              <b className="text-slate-900">{scopedJobs.length}</b> jobs
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
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-sm font-medium text-slate-700">
                Prints per PC
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Job counts from the recent print feed. Pick a group to compare
                only those PCs (zeros included). Green = most, amber = least.
              </p>
            </div>
            <label className="text-xs text-slate-500">
              Group
              <select
                value={groupFilter}
                onChange={(e) => setGroupFilter(e.target.value)}
                className="mt-1 block min-w-48 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
              >
                <option value="">All groups</option>
                {orgGroups.map((g: Group) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {perPcRows.length > 0 ? (
            <>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
                    Most prints
                  </p>
                  <p className="mt-1 truncate text-sm font-semibold text-slate-900">
                    {maxPcs.map((p) => p.name).join(", ")}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-600">
                    {maxCount} job{maxCount === 1 ? "" : "s"}
                  </p>
                </div>
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-800">
                    Least prints
                  </p>
                  <p className="mt-1 truncate text-sm font-semibold text-slate-900">
                    {minPcs.map((p) => p.name).join(", ")}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-600">
                    {minCount} job{minCount === 1 ? "" : "s"}
                  </p>
                </div>
              </div>
              <div className="mt-4 h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={perPcRows}
                    margin={{ bottom: 48, left: 8, right: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis
                      dataKey="name"
                      fontSize={11}
                      stroke="#94a3b8"
                      interval={0}
                      angle={-35}
                      textAnchor="end"
                      height={70}
                    />
                    <YAxis
                      allowDecimals={false}
                      fontSize={11}
                      stroke="#94a3b8"
                    />
                    <Tooltip
                      formatter={(value) => [
                        `${value} print${value === 1 ? "" : "s"}`,
                        "Jobs",
                      ]}
                    />
                    <Bar dataKey="prints" radius={[4, 4, 0, 0]}>
                      {perPcRows.map((row) => (
                        <Cell key={row.key} fill={barColor(row.prints)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <p className="mt-4 text-sm text-slate-500">
              {groupFilter
                ? "No PCs in this group, or none have printed yet."
                : "No print jobs yet — the per-PC chart fills in as jobs arrive."}
            </p>
          )}
        </div>

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
          {scopedJobs.length === 0 ? (
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
                  {scopedJobs.map((j: PrintJob) => (
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
