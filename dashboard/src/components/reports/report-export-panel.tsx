"use client";

import { FormEvent, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  exportReportsCsv,
  fetchGroups,
  fetchPrintJobsByPc,
  fetchReports,
  fetchSubCategories,
  fmtBytes,
  fmtPercent,
  fmtRelative,
  fmtUptime,
  groupMachines,
  groupOf,
  MachineSortKey,
  machineEmails,
  machineMac,
  maxDiskPercent,
  networkTotalBytes,
  PrintJobsByPcRow,
  Report,
  SortOrder,
  sortMachines,
  subCategoryOf,
  cpuDisplayName,
} from "@/lib/api";
import { downloadExportPdf } from "@/lib/export-pdf";
import { DashboardShell } from "@/components/dashboard/shell";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const inputClass =
  "w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2";

const EMPTY_PRINT_PCS: PrintJobsByPcRow[] = [];

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

function csvCell(value: string | number | null | undefined): string {
  const s = String(value ?? "");
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function printRangeForMachine(
  m: { deviceId: string | null; name: string; latest: Report },
  pcs: PrintJobsByPcRow[],
): { jobs: number; pages: number } {
  const did = m.deviceId || m.latest.device_id;
  if (did) {
    const hit = pcs.find((p) => p.device_id === did);
    if (hit) return { jobs: hit.jobs, pages: hit.pages };
  }
  const names = new Set(
    [m.name, m.latest.pc_name, m.latest.os?.hostname]
      .filter(Boolean)
      .map((n) => String(n).toLowerCase()),
  );
  const hit = pcs.find((p) => p.pc_name && names.has(p.pc_name.toLowerCase()));
  if (hit) return { jobs: hit.jobs, pages: hit.pages };
  return { jobs: 0, pages: 0 };
}

function fmtSecurity(sec: Report["security"] | unknown): string {
  if (!sec) return "—";
  if (Array.isArray(sec)) {
    return (
      (sec as { name?: string }[])
        .map((s) => s.name)
        .filter(Boolean)
        .join(", ") || "—"
    );
  }
  const installed = (sec as Report["security"])?.installed;
  if (!installed?.length) return "—";
  return installed
    .map((s) => {
      if (s.expired) return `${s.name} (Expired)`;
      if (s.expiry_date) {
        const days = s.days_remaining ?? 0;
        return `${s.name} (${days}d remaining, ${s.expiry_date})`;
      }
      return s.name;
    })
    .join(", ");
}

function fmtRangeSpan(fromTs?: number, toTs?: number): string {
  const fmt = (ts?: number) =>
    ts == null ? "" : new Date(ts * 1000).toLocaleString();
  if (fromTs == null && toTs == null) return "all dates";
  return `${fmt(fromTs) || "..."} - ${fmt(toTs) || "now"}`;
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
  const [subCategoryId, setSubCategoryId] = useState("");
  const [diskHealth, setDiskHealth] = useState<"" | "healthy" | "problem">("");
  const [battery, setBattery] = useState<"" | "has" | "none">("");
  const [batteryHealthMin, setBatteryHealthMin] = useState("");
  const [applied, setApplied] = useState<{
    range: RangeKey;
    fromTs?: number;
    toTs?: number;
    pcName: string;
    country: string;
    os: string;
    groupId: string;
    subCategoryId: string;
    diskHealth: "" | "healthy" | "problem";
    battery: "" | "has" | "none";
    batteryHealthMin: number;
  } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [sort, setSort] = useState<MachineSortKey>("last_seen");
  const [order, setOrder] = useState<SortOrder>("desc");

  const { data: groups = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: () => fetchGroups(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
  });

  const { data: subCategories = [] } = useQuery({
    queryKey: ["sub-categories"],
    queryFn: () => fetchSubCategories(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
  });

  const { data, isLoading, isError, isFetching } = useQuery({
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
            subCategoryId: applied.subCategoryId || undefined,
            diskHealth: applied.diskHealth || undefined,
            battery: applied.battery || undefined,
            batteryHealthMin: applied.batteryHealthMin || undefined,
          })
        : Promise.resolve({ total: 0, reports: [] }),
    enabled: !!apiToken && !!applied,
  });

  const { data: printByPc } = useQuery({
    queryKey: [
      "print-jobs-by-pc",
      applied?.fromTs,
      applied?.toTs,
      applied?.groupId,
      applied?.pcName,
    ],
    queryFn: () =>
      fetchPrintJobsByPc(API_URL, apiToken ?? "", {
        fromTs: applied?.fromTs,
        toTs: applied?.toTs,
        groupId: applied?.groupId || undefined,
        pcName: applied?.pcName || undefined,
      }),
    enabled: !!apiToken && !!applied,
  });

  const machines = useMemo(() => {
    let list = groupMachines(data?.reports ?? []);
    if (applied?.groupId) {
      list = list.filter((m) => {
        const g = groupOf(m, groups);
        if (g && g.id === applied.groupId) return true;
        const s = subCategoryOf(m, subCategories);
        return (
          !!s &&
          s.group_ids.includes(applied.groupId) &&
          groups.some((gr) => gr.id === applied.groupId)
        );
      });
    }
    if (applied?.subCategoryId) {
      list = list.filter((m) => {
        const s = subCategoryOf(m, subCategories);
        return !!s && s.id === applied.subCategoryId;
      });
    }
    if (applied != null && (applied.diskHealth || applied.battery || applied.batteryHealthMin > 0)) {
      const a = applied;
      list = list.filter((m) => {
        const r = m.latest;
        const healthDisks = r.health?.disks ?? [];
        const problemDisks = healthDisks.filter(
          (d) => d.health === "warning" || d.health === "fail",
        );
        if (a.diskHealth === "healthy" && problemDisks.length > 0) return false;
        if (a.diskHealth === "problem" && problemDisks.length === 0) return false;

        const hasBattery = r.health?.battery != null;
        if (a.battery === "has" && !hasBattery) return false;
        if (a.battery === "none" && hasBattery) return false;
        const batHealth = r.health?.battery?.health_percent;
        if (a.batteryHealthMin > 0) {
          if (!hasBattery || batHealth == null || batHealth < a.batteryHealthMin)
            return false;
        }
        return true;
      });
    }
    return sortMachines(list, sort, order);
  }, [data?.reports, applied, groups, subCategories, sort, order]);

  const reports = data?.reports ?? [];
  const totalReports = data?.total ?? 0;
  const printPcs = printByPc?.pcs ?? EMPTY_PRINT_PCS;

  const printPreviewRows = useMemo(() => {
    const rows = machines.map((m) => {
      const st = printRangeForMachine(m, printPcs);
      return {
        name: m.name,
        deviceId: m.deviceId ?? "",
        jobs: st.jobs,
        pages: st.pages,
      };
    });
    const seen = new Set(
      rows.flatMap((r) => [r.deviceId, r.name.toLowerCase()].filter(Boolean)),
    );
    for (const p of printPcs) {
      const did = p.device_id ?? "";
      const name = p.pc_name ?? "Unknown PC";
      if ((did && seen.has(did)) || seen.has(name.toLowerCase())) continue;
      rows.push({ name, deviceId: did, jobs: p.jobs, pages: p.pages });
    }
    return rows;
  }, [machines, printPcs]);

  const printTotals = useMemo(() => {
    const jobs = printByPc?.total_jobs ?? printPreviewRows.reduce((s, r) => s + r.jobs, 0);
    const pages = printByPc?.total_pages ?? printPreviewRows.reduce((s, r) => s + r.pages, 0);
    const withJobs = printPreviewRows.filter((r) => r.jobs > 0);
    const ranked = (withJobs.length ? withJobs : printPreviewRows).slice();
    const maxCount = ranked.length ? Math.max(...ranked.map((r) => r.jobs)) : 0;
    const minCount = ranked.length ? Math.min(...ranked.map((r) => r.jobs)) : 0;
    return {
      jobs,
      pages,
      maxCount,
      minCount,
      maxPcs: ranked.filter((r) => r.jobs === maxCount).map((r) => r.name),
      minPcs: ranked.filter((r) => r.jobs === minCount).map((r) => r.name),
    };
  }, [printByPc, printPreviewRows]);

  const lifetimePrintRows = useMemo(() => {
    return machines
      .map((m) => {
        const prv = m.latest.printers;
        const printerCount =
          (prv?.usb?.length ?? 0) + (prv?.network?.length ?? 0) + (prv?.other?.length ?? 0);
        const total =
          (prv?.usb ?? []).reduce((s, p) => s + (p.print_count ?? 0), 0) +
          (prv?.network ?? []).reduce((s, p) => s + (p.print_count ?? 0), 0) +
          (prv?.other ?? []).reduce((s, p) => s + (p.print_count ?? 0), 0);
        return { name: m.name, deviceId: m.deviceId ?? "", printers: printerCount, total };
      })
      .filter((r) => r.total > 0 || r.printers > 0)
      .sort((a, b) => b.total - a.total);
  }, [machines]);

  const totalLifetimePrints = useMemo(
    () => lifetimePrintRows.reduce((s, r) => s + r.total, 0),
    [lifetimePrintRows],
  );

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
      subCategoryId,
      diskHealth,
      battery,
      batteryHealthMin: Number(batteryHealthMin) || 0,
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
    setSubCategoryId("");
    setDiskHealth("");
    setBattery("");
    setBatteryHealthMin("");
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
        subCategoryId: applied.subCategoryId || undefined,
        diskHealth: applied.diskHealth || undefined,
        battery: applied.battery || undefined,
        batteryHealthMin: applied.batteryHealthMin || undefined,
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

  function onDownloadPrints() {
    if (!applied) return;
    const header = ["pc_name", "device_id", "jobs", "pages"];
    const lines = [
      header.join(","),
      ...printPreviewRows.map((r) =>
        [csvCell(r.name), csvCell(r.deviceId), r.jobs, r.pages].join(","),
      ),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `print-totals-${applied.range}-${Date.now()}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function onDownloadTotalPrints() {
    if (!applied) return;
    const header = ["pc_name", "device_id", "printers", "total_prints"];
    const lines = [
      header.join(","),
      ...lifetimePrintRows.map((r) =>
        [csvCell(r.name), csvCell(r.deviceId), r.printers, r.total].join(","),
      ),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `total-print-count-${applied.range}-${Date.now()}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function onDownloadPdf() {
    if (!applied) return;
    setExportingPdf(true);
    setExportError(null);
    try {
      const groupName = groups.find((g) => g.id === applied.groupId)?.name;
      const subName = subCategories.find((s) => s.id === applied.subCategoryId)?.name;
      const filters: string[] = [];
      if (applied.pcName) filters.push(`PC: ${applied.pcName}`);
      if (applied.country) filters.push(`Country: ${applied.country}`);
      if (applied.os) filters.push(`OS: ${applied.os}`);
      if (applied.groupId) filters.push(`Group: ${groupName || applied.groupId}`);
      if (applied.subCategoryId)
        filters.push(`Sub-category: ${subName || applied.subCategoryId}`);
      if (applied.diskHealth) filters.push(`Disk: ${applied.diskHealth}`);
      if (applied.battery) filters.push(`Battery: ${applied.battery}`);
      if (applied.batteryHealthMin > 0)
        filters.push(`Min battery health: ${applied.batteryHealthMin}%`);

      const overviewBody = machines.map((m) => {
        const r = m.latest;
        const res = r.resources;
        const prv = r.printers;
        const printerCount =
          (prv?.usb?.length ?? 0) +
          (prv?.network?.length ?? 0) +
          (prv?.other?.length ?? 0);
        const printTotal =
          (prv?.usb ?? []).reduce((s, p) => s + (p.print_count ?? 0), 0) +
          (prv?.network ?? []).reduce((s, p) => s + (p.print_count ?? 0), 0) +
          (prv?.other ?? []).reduce((s, p) => s + (p.print_count ?? 0), 0);
        const rangePrints = printRangeForMachine(m, printPcs);
        return [
          m.name,
          r.private_ip ?? "-",
          machineMac(r) ?? "-",
          fmtRelative(r.created_at),
          String(m.reports.length),
          fmtPercent(res?.cpu_percent),
          fmtPercent(res?.ram_percent),
          fmtPercent(maxDiskPercent(r)),
          fmtBytes(networkTotalBytes(r)),
          fmtUptime(r.uptime?.uptime_seconds),
          r.os?.system || "-",
          r.location?.country || "-",
          printerCount ? String(printerCount) : "-",
          printTotal > 0 ? printTotal.toLocaleString() : "-",
          rangePrints.jobs.toLocaleString(),
          rangePrints.pages.toLocaleString(),
        ];
      });

      const hardwareBody = machines.map((m) => {
        const r = m.latest;
        const res = r.resources;
        const dis = r.disk;
        const usedDisk = dis?.devices?.reduce((s, d) => s + (d.used ?? 0), 0) ?? 0;
        const freeDisk = dis?.devices?.reduce((s, d) => s + (d.free ?? 0), 0) ?? 0;
        const healthDisks = r.health?.disks ?? [];
        const ssdBrands =
          [...new Set(healthDisks.filter((d) => d.media_type === "ssd").map((d) => d.brand).filter(Boolean))].join(", ") ||
          "-";
        const hddBrands =
          [...new Set(healthDisks.filter((d) => d.media_type === "hdd").map((d) => d.brand).filter(Boolean))].join(", ") ||
          "-";
        const emails = machineEmails(r)
          .map((a) => a.email)
          .filter(Boolean)
          .join(", ");
        return [
          m.name,
          res?.cpu_brand || "-",
          cpuDisplayName(r) || "-",
          res?.cpu_count != null
            ? `${res.cpu_count} (${res.cpu_count_physical ?? "?"} phys)`
            : "-",
          fmtBytes(res?.ram_total),
          res?.ram_type || "-",
          res?.ram_speed_mhz != null ? `${res.ram_speed_mhz} MHz` : "-",
          ssdBrands,
          hddBrands,
          fmtBytes(usedDisk),
          fmtBytes(freeDisk),
          fmtSecurity(r.security),
          r.resources?.battery ? fmtPercent(r.resources.battery.percent) : "-",
          emails || "-",
        ];
      });

      await downloadExportPdf({
        filename: `system-info-report-${applied.range}-${Date.now()}.pdf`,
        title: "System Info Report",
        subtitle: [
          `${rangeLabel || "Custom"} · ${fmtRangeSpan(applied.fromTs, applied.toTs)}`,
          `${machines.length} PC${machines.length === 1 ? "" : "s"} · ${reports.length} report snapshot${reports.length === 1 ? "" : "s"}`,
          filters.length ? `Filters: ${filters.join(" · ")}` : "Filters: none",
          `Generated ${new Date().toLocaleString()}`,
        ],
        stats: [
          { label: "Total prints", value: totalLifetimePrints.toLocaleString() },
          { label: "Prints in range", value: printTotals.jobs.toLocaleString() },
          { label: "Pages in range", value: printTotals.pages.toLocaleString() },
          {
            label: "Most prints",
            value: printTotals.maxPcs.length
              ? `${printTotals.maxPcs.join(", ")} (${printTotals.maxCount})`
              : "-",
          },
          {
            label: "Least prints",
            value: printTotals.minPcs.length
              ? `${printTotals.minPcs.join(", ")} (${printTotals.minCount})`
              : "-",
          },
        ],
        tables: [
          {
            title: "PCs - overview and prints",
            head: [
              "PC",
              "IP",
              "MAC",
              "Last seen",
              "Reports",
              "CPU %",
              "RAM %",
              "Disk %",
              "Net",
              "Uptime",
              "OS",
              "Country",
              "Printers",
              "Lifetime prints",
              "Prints in range",
              "Pages in range",
            ],
            body: overviewBody,
          },
          {
            title: "PCs - hardware",
            head: [
              "PC",
              "CPU brand",
              "CPU model",
              "Cores",
              "RAM total",
              "RAM type",
              "RAM speed",
              "SSD",
              "HDD",
              "Disk used",
              "Disk free",
              "Security",
              "Battery",
              "Emails",
            ],
            body: hardwareBody,
          },
          {
            title: "Print totals by PC",
            head: ["PC", "Device ID", "Jobs", "Pages"],
            body: printPreviewRows.map((r) => [
              r.name,
              r.deviceId || "-",
              String(r.jobs),
              String(r.pages),
            ]),
          },
          {
            title: "Total print count by PC",
            head: ["PC", "Device ID", "Printers", "Total prints"],
            body: lifetimePrintRows.map((r) => [
              r.name,
              r.deviceId || "-",
              r.printers ? String(r.printers) : "-",
              r.total > 0 ? r.total.toLocaleString() : "-",
            ]),
          },
        ],
      });
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "PDF export failed");
    } finally {
      setExportingPdf(false);
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
      subtitle="Generate a CSV or PDF report with all collected fields"
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
          <label className="block text-xs text-slate-400">
            Sub-category
            <select
              value={subCategoryId}
              onChange={(e) => setSubCategoryId(e.target.value)}
              className={inputClass}
            >
              <option value="">All sub-categories</option>
              {subCategories
                .filter((s) => !groupId || s.group_ids.includes(groupId))
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
            </select>
          </label>

          <div>
            <p className="mb-2 pt-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              Health
            </p>
            <label className="block text-xs text-slate-400">
              Disk health
              <select
                value={diskHealth}
                onChange={(e) =>
                  setDiskHealth(e.target.value as "" | "healthy" | "problem")
                }
                className={inputClass}
              >
                <option value="">Any</option>
                <option value="healthy">All healthy</option>
                <option value="problem">Has warning / failing</option>
              </select>
            </label>
            <label className="mt-3 block text-xs text-slate-400">
              Battery
              <select
                value={battery}
                onChange={(e) => setBattery(e.target.value as "" | "has" | "none")}
                className={inputClass}
              >
                <option value="">Any</option>
                <option value="has">Has battery</option>
                <option value="none">No battery</option>
              </select>
            </label>
            <label className="mt-3 block text-xs text-slate-400">
              Min battery health %
              <input
                type="number"
                min={0}
                max={100}
                value={batteryHealthMin}
                onChange={(e) => setBatteryHealthMin(e.target.value)}
                className={inputClass}
              />
            </label>
          </div>

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
                add filters, then Generate to preview PC-wise reports and print
                totals, then download as CSV or PDF.
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
                    (up to 500) · {machines.length} PC{machines.length === 1 ? "" : "s"} ·
                    prints in range from completed jobs · CSV has every field ·
                    PDF is the PC-wise preview plus print totals
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                <button
                  type="button"
                  onClick={onDownloadPrints}
                  disabled={isFetching || exporting || exportingPdf}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                >
                  Download prints CSV
                </button>
                <button
                  type="button"
                  onClick={onDownloadTotalPrints}
                  disabled={isFetching || exporting || exportingPdf}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                >
                  Download total prints CSV
                </button>
                <button
                  type="button"
                  onClick={onDownload}
                  disabled={exporting || exportingPdf || isFetching}
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
                <button
                  type="button"
                  onClick={onDownloadPdf}
                  disabled={exportingPdf || exporting || isFetching || (machines.length === 0 && printPreviewRows.length === 0)}
                  className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60"
                >
                  {exportingPdf ? (
                    <>
                      <Spinner className="h-4 w-4" />
                      Building PDF…
                    </>
                  ) : (
                    "Download PDF"
                  )}
                </button>
                </div>
              </div>
              {printPreviewRows.length > 0 && (
                <div className="grid gap-3 border-b border-slate-100 px-4 py-3 sm:grid-cols-2 lg:grid-cols-5">
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      Total prints
                    </p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">
                      {totalLifetimePrints.toLocaleString()}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      lifetime printer counter · all PCs
                    </p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      Prints in range
                    </p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">
                      {printTotals.jobs.toLocaleString()}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      completed jobs · {rangeLabel.toLowerCase() || "selected range"}
                    </p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      Pages in range
                    </p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">
                      {printTotals.pages.toLocaleString()}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">sum of job page counts</p>
                  </div>
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
                      Most prints
                    </p>
                    <p className="mt-1 truncate text-sm font-semibold text-slate-900">
                      {printTotals.maxPcs.length ? printTotals.maxPcs.join(", ") : "—"}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-600">
                      {printTotals.maxPcs.length
                        ? `${printTotals.maxCount} job${printTotals.maxCount === 1 ? "" : "s"}`
                        : "no jobs in range"}
                    </p>
                  </div>
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-800">
                      Least prints
                    </p>
                    <p className="mt-1 truncate text-sm font-semibold text-slate-900">
                      {printTotals.minPcs.length ? printTotals.minPcs.join(", ") : "—"}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-600">
                      {printTotals.minPcs.length
                        ? `${printTotals.minCount} job${printTotals.minCount === 1 ? "" : "s"}`
                        : "no jobs in range"}
                    </p>
                  </div>
                </div>
              )}
              {machines.length === 0 ? (
                <p className="px-4 py-10 text-center text-sm text-slate-500">
                  No PCs match these filters.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[1600px] text-left text-sm">
                  <thead className="border-b bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3">PC</th>
                      <th className="px-4 py-3">IP</th>
                      <th className="px-4 py-3">MAC</th>
                      <th className="px-4 py-3">Emails</th>
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
                      <th className="px-4 py-3">Lifetime prints</th>
                      <th className="px-4 py-3">Prints in range</th>
                      <th className="px-4 py-3">Pages in range</th>
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
                      const rangePrints = printRangeForMachine(m, printPcs);
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
                          <td className="max-w-[220px] truncate px-4 py-3 text-slate-600" title={machineEmails(r).map((a) => a.email).filter(Boolean).join(", ")}>
                            {machineEmails(r).length
                              ? machineEmails(r).map((a) => a.email).filter(Boolean).join(", ")
                              : "—"}
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
                          <td className="max-w-[180px] truncate px-4 py-3 text-slate-600" title={cpuDisplayName(r) ?? undefined}>
                            {cpuDisplayName(r) || "—"}
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
                            {fmtSecurity(sec)}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {printerCount || "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {printTotal > 0 ? printTotal.toLocaleString() : "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {rangePrints.jobs.toLocaleString()}
                          </td>
                          <td className="px-4 py-3 text-slate-600">
                            {rangePrints.pages.toLocaleString()}
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
