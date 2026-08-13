"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  exportReportsCsv,
  fetchGroups,
  fetchReports,
  fmtBytes,
  fmtPercent,
  fmtRelative,
  fmtUptime,
  groupMachines,
  groupOf,
  MachineSortKey,
  machineMac,
  maxDiskPercent,
  networkTotalBytes,
  SortOrder,
  sortMachines,
} from "@/lib/api";
import { DashboardShell } from "@/components/dashboard/shell";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const inputClass =
  "w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2";

type RangeKey = "daily" | "weekly" | "monthly" | "yearly" | "custom";

const RANGE_LABELS: { key: RangeKey; label: string }[] = [
  { key: "daily", label: "Daily" },
  { key: "weekly", label: "Weekly" },
  { key: "monthly", label: "Monthly" },
  { key: "yearly", label: "Yearly" },
  { key: "custom", label: "Custom" },
];

/** Start of the current UTC day as a unix timestamp. */
function startOfTodayUtc(): number {
  const d = new Date();
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) / 1000;
}

function startOfUtcDay(ts: number): number {
  const d = new Date(ts * 1000);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) / 1000;
}

/** Range boundaries (unix seconds) for a preset relative to now. */
function rangeForPreset(key: RangeKey): { fromTs?: number; toTs?: number } {
  const now = Math.floor(Date.now() / 1000);
  const todayStart = startOfTodayUtc();
  const day = 86400;
  const nowDate = new Date(now * 1000);
  switch (key) {
    case "daily":
      return { fromTs: todayStart, toTs: now };
    case "weekly": {
      const dow = nowDate.getUTCDay(); // 0 = Sun
      const daysSinceMonday = (dow + 6) % 7;
      const mondayStart = startOfUtcDay(todayStart - daysSinceMonday * day);
      return { fromTs: mondayStart, toTs: now };
    }
    case "monthly": {
      const monthStart = Date.UTC(nowDate.getUTCFullYear(), nowDate.getUTCMonth(), 1) / 1000;
      return { fromTs: monthStart, toTs: now };
    }
    case "yearly": {
      const yearStart = Date.UTC(nowDate.getUTCFullYear(), 0, 1) / 1000;
      return { fromTs: yearStart, toTs: now };
    }
    case "custom":
    default:
      return {};
  }
}

function dateInputToTs(value: string, endOfDay: boolean): number | undefined {
  if (!value) return undefined;
  const d = new Date(value + (endOfDay ? "T23:59:59" : "T00:00:00"));
  const ts = d.getTime() / 1000;
  return Number.isFinite(ts) ? ts : undefined;
}

function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} fill="none" viewBox="0 0 24 24" aria-hidden>
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"
      />
    </svg>
  );
}

export function ReportExportPanel() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;

  const [range, setRange] = useState<RangeKey>("monthly");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [pcName, setPcName] = useState("");
  const [country, setCountry] = useState("");
  const [os, setOs] = useState("");
  const [groupId, setGroupId] = useState("");
  const [applied, setApplied] = useState<{
    range: RangeKey;
    fromTs?: number;
    toTs?: number;
    pcName: string;
    country: string;
    os: string;
    groupId: string;
  } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [sort, setSort] = useState<MachineSortKey>("last_seen");
  const [order, setOrder] = useState<SortOrder>("desc");

  const { data: groups = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: () => fetchGroups(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
  });

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["reports-export", applied],
    queryFn: () =>
      applied
        ? fetchReports(API_URL, apiToken ?? "", 500, {
            pcName: applied.pcName || undefined,
            country: applied.country || undefined,
            os: applied.os || undefined,
            fromTs: applied.fromTs,
            toTs: applied.toTs,
            groupId: applied.groupId || undefined,
          })
        : Promise.resolve({ total: 0, reports: [] }),
    enabled: !!apiToken && !!applied,
  });

  const machines = useMemo(() => {
    let list = groupMachines(data?.reports ?? []);
    if (applied?.groupId) {
      list = list.filter((m) => {
        const g = groupOf(m, groups);
        return !!g && g.id === applied.groupId;
      });
    }
    return sortMachines(list, sort, order);
  }, [data?.reports, applied, groups, sort, order]);

  const reports = data?.reports ?? [];
  const totalReports = data?.total ?? 0;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const presetRange =
      range === "custom"
        ? {}
        : rangeForPreset(range);
    const customFrom = dateInputToTs(fromDate, false);
    const customTo = dateInputToTs(toDate, true);
    setApplied({
      range,
      fromTs: range === "custom" ? customFrom : presetRange.fromTs,
      toTs: range === "custom" ? customTo : presetRange.toTs,
      pcName: pcName.trim(),
      country: country.trim(),
      os: os.trim(),
      groupId,
    });
    setExportError(null);
  }

  function onClear() {
    setRange("monthly");
    setFromDate("");
    setToDate("");
    setPcName("");
    setCountry("");
    setOs("");
    setGroupId("");
    setSort("last_seen");
    setOrder("desc");
    setApplied(null);
    setExportError(null);
  }

  async function onDownload() {
    if (!applied || !apiToken) return;
    setExporting(true);
    setExportError(null);
    try {
      const blob = await exportReportsCsv(API_URL, apiToken, {
        pcName: applied.pcName || undefined,
        country: applied.country || undefined,
        os: applied.os || undefined,
        fromTs: applied.fromTs,
        toTs: applied.toTs,
        groupId: applied.groupId || undefined,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `system-info-report-${Date.now()}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const rangeLabel =
    RANGE_LABELS.find((r) => r.key === applied?.range)?.label ?? "";

  return (
    <DashboardShell
      title="Report Export"
      nav="export"
      role={session?.user?.role}
      widthClass="w-80"
      subtitle="Generate a CSV report with all collected fields"
      sidebar={
        <form onSubmit={onSubmit} className="space-y-4 border-b border-slate-800 px-3 py-3">
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              Date range
            </p>
            <div className="grid grid-cols-2 gap-1.5">
              {RANGE_LABELS.map((r) => (
                <button
                  key={r.key}
                  type="button"
                  onClick={() => setRange(r.key)}
                  className={`rounded-lg px-2 py-1.5 text-xs font-medium transition ${
                    range === r.key
                      ? "bg-blue-600 text-white"
                      : "bg-slate-900 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
            {range === "custom" && (
              <div className="mt-3 space-y-3">
                <label className="block text-xs text-slate-400">
                  From
                  <input
                    type="date"
                    value={fromDate}
                    onChange={(e) => setFromDate(e.target.value)}
                    className={inputClass}
                  />
                </label>
                <label className="block text-xs text-slate-400">
                  To
                  <input
                    type="date"
                    value={toDate}
                    onChange={(e) => setToDate(e.target.value)}
                    className={inputClass}
                  />
                </label>
              </div>
            )}
          </div>

          <p className="pt-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Filters
          </p>
          <label className="block text-xs text-slate-400">
            PC name
            <input
              value={pcName}
              onChange={(e) => setPcName(e.target.value)}
              placeholder="Contains…"
              className={inputClass}
            />
          </label>
          <label className="block text-xs text-slate-400">
            Country
            <input
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              placeholder="Name or code"
              className={inputClass}
            />
          </label>
          <label className="block text-xs text-slate-400">
            OS
            <input
              value={os}
              onChange={(e) => setOs(e.target.value)}
              placeholder="Darwin, Windows…"
              className={inputClass}
            />
          </label>
          <label className="block text-xs text-slate-400">
            Group
            <select
              value={groupId}
              onChange={(e) => setGroupId(e.target.value)}
              className={inputClass}
            >
              <option value="">All groups</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </label>

          <p className="pt-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Sort by
          </p>
          <label className="block text-xs text-slate-400">
            Metric
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as MachineSortKey)}
              className={inputClass}
            >
              <option value="last_seen">Last seen</option>
              <option value="cpu">Most CPU %</option>
              <option value="ram">Most RAM %</option>
              <option value="disk">Most disk used %</option>
              <option value="ssd">Most SSD capacity</option>
              <option value="hdd">Most HDD capacity</option>
              <option value="network">Most network usage</option>
            </select>
          </label>
          <label className="block text-xs text-slate-400">
            Order
            <select
              value={order}
              onChange={(e) => setOrder(e.target.value as SortOrder)}
              className={inputClass}
            >
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </label>

          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              className="flex-1 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500"
            >
              Generate
            </button>
            <button
              type="button"
              onClick={onClear}
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-200 hover:bg-slate-800"
            >
              Clear
            </button>
          </div>
        </form>
      }
      header={
        <div className="border-b border-slate-200 bg-white/80 px-6 py-4 backdrop-blur">
          {applied ? (
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-slate-900">
                  {rangeLabel} report
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  {applied.fromTs
                    ? new Date(applied.fromTs * 1000).toLocaleString()
                    : "Start of data"}{" "}
                  →{" "}
                  {applied.toTs
                    ? new Date(applied.toTs * 1000).toLocaleString()
                    : "Now"}
                  <span className="mx-1.5 text-slate-300">·</span>
                  {totalReports} report{totalReports === 1 ? "" : "s"} ·{" "}
                  {machines.length} machine{machines.length === 1 ? "" : "s"}
                </p>
              </div>
            </div>
          ) : (
            <div>
              <h2 className="text-xl font-semibold text-slate-900">
                Generate a report
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Pick a date range (daily / weekly / monthly / yearly / custom),
                add filters, then Generate to preview and download as CSV.
              </p>
            </div>
          )}
        </div>
      }
    >
      <div className="flex-1 overflow-y-auto px-6 py-6">
          {exportError && (
            <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              Export failed: {exportError}
            </div>
          )}
          {isError && (
            <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              Failed to load reports from {API_URL}.
            </div>
          )}
          {!applied ? (
            <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/60 text-sm text-slate-500">
              No report generated yet.
            </div>
          ) : isLoading ? (
            <div className="flex h-64 flex-col items-center justify-center gap-4 rounded-2xl border border-slate-200 bg-white">
              <span className="text-emerald-500">
                <Spinner className="h-9 w-9" />
              </span>
              <div className="text-center">
                <p className="text-sm font-medium text-slate-700">
                  Generating report…
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Fetching matching reports from the API
                </p>
              </div>
            </div>
          ) : (
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm shadow-slate-200/60">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
                <div>
                  <h3 className="text-sm font-medium text-slate-700">Preview</h3>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {reports.length} report{reports.length === 1 ? "" : "s"} loaded
                    (up to 500) · CSV includes every field from the full report set
                  </p>
                </div>
                <button
                  type="button"
                  onClick={onDownload}
                  disabled={exporting || isFetching}
                  className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
                >
                  {exporting ? (
                    <>
                      <Spinner className="h-4 w-4" />
                      Exporting…
                    </>
                  ) : (
                    "Download CSV"
                  )}
                </button>
              </div>
              {machines.length === 0 ? (
                <p className="px-4 py-10 text-center text-sm text-slate-500">
                  No PCs match these filters.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[1400px] text-left text-sm">
                  <thead className="border-b bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3">PC</th>
                      <th className="px-4 py-3">IP</th>
                      <th className="px-4 py-3">MAC</th>
                      <th className="px-4 py-3">Last seen</th>
                      <th className="px-4 py-3">Reports</th>
                      <th className="px-4 py-3">CPU %</th>
                      <th className="px-4 py-3">CPU brand</th>
                      <th className="px-4 py-3">CPU model</th>
                      <th className="px-4 py-3">Cores</th>
                      <th className="px-4 py-3">RAM %</th>
                      <th className="px-4 py-3">RAM total</th>
                      <th className="px-4 py-3">RAM used</th>
                      <th className="px-4 py-3">RAM free</th>
                      <th className="px-4 py-3">RAM speed</th>
                      <th className="px-4 py-3">RAM type</th>
                      <th className="px-4 py-3">Swap</th>
                      <th className="px-4 py-3">Disk %</th>
                      <th className="px-4 py-3">SSD brand</th>
                      <th className="px-4 py-3">HDD brand</th>
                      <th className="px-4 py-3">Disk used</th>
                      <th className="px-4 py-3">Disk free</th>
                      <th className="px-4 py-3">Net total</th>
                      <th className="px-4 py-3">Uptime</th>
                      <th className="px-4 py-3">OS</th>
                      <th className="px-4 py-3">Country</th>
                      <th className="px-4 py-3">Security</th>
                      <th className="px-4 py-3">Printers</th>
                      <th className="px-4 py-3">Total prints</th>
                      <th className="px-4 py-3">Battery</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {machines.map((m) => {
                      const r = m.latest;
                      const res = r.resources;
                      const dis = r.disk;
                      const up = r.uptime;
                      const sec = r.security;
                      const prv = r.printers;
                      const bat = res?.battery;
                      const totalDisk = dis?.devices?.reduce((s, d) => s + (d.total ?? 0), 0) ?? 0;
                      const usedDisk = dis?.devices?.reduce((s, d) => s + (d.used ?? 0), 0) ?? 0;
                      const freeDisk = dis?.devices?.reduce((s, d) => s + (d.free ?? 0), 0) ?? 0;
                      const printerCount = (prv?.usb?.length ?? 0) + (prv?.network?.length ?? 0) + (prv?.other?.length ?? 0);
                      const printTotal = (prv?.usb ?? []).reduce((s, p) => s + (p.print_count ?? 0), 0) +
                        (prv?.network ?? []).reduce((s, p) => s + (p.print_count ?? 0), 0) +
                        (prv?.other ?? []).reduce((s, p) => s + (p.print_count ?? 0), 0);
                      const healthDisks = r.health?.disks ?? [];
                      const ssdBrands = [...new Set(healthDisks.filter((d) => d.media_type === "ssd").map((d) => d.brand).filter(Boolean))]
                        .join(", ") || "—";
                      const hddBrands = [...new Set(healthDisks.filter((d) => d.media_type === "hdd").map((d) => d.brand).filter(Boolean))]
                        .join(", ") || "—";
                      return (
                        <tr key={m.key} className="hover:bg-slate-50/80">
                          <td className="px-4 py-3 font-medium text-slate-900">
                            {m.name}
                          </td>
                          <td className="px-4 py-3 font-mono text-slate-600">
                            {r.private_ip ?? "—"}
                          </td>
                          <td className="px-4 py-3 font-mono text-slate-600">
                            {machineMac(r) ?? "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {fmtRelative(r.created_at)}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {m.reports.length}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {fmtPercent(res?.cpu_percent)}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {res?.cpu_brand || "—"}
                          </td>
                          <td className="max-w-[180px] truncate px-4 py-3 text-slate-600" title={r.os?.processor}>
                            {r.os?.processor || "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {res?.cpu_count != null ? `${res.cpu_count} (${res.cpu_count_physical ?? "?"} phys)` : "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {fmtPercent(res?.ram_percent)}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {fmtBytes(res?.ram_total)}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {fmtBytes(res?.ram_used)}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {fmtBytes(res?.ram_free)}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {res?.ram_speed_mhz != null ? `${res.ram_speed_mhz} MHz` : "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {res?.ram_type || "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {fmtBytes(res?.swap_total)}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {fmtPercent(maxDiskPercent(r))}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {ssdBrands}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {hddBrands}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {fmtBytes(usedDisk)}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {fmtBytes(freeDisk)}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {fmtBytes(networkTotalBytes(r))}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {fmtUptime(up?.uptime_seconds)}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {r.os?.system || "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {r.location?.country || "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {sec
                              ? Array.isArray(sec)
                                ? sec.map((s: any) => s.name).join(", ")
                                : (sec as any).installed?.map((s: any) => s.name).join(", ") || "—"
                              : "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {printerCount || "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {printTotal > 0 ? printTotal.toLocaleString() : "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-600" title={bat ? `Plugged: ${bat.power_plugged}` : undefined}>
                            {bat ? `${fmtPercent(bat.percent)}` : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                </div>
              )}
              {isFetching && (
                <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-400">
                  Refreshing…
                </p>
              )}
            </div>
          )}
        </div>
    </DashboardShell>
  );
}
