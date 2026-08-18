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
  fetchPrintJobsByPrinter,
  fetchPrintSummary,
  fetchReports,
  fetchSubCategories,
  fmtRelative,
  Group,
  groupMachines,
  groupOf,
  printerIpLookup,
  MachineSummary,
  PrintJob,
  SubCategory,
  subCategoryOf,
} from "@/lib/api";
import { downloadExportPdf } from "@/lib/export-pdf";
import { DashboardShell } from "@/components/dashboard/shell";
import { PrintingBadge } from "@/components/dashboard/printing-badge";
import { useRealtime } from "@/components/realtime-provider";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const TABLE_PAGE_SIZE = 25;
const MAX_BAR = "#059669";
const MIN_BAR = "#d97706";
const OTHER_BAR = "#2563eb";

type SummaryRange =
  | "last24h"
  | "daily"
  | "weekly"
  | "monthly"
  | "yearly"
  | "custom";

const SUMMARY_RANGES: { key: SummaryRange; label: string }[] = [
  { key: "last24h", label: "Last 24 hours" },
  { key: "daily", label: "Daily" },
  { key: "weekly", label: "Weekly" },
  { key: "monthly", label: "Monthly" },
  { key: "yearly", label: "Yearly" },
  { key: "custom", label: "Custom range" },
];

function startOfUtcDay(ts: number): number {
  const d = new Date(ts * 1000);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) / 1000;
}

function startOfUtcMonth(ts: number): number {
  const d = new Date(ts * 1000);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) / 1000;
}

function summaryRangeFor(
  key: SummaryRange,
  customFrom?: string,
  customTo?: string,
): { fromTs?: number; toTs?: number; bucket: string } {
  const now = Math.floor(Date.now() / 1000);
  const day = 86400;
  switch (key) {
    case "daily":
      return { fromTs: startOfUtcDay(now), toTs: now, bucket: "hour" };
    case "weekly":
      return { fromTs: now - 7 * day, toTs: now, bucket: "day" };
    case "monthly":
      return { fromTs: startOfUtcMonth(now), toTs: now, bucket: "day" };
    case "yearly":
      return { fromTs: now - 365 * day, toTs: now, bucket: "month" };
    case "custom": {
      const from = customFrom ? new Date(customFrom + "T00:00:00").getTime() / 1000 : undefined;
      const to = customTo ? new Date(customTo + "T23:59:59").getTime() / 1000 : undefined;
      const spanDays = (to ?? now) - (from ?? 0);
      const bucket =
        spanDays <= 3 * day
          ? "hour"
          : spanDays <= 60 * day
            ? "day"
            : "month";
      return { fromTs: from, toTs: to, bucket };
    }
    case "last24h":
    default:
      return { fromTs: now - 24 * 3600, toTs: now, bucket: "hour" };
  }
}

function summaryRangeLabel(range: SummaryRange): string {
  const hit = SUMMARY_RANGES.find((r) => r.key === range);
  return hit ? hit.label : "Last 24 hours";
}

function summaryRangeTitle(range: SummaryRange): string {
  switch (range) {
    case "daily":
      return "Print jobs per hour (today)";
    case "weekly":
      return "Print jobs per day (last 7 days)";
    case "monthly":
      return "Print jobs per day (this month)";
    case "yearly":
      return "Print jobs per month (last 365 days)";
    case "custom":
      return "Print jobs for the custom range";
    case "last24h":
    default:
      return "Print jobs per hour (last 24h)";
  }
}

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
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [summaryRange, setSummaryRange] = useState<SummaryRange>("last24h");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [pcRange, setPcRange] = useState<SummaryRange>("last24h");
  const [pcCustomFrom, setPcCustomFrom] = useState("");
  const [pcCustomTo, setPcCustomTo] = useState("");
  const [printerRange, setPrinterRange] = useState<SummaryRange>("weekly");
  const [printerCustomFrom, setPrinterCustomFrom] = useState("");
  const [printerCustomTo, setPrinterCustomTo] = useState("");
  const [pdfBusy, setPdfBusy] = useState(false);

  const groupQuery = groupFilter || undefined;

  const { data: feedResp, isLoading, isError } = useQuery({
    queryKey: ["print-jobs", "feed", groupFilter],
    queryFn: () =>
      fetchPrintJobs(API_URL, apiToken ?? "", 500, 0, { groupId: groupQuery }),
    enabled: !!apiToken,
    refetchInterval: 60_000,
  });

  const { data: tableResp, isFetching: tableFetching } = useQuery({
    queryKey: ["print-jobs", "page", page, groupFilter, search],
    queryFn: () =>
      fetchPrintJobs(
        API_URL,
        apiToken ?? "",
        TABLE_PAGE_SIZE,
        (page - 1) * TABLE_PAGE_SIZE,
        { groupId: groupQuery, search: search.trim() || undefined },
      ),
    enabled: !!apiToken,
    refetchInterval: 60_000,
    placeholderData: (prev) => prev,
  });

  const { data: summary } = useQuery({
    queryKey: ["print-summary", summaryRange, customFrom, customTo],
    queryFn: () => {
      if (summaryRange === "last24h") {
        return fetchPrintSummary(API_URL, apiToken ?? "", 24);
      }
      const range = summaryRangeFor(summaryRange, customFrom, customTo);
      return fetchPrintSummary(API_URL, apiToken ?? "", 24, range);
    },
    enabled: !!apiToken,
    refetchInterval: 60_000,
  });

  const { data: orgGroups = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: () => fetchGroups(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
  });

  const printerRangeWindow = useMemo(() => {
    if (printerRange === "last24h") return null;
    return summaryRangeFor(printerRange, printerCustomFrom, printerCustomTo);
  }, [printerRange, printerCustomFrom, printerCustomTo]);

  const { data: printByPrinter } = useQuery({
    queryKey: [
      "print-jobs-by-printer",
      printerRange,
      printerCustomFrom,
      printerCustomTo,
      groupFilter,
    ],
    queryFn: () =>
      fetchPrintJobsByPrinter(API_URL, apiToken ?? "", {
        fromTs: printerRangeWindow?.fromTs,
        toTs: printerRangeWindow?.toTs,
        groupId: groupFilter || undefined,
      }),
    enabled: !!apiToken,
    refetchInterval: 60_000,
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

  const jobs = feedResp?.jobs ?? [];
  const tableJobs = tableResp?.jobs ?? [];
  const tableTotal = tableResp?.total ?? 0;
  const tablePages = Math.max(1, Math.ceil(tableTotal / TABLE_PAGE_SIZE));
  const safePage = Math.min(page, tablePages);
  const tableStart = tableTotal === 0 ? 0 : (safePage - 1) * TABLE_PAGE_SIZE;

  const scopedJobs = jobs;

  const pcRangeWindow = useMemo(() => {
    if (pcRange === "last24h") return null;
    return summaryRangeFor(pcRange, pcCustomFrom, pcCustomTo);
  }, [pcRange, pcCustomFrom, pcCustomTo]);

  const pcJobs = useMemo(() => {
    let rows = jobs;
    const win = pcRangeWindow;
    if (win) {
      rows = rows.filter((j) => {
        const t = j.completed_at ?? j.created_at ?? 0;
        if (win.fromTs != null && t < win.fromTs) return false;
        if (win.toTs != null && t > win.toTs) return false;
        return true;
      });
    }
    return rows;
  }, [jobs, pcRangeWindow]);

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
      for (const j of pcJobs) {
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
    return groupJobsByPc(pcJobs)
      .map((g) => ({
        key: g.key,
        name: g.name,
        prints: g.jobs.length,
      }))
      .sort((a, b) => b.prints - a.prints || a.name.localeCompare(b.name));
  }, [groupFilter, machines, orgGroups, subCategories, pcJobs]);

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

  const topPrinters = useMemo(() => {
    const counts = new Map<string, { jobs: number; pcs: Set<string> }>();
    for (const j of pcJobs) {
      const p = j.printer || "Unknown printer";
      const cur = counts.get(p) ?? { jobs: 0, pcs: new Set<string>() };
      cur.jobs += 1;
      if (j.pc_name) cur.pcs.add(j.pc_name);
      counts.set(p, cur);
    }
    const rows = [...counts.entries()]
      .map(([printer, v]) => ({
        printer,
        jobs: v.jobs,
        pcs: [...v.pcs].sort((a, b) => a.localeCompare(b)),
      }))
      .sort((a, b) => b.jobs - a.jobs || a.printer.localeCompare(b.printer));
    const max = rows.length ? rows[0].jobs : 0;
    const topRow = rows.find((r) => r.jobs === max);
    return {
      top: rows.slice(0, 5),
      maxPrinter: rows.filter((r) => r.jobs === max).map((r) => r.printer),
      maxCount: max,
      topRow,
    };
  }, [pcJobs]);

  const printerIp = useMemo(() => printerIpLookup(machines), [machines]);

  const printerRows = useMemo(
    () =>
      (printByPrinter?.printers ?? []).map((p) => ({
        printer: p.printer || "Unknown printer",
        jobs: p.jobs,
        pages: p.pages,
        pcs: p.pcs ?? [],
      })),
    [printByPrinter],
  );

  const handlePrinterPdf = async () => {
    if (pdfBusy || !apiToken) return;
    setPdfBusy(true);
    try {
      const win = printerRangeWindow;
      const span = win
        ? `${new Date((win.fromTs ?? 0) * 1000).toLocaleDateString()} – ${new Date((win.toTs ?? Date.now() / 1000) * 1000).toLocaleDateString()}`
        : "Last 24 hours";
      const most = printerRows.length ? printerRows[0] : null;
      await downloadExportPdf({
        filename: `printer-report-${printerRange}-${Date.now()}.pdf`,
        title: "Printer Usage Report",
        subtitle: [
          `${summaryRangeLabel(printerRange)} · ${span}`,
          groupFilter
            ? `Group: ${selectedGroupName}`
            : "Group: All groups",
          `${printerRows.length} printer${printerRows.length === 1 ? "" : "s"} used`,
          `Generated ${new Date().toLocaleString()}`,
        ],
        stats: [
          { label: "Total prints", value: (printByPrinter?.total_jobs ?? 0).toLocaleString() },
          { label: "Total pages", value: (printByPrinter?.total_pages ?? 0).toLocaleString() },
          {
            label: "Most used",
            value: most ? `${most.printer} (${most.jobs})` : "-",
          },
          {
            label: "Top printer pages",
            value: most ? most.pages.toLocaleString() : "-",
          },
        ],
        tables: [
          {
            title: "Printers - jobs and pages",
            head: ["Printer", "Jobs", "Pages", "Connected PC(s)"],
            body: printerRows.map((p) => [
              p.printer,
              p.jobs.toLocaleString(),
              p.pages.toLocaleString(),
              p.pcs.length
                ? p.pcs.filter(Boolean).join(", ")
                : (printerIp.get(p.printer.trim().toLowerCase()) ?? "-"),
            ]),
          },
        ],
      });
    } finally {
      setPdfBusy(false);
    }
  };

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
          onChange={(e) => {
            setGroupFilter(e.target.value);
            setPage(1);
          }}
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
    summary?.buckets.map((b) => ({
      label: b.hour,
      prints: b.count,
    })) ?? [];

  const bucketTick = (v: string) => {
    if (summaryRange === "yearly" || summaryRange === "custom") {
      if (/^\d{4}-\d{2}$/.test(v)) return v;
      return v.slice(0, 10);
    }
    return v.replace("T", "\n").replace(":00", "");
  };

  const chartEmptyMessage =
    summary && summary.buckets.length === 0
      ? `No prints in the ${summaryRangeLabel(summaryRange)} — the chart fills in as the agent reports jobs.`
      : "No prints in the last 24 hours — the chart fills in as the agent reports jobs.";

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
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-xs text-slate-500">
                Range
                <select
                  value={pcRange}
                  onChange={(e) => setPcRange(e.target.value as SummaryRange)}
                  className="mt-1 block min-w-36 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
                >
                  {SUMMARY_RANGES.map((r) => (
                    <option key={r.key} value={r.key}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </label>
              {pcRange === "custom" && (
                <>
                  <label className="text-xs text-slate-500">
                    From
                    <input
                      type="date"
                      value={pcCustomFrom}
                      onChange={(e) => setPcCustomFrom(e.target.value)}
                      className="mt-1 block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
                    />
                  </label>
                  <label className="text-xs text-slate-500">
                    To
                    <input
                      type="date"
                      value={pcCustomTo}
                      onChange={(e) => setPcCustomTo(e.target.value)}
                      className="mt-1 block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
                    />
                  </label>
                </>
              )}
              <label className="text-xs text-slate-500">
                Group
                <select
                  value={groupFilter}
                  onChange={(e) => {
                    setGroupFilter(e.target.value);
                    setPage(1);
                  }}
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
          </div>

          {perPcRows.length > 0 ? (
            <>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
                <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-700">
                    Most used printer
                  </p>
                  <p className="mt-1 truncate text-sm font-semibold text-slate-900">
                    {topPrinters.maxPrinter.length
                      ? topPrinters.maxPrinter.join(", ")
                      : "—"}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-slate-600">
                    {(() => {
                      const r = topPrinters.topRow;
                      if (!r) return "no jobs in the selected range";
                      const ip = printerIp.get(r.printer.trim().toLowerCase());
                      const loc = ip
                        ? ip
                        : r.pcs.length
                          ? `via ${r.pcs.join(", ")}`
                          : "";
                      return [loc, `${topPrinters.maxCount} job${topPrinters.maxCount === 1 ? "" : "s"}`]
                        .filter(Boolean)
                        .join(" · ");
                    })()}
                  </p>
                </div>
              </div>
              {topPrinters.top.length > 0 && (
                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                    Top printers · usage ranking
                  </p>
                  <ol className="mt-2 space-y-1.5">
                    {topPrinters.top.map((row, i) => (
                      <li key={`${row.printer}-${i}`} className="flex items-center gap-3">
                        <span
                          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                            i === 0
                              ? "bg-blue-100 text-blue-700"
                              : i === 1
                                ? "bg-slate-200 text-slate-600"
                                : i === 2
                                  ? "bg-orange-100 text-orange-700"
                                  : "bg-slate-100 text-slate-500"
                          }`}
                        >
                          {i + 1}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">
                          {row.printer}
                        </span>
                        <span className="hidden shrink-0 truncate text-xs text-slate-500 sm:block">
                          {printerIp.get(row.printer.trim().toLowerCase()) ??
                            (row.pcs.length ? `via ${row.pcs.join(", ")}` : "")}
                        </span>
                        <span className="shrink-0 text-sm font-semibold text-slate-600">
                          {row.jobs} job{row.jobs === 1 ? "" : "s"}
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
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
                ? "No PCs in this group, or none have printed in the selected range."
                : `No print jobs ${pcRange === "last24h" ? "yet" : `in the ${summaryRangeLabel(pcRange)}`} — the per-PC chart fills in as jobs arrive.`}
            </p>
          )}
        </div>

        <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-medium text-slate-700">
                Prints per printer
                {printerRows.length > 0 && (
                  <span className="ml-2 rounded-full bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
                    {printerRows.reduce((s, p) => s + p.jobs, 0).toLocaleString()}{" "}
                    total
                  </span>
                )}
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Job counts per printer from the print-job database — pick a
                range and export the report as PDF.
              </p>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-xs text-slate-500">
                Range
                <select
                  value={printerRange}
                  onChange={(e) =>
                    setPrinterRange(e.target.value as SummaryRange)
                  }
                  className="mt-1 block min-w-36 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
                >
                  {SUMMARY_RANGES.map((r) => (
                    <option key={r.key} value={r.key}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </label>
              {printerRange === "custom" && (
                <>
                  <label className="text-xs text-slate-500">
                    From
                    <input
                      type="date"
                      value={printerCustomFrom}
                      onChange={(e) => setPrinterCustomFrom(e.target.value)}
                      className="mt-1 block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
                    />
                  </label>
                  <label className="text-xs text-slate-500">
                    To
                    <input
                      type="date"
                      value={printerCustomTo}
                      onChange={(e) => setPrinterCustomTo(e.target.value)}
                      className="mt-1 block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
                    />
                  </label>
                </>
              )}
              <button
                type="button"
                onClick={handlePrinterPdf}
                disabled={pdfBusy || printerRows.length === 0}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {pdfBusy ? "Building…" : "Export PDF"}
              </button>
            </div>
          </div>
          {printerRows.length > 0 ? (
            <div className="mt-3 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={printerRows}
                  margin={{ bottom: 48, left: 8, right: 8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="printer"
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
                    formatter={(value, _name, entry) => {
                      const row = entry.payload as (typeof printerRows)[number];
                      return [
                        `${value} print${value === 1 ? "" : "s"} · ${row.pages} page${row.pages === 1 ? "" : "s"}`,
                        "Jobs",
                      ];
                    }}
                  />
                  <Bar
                    dataKey="jobs"
                    radius={[4, 4, 0, 0]}
                    fill="#2563eb"
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-500">
              No print jobs{" "}
              {printerRange === "last24h"
                ? "yet"
                : `in the ${summaryRangeLabel(printerRange)}`}{" "}
              — the per-printer chart fills in as the agent reports jobs.
            </p>
          )}
        </div>

        <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-medium text-slate-700">
                {summaryRangeTitle(summaryRange)}
                {chartData.length > 0 && (
                  <span className="ml-2 rounded-full bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
                    {chartData.reduce((s, b) => s + (Number(b.prints) || 0), 0).toLocaleString()}{" "}
                    total
                  </span>
                )}
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                {summaryRange === "last24h"
                  ? "Last 24 hours by default — switch to daily, weekly, monthly, yearly, or a custom date range."
                  : `${summaryRangeLabel(summaryRange)} print-job counts.`}
              </p>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-xs text-slate-500">
                Range
                <select
                  value={summaryRange}
                  onChange={(e) => setSummaryRange(e.target.value as SummaryRange)}
                  className="mt-1 block min-w-36 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
                >
                  {SUMMARY_RANGES.map((r) => (
                    <option key={r.key} value={r.key}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </label>
              {summaryRange === "custom" && (
                <>
                  <label className="text-xs text-slate-500">
                    From
                    <input
                      type="date"
                      value={customFrom}
                      onChange={(e) => setCustomFrom(e.target.value)}
                      className="mt-1 block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
                    />
                  </label>
                  <label className="text-xs text-slate-500">
                    To
                    <input
                      type="date"
                      value={customTo}
                      onChange={(e) => setCustomTo(e.target.value)}
                      className="mt-1 block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
                    />
                  </label>
                </>
              )}
            </div>
          </div>
          {chartData.length > 0 ? (
            <div className="mt-3 h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="label"
                    fontSize={10}
                    stroke="#94a3b8"
                    tickFormatter={bucketTick}
                    minTickGap={24}
                  />
                  <YAxis allowDecimals={false} fontSize={11} stroke="#94a3b8" />
                  <Tooltip
                    formatter={(value) => [
                      `${value} print${value === 1 ? "" : "s"}`,
                      "Jobs",
                    ]}
                    labelFormatter={(label) =>
                      `${String(label)
                        .replace("T", " ")
                        .replace(/:00$/, ":00")} UTC`
                    }
                  />
                  <Bar dataKey="prints" fill="#2563eb" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-500">{chartEmptyMessage}</p>
          )}
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-medium text-slate-700">Recent prints</h2>
            <label className="relative block" htmlFor="print-search">
              <svg
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
                aria-hidden
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M21 21l-4.35-4.35M17 10a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              <input
                id="print-search"
                type="search"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                placeholder="Search PC, printer, document, user…"
                className="w-64 max-w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-slate-900 placeholder:text-slate-400 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
              />
            </label>
          </div>
          {search.trim() && tableTotal > 0 && (
            <p className="mt-2 text-xs text-slate-500">
              {tableTotal} job{tableTotal === 1 ? "" : "s"} match
              {tableTotal === 1 ? "es" : ""} “{search.trim()}”.
            </p>
          )}
          {tableTotal === 0 ? (
            <p className="mt-3 text-sm text-slate-500">
              {search.trim()
                ? `No print jobs match “${search.trim()}”.`
                : "Waiting for print jobs…"}
            </p>
          ) : (
            <>
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
                  {tableJobs.map((j: PrintJob) => (
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
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-slate-500">
                {tableFetching ? "Loading… · " : ""}
                Showing {tableStart + 1}–
                {Math.min(tableStart + TABLE_PAGE_SIZE, tableTotal)} of{" "}
                {tableTotal} · Page {safePage} of {tablePages}
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={safePage <= 1}
                  onClick={() => setPage(Math.max(1, safePage - 1))}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={safePage >= tablePages}
                  onClick={() => setPage(Math.min(tablePages, safePage + 1))}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
            </>
          )}
        </div>
      </div>
    </DashboardShell>
  );
}
