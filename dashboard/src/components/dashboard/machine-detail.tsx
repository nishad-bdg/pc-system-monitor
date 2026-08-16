"use client";

import { useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import {
  fmtBatteryTime,
  fmtBytes,
  fmtPercent,
  fmtRate,
  fmtRelative,
  fmtTime,
  fmtUptime,
  formatUtcDayBd,
  clientLabel,
  EmailAccountInfo,
  MachineSummary,
  machineEmails,
  machineMac,
  networkTotalBytes,
  Report,
  fmtAppVersion,
} from "@/lib/api";
import { StatusDot } from "./status-dot";
import { useRealtime } from "../realtime-provider";
import type { LiveMetricsSample } from "../realtime-provider";
import { RemoteActions } from "./remote-actions";
import { isHighLiveLoad } from "./load-warning-badge";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export function MachineDetail({ machine }: { machine: MachineSummary }) {
  const host = machine.latest;
  const { isOnline, lastSeenFor, metricsFor } = useRealtime();
  const liveOnline = isOnline(machine.deviceId) ?? host.online;
  const liveLastSeen = lastSeenFor(machine.deviceId, host.last_seen);
  const live = metricsFor(machine.deviceId);
  const [tab, setTab] = useState<
    | "summary"
    | "overview"
    | "printers"
    | "uptime"
    | "storage"
    | "health"
    | "emails"
  >("summary");
  const timeSeries = machine.reports.map((r) => ({
    time: fmtTime(r.created_at),
    cpu: r.resources?.cpu_percent ?? 0,
    ram: r.resources?.ram_percent ?? 0,
    swap: r.resources?.swap_percent ?? 0,
  }));
  const bandwidthSeries = machine.reports.map((r) => ({
    time: fmtTime(r.created_at),
    upload: (r.network?.send_rate_bps ?? 0) / 1024,
    download: (r.network?.recv_rate_bps ?? 0) / 1024,
  }));

  const hasDisk =
    (host.disk?.devices?.length ?? 0) > 0 ||
    (host.disk?.partitions?.length ?? 0) > 0;

  const ramTotal = live?.ram_total ?? host.resources?.ram_total;
  const ramAvailable = host.resources?.ram_available;
  const ramUsedBytes =
    live?.ram_used ??
    (ramTotal != null && ramAvailable != null
      ? Math.max(0, ramTotal - ramAvailable)
      : (host.resources?.ram_used ?? 0));
  const cpuPercent = live?.cpu_percent ?? host.resources?.cpu_percent;
  const ramPercent = live?.ram_percent ?? host.resources?.ram_percent;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm shadow-slate-200/50">
        <span className="flex items-baseline gap-1.5 text-xs">
          <span className="font-medium text-slate-500">Status</span>
          <span className="font-medium text-slate-800">
            <StatusDot online={liveOnline} showLabel /> · Last seen{" "}
            {fmtRelative(liveLastSeen)}
          </span>
        </span>
        <IdentityItem label="Private IP" value={host.private_ip} />
        <IdentityItem label="Public IP" value={host.public_ip} />
        <IdentityItem label="MAC address" value={machineMac(host)} />
        <IdentityItem label="App version" value={fmtAppVersion(host.app_version)} />
        <div className="ml-auto">
          <RemoteActions
            apiUrl={API_URL}
            deviceId={machine.deviceId}
            pcName={machine.name}
            osSystem={host.os?.system}
          />
        </div>
      </div>
      <div className="flex gap-2 overflow-x-auto border-b border-slate-200">
        <button
          type="button"
          onClick={() => setTab("summary")}
          className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition ${
            tab === "summary"
              ? "border-blue-600 text-blue-700"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Summary
        </button>
        <button
          type="button"
          onClick={() => setTab("overview")}
          className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition ${
            tab === "overview"
              ? "border-blue-600 text-blue-700"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Overview
        </button>
        <button
          type="button"
          onClick={() => setTab("printers")}
          className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition ${
            tab === "printers"
              ? "border-blue-600 text-blue-700"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Printers
        </button>
        <button
          type="button"
          onClick={() => setTab("uptime")}
          className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition ${
            tab === "uptime"
              ? "border-blue-600 text-blue-700"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Uptime
        </button>
        <button
          type="button"
          onClick={() => setTab("storage")}
          className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition ${
            tab === "storage"
              ? "border-blue-600 text-blue-700"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Storage
        </button>
        <button
          type="button"
          onClick={() => setTab("health")}
          className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition ${
            tab === "health"
              ? "border-blue-600 text-blue-700"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Health
        </button>
        <button
          type="button"
          onClick={() => setTab("emails")}
          className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition ${
            tab === "emails"
              ? "border-blue-600 text-blue-700"
              : "border-transparent text-slate-500 hover:text-slate-800"
          }`}
        >
          Emails
        </button>
      </div>

      {tab === "printers" ? (
        host.printers ? (
          <PrintersTab printers={host.printers} />
        ) : (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
            No printer data for this PC yet.
          </div>
        )
      ) : tab === "uptime" ? (
        host.uptime ? (
          <UptimeSection uptime={host.uptime} />
        ) : (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
            No uptime data for this PC yet.
          </div>
        )
      ) : tab === "storage" ? (
        hasDisk ? (
          <StorageSection disk={host.disk!} />
        ) : (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
            No disk data for this PC yet.
          </div>
        )
      ) : tab === "health" ? (
        <HealthSection health={host.health ?? null} />
      ) : tab === "emails" ? (
        <EmailsTab accounts={machineEmails(host)} />
      ) : tab === "summary" ? (
        <SummarySection machine={machine} live={live} />
      ) : (
        <>
          {(host.resources || live) && (
            <div className="grid gap-4 sm:grid-cols-3">
              <StatCard
                label="CPU usage"
                value={fmtPercent(cpuPercent)}
                sub={`${host.resources?.cpu_count ?? "?"} cores · ${
                  host.resources?.cpu_freq_mhz ?? "?"
                } MHz`}
                accent
                live={live != null}
                warn={isHighLiveLoad(live?.cpu_percent)}
              />
              <StatCard
                label="Memory (RAM)"
                value={fmtPercent(ramPercent)}
                sub={`${fmtBytes(ramUsedBytes)} / ${fmtBytes(ramTotal)}`}
                live={live != null}
                warn={isHighLiveLoad(live?.ram_percent)}
              />
              <StatCard
                label="Swap"
                value={fmtPercent(host.resources?.swap_percent)}
                sub={`${fmtBytes(host.resources?.swap_used)} / ${fmtBytes(
                  host.resources?.swap_total,
                )}`}
              />
              {host.resources?.battery && (
                <StatCard
                  label="Battery"
                  value={fmtPercent(host.resources.battery.percent)}
                  sub={
                    host.resources.battery.status === "charging"
                      ? `Charging · ${fmtBatteryTime(
                          host.resources.battery.seconds_left,
                        )} to full`
                      : host.resources.battery.status === "full"
                        ? "Fully charged · plugged in"
                        : host.resources.battery.status === "discharging"
                          ? `On battery · ${fmtBatteryTime(
                              host.resources.battery.seconds_left,
                            )} remaining`
                          : host.resources.battery.power_plugged
                            ? "Plugged in"
                            : fmtBatteryTime(host.resources.battery.seconds_left) +
                              " remaining"
                  }
                  accent
                />
              )}
            </div>
          )}

          {host.uptime && <UptimeState uptime={host.uptime} />}

          <div className="grid gap-4 lg:grid-cols-2">
            {host.location && (
              <InfoBlock title="Location">
                {host.location.city ?? "—"}, {host.location.region ?? "—"},{" "}
                {host.location.country ?? "—"} ({host.location.country_code ?? "—"})
                <span className="mx-1 text-slate-300">·</span>
                ISP: {host.location.isp ?? "—"}
              </InfoBlock>
            )}
            {host.os && (
              <InfoBlock title="Machine">
                {host.os.system ?? "—"} {host.os.release ?? "—"} ·{" "}
                {host.os.machine ?? "—"} · {host.os.platform_detail ?? "—"}
                {fmtAppVersion(host.app_version)
                  ? ` · Reporter ${fmtAppVersion(host.app_version)}`
                  : ""}
              </InfoBlock>
            )}
          </div>

          {host.disk && hasDisk && <DiskState disk={host.disk} />}

          <NetworkSection
            network={host.network ?? null}
            series={bandwidthSeries}
            live={live}
          />

          {host.printers && <PrintersSection printers={host.printers} />}

          {host.security && <SecuritySection security={host.security} />}

          <ChartCard title="CPU / RAM / Swap over time">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={timeSeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="time" fontSize={11} stroke="#94a3b8" />
                <YAxis domain={[0, 100]} fontSize={11} stroke="#94a3b8" />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="cpu"
                  stroke="#2563eb"
                  name="CPU %"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="ram"
                  stroke="#0f766e"
                  name="RAM %"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="swap"
                  stroke="#d97706"
                  name="Swap %"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>

          <ReportHistorySection reports={machine.reports} />
        </>
      )}
    </div>
  );
}

const HISTORY_PAGE_SIZE = 10;

function reportMatchesQuery(r: Report, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    fmtTime(r.created_at),
    r.pc_name,
    r.os?.hostname,
    r.app_version,
    r.private_ip,
    r.public_ip,
    machineMac(r),
    r.location?.country,
    r.location?.city,
    r.location?.region,
    fmtPercent(r.resources?.cpu_percent),
    fmtPercent(r.resources?.ram_percent),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(q);
}

function ReportHistorySection({ reports }: { reports: Report[] }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  const newestFirst = useMemo(
    () => reports.slice().reverse(),
    [reports],
  );

  const filtered = useMemo(
    () => newestFirst.filter((r) => reportMatchesQuery(r, query)),
    [newestFirst, query],
  );

  const totalPages = Math.max(1, Math.ceil(filtered.length / HISTORY_PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const start = (safePage - 1) * HISTORY_PAGE_SIZE;
  const pageRows = filtered.slice(start, start + HISTORY_PAGE_SIZE);

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm shadow-slate-200/60">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div>
          <h3 className="text-sm font-medium text-slate-700">Report history</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            {filtered.length} of {reports.length} reports
          </p>
        </div>
        <label className="relative block min-w-[12rem] flex-1 sm:max-w-xs">
          <span className="sr-only">Search reports</span>
          <input
            type="search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search time, PC, IP, country…"
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100"
          />
        </label>
      </div>
      <table className="w-full text-left text-sm">
        <thead className="border-b bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">Time</th>
            <th className="px-4 py-3">PC</th>
            <th className="px-4 py-3">IP</th>
            <th className="px-4 py-3">MAC</th>
            <th className="px-4 py-3">Country</th>
            <th className="px-4 py-3">CPU</th>
            <th className="px-4 py-3">RAM</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {pageRows.length === 0 ? (
            <tr>
              <td
                colSpan={7}
                className="px-4 py-8 text-center text-sm text-slate-500"
              >
                {query.trim()
                  ? "No reports match your search."
                  : "No reports yet."}
              </td>
            </tr>
          ) : (
            pageRows.map((r) => (
              <ReportRow
                key={r._id ?? `${r.created_at}-${r.public_ip}`}
                r={r}
              />
            ))
          )}
        </tbody>
      </table>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-4 py-3">
        <p className="text-xs text-slate-500">
          {filtered.length === 0
            ? "Page 0 of 0"
            : `Showing ${start + 1}–${Math.min(start + HISTORY_PAGE_SIZE, filtered.length)} · Page ${safePage} of ${totalPages}`}
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
            disabled={safePage >= totalPages}
            onClick={() => setPage(Math.min(totalPages, safePage + 1))}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

function SummarySection({
  machine,
  live,
}: {
  machine: MachineSummary;
  live?: LiveMetricsSample | null;
}) {
  const r = machine.latest;
  const res = r.resources;
  const uptime = r.uptime;
  const network = r.network;
  const security = r.security;
  const health = r.health;
  const printers = r.printers;

  const totalUp = Object.values(uptime?.by_day ?? {}).reduce(
    (sum, sec) => sum + sec,
    0,
  );

  const printTotal =
    (printers?.usb?.reduce((s, p) => s + (p.print_count ?? 0), 0) ?? 0) +
    (printers?.network?.reduce((s, p) => s + (p.print_count ?? 0), 0) ?? 0) +
    (printers?.other?.reduce((s, p) => s + (p.print_count ?? 0), 0) ?? 0);

  const printerCount = (printers?.usb?.length ?? 0) +
    (printers?.network?.length ?? 0) +
    (printers?.other?.length ?? 0);

  const disks = health?.disks ?? [];
  const ssdCount = disks.filter((d) => d.media_type === "ssd").length;
  const hddCount = disks.filter((d) => d.media_type === "hdd").length;
  const unhealthyDisks = disks.filter((d) => d.health === "fail" || d.health === "warning");
  const batteryHealth = health?.battery;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label="Total uptime"
          value={fmtUptime(totalUp)}
          sub={`${Object.keys(uptime?.by_day ?? {}).length} days tracked`}
          accent
        />
        <StatCard
          label="Current session"
          value={fmtUptime(uptime?.uptime_seconds)}
          sub={uptime?.boot_time ? `Since ${fmtTime(uptime.boot_time)}` : "—"}
        />
        <StatCard
          label="Network total"
          value={fmtBytes(
            live?.bytes_sent != null && live?.bytes_recv != null
              ? live.bytes_sent + live.bytes_recv
              : networkTotalBytes(r),
          )}
          sub="Sent + received since boot"
          accent
          live={live != null}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <InfoBlock title="CPU (full spec)">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
            <span className="text-slate-500">Brand</span>
            <span className="font-medium text-slate-900">{res?.cpu_brand || "—"}</span>
            <span className="text-slate-500">Model</span>
            <span className="font-medium text-slate-900">{r.os?.processor || "—"}</span>
            <span className="text-slate-500">Architecture</span>
            <span className="font-medium text-slate-900">{r.os?.machine || "—"}</span>
            <span className="text-slate-500">Cores (logical)</span>
            <span className="font-medium text-slate-900">{res?.cpu_count ?? "—"}</span>
            <span className="text-slate-500">Cores (physical)</span>
            <span className="font-medium text-slate-900">{res?.cpu_count_physical ?? "—"}</span>
            <span className="text-slate-500">Clock speed</span>
            <span className="font-medium text-slate-900">
              {res?.cpu_freq_mhz != null ? `${res.cpu_freq_mhz} MHz` : "—"}
            </span>
            <span className="text-slate-500">Usage</span>
            <span
              className={`font-medium ${
                isHighLiveLoad(live?.cpu_percent) ? "text-red-700" : "text-slate-900"
              }`}
            >
              {fmtPercent(live?.cpu_percent ?? res?.cpu_percent)}
              {isHighLiveLoad(live?.cpu_percent)
                ? " · high"
                : live
                  ? " · live"
                  : ""}
            </span>
          </div>
        </InfoBlock>

        <InfoBlock title="RAM (full spec)">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
            <span className="text-slate-500">Total</span>
            <span className="font-medium text-slate-900">
              {fmtBytes(live?.ram_total ?? res?.ram_total)}
            </span>
            <span className="text-slate-500">Used</span>
            <span
              className={`font-medium ${
                isHighLiveLoad(live?.ram_percent) ? "text-red-700" : "text-slate-900"
              }`}
            >
              {fmtPercent(live?.ram_percent ?? res?.ram_percent)}
              {isHighLiveLoad(live?.ram_percent)
                ? " · high"
                : live
                  ? " · live"
                  : ""}
            </span>
            <span className="text-slate-500">Available</span>
            <span className="font-medium text-slate-900">{fmtBytes(res?.ram_available)}</span>
            <span className="text-slate-500">Free</span>
            <span className="font-medium text-slate-900">{fmtBytes(res?.ram_free)}</span>
            <span className="text-slate-500">Swap total</span>
            <span className="font-medium text-slate-900">{fmtBytes(res?.swap_total)}</span>
            <span className="text-slate-500">Swap used</span>
            <span className="font-medium text-slate-900">{fmtBytes(res?.swap_used)}</span>
            <span className="text-slate-500">Bus speed</span>
            <span className="font-medium text-slate-900">
              {res?.ram_speed_mhz != null ? `${res.ram_speed_mhz} MHz` : "—"}
            </span>
            <span className="text-slate-500">Memory type</span>
            <span className="font-medium text-slate-900">{res?.ram_type || "—"}</span>
          </div>
        </InfoBlock>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-medium text-slate-700">Storage health</h2>
            <p className="text-xs text-slate-500">
              {ssdCount} SSD{ssdCount === 1 ? "" : "s"} · {hddCount} HDD{hddCount === 1 ? "" : "s"}
            </p>
          </div>
          {disks.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">No storage health data for this PC.</p>
          ) : (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {disks.map((d) => (
                <StorageHealthCard key={`${d.device}-${d.name}`} disk={d} />
              ))}
            </div>
          )}
          {unhealthyDisks.length > 0 && (
            <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
              {unhealthyDisks.length} disk{unhealthyDisks.length === 1 ? "" : "s"} need attention
            </p>
          )}
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-medium text-slate-700">Battery health</h2>
          </div>
          {!batteryHealth ? (
            <p className="mt-4 text-sm text-slate-500">
              No battery detected on this PC (desktop or unsupported).
            </p>
          ) : (
            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              <StatCard
                label="Health"
                value={batteryHealth.health_percent != null ? `${batteryHealth.health_percent}%` : "—"}
                sub="of original design capacity"
                accent
              />
              <StatCard
                label="Cycle count"
                value={
                  batteryHealth.cycle_count != null && batteryHealth.cycle_count > 0
                    ? String(batteryHealth.cycle_count)
                    : "—"
                }
                sub="Full charge cycles"
              />
              <StatCard
                label="Max capacity"
                value={batteryHealth.max_capacity_percent != null ? `${batteryHealth.max_capacity_percent}%` : "—"}
                sub="Current maximum charge"
              />
            </div>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-medium text-slate-700">Internet security</h2>
            {security?.count ? (
              <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700">
                {security.count} product{security.count === 1 ? "" : "s"} installed
              </span>
            ) : null}
          </div>
          {!security?.installed?.length ? (
            <p className="mt-4 text-sm text-slate-500">No internet-security software detected.</p>
          ) : (
            <ul className="mt-4 space-y-2">
              {security.installed.map((p) => (
                <li
                  key={`${p.name}-${p.vendor}`}
                  className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50/80 px-4 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-900">{p.name}</p>
                    <p className="truncate text-xs text-slate-500">{p.vendor}</p>
                    <SecurityExpiryLine product={p} />
                  </div>
                  {p.active === true && (
                    <span className="shrink-0 text-[11px] font-semibold text-emerald-600">Active</span>
                  )}
                  {p.active === false && (
                    <span className="shrink-0 text-[11px] font-semibold text-red-600">Inactive</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-medium text-slate-700">Printers</h2>
            <p className="text-xs text-slate-500">
              {printerCount} connected · <span className="font-semibold text-slate-800">{printTotal.toLocaleString()}</span> total prints
            </p>
          </div>
          {printerCount === 0 ? (
            <p className="mt-4 text-sm text-slate-500">No printers detected.</p>
          ) : (
            <ul className="mt-4 space-y-2">
              {[
                ...(printers?.usb ?? []),
                ...(printers?.network ?? []),
                ...(printers?.other ?? []),
              ].map((p) => (
                <li
                  key={`${p.name}-${p.port}`}
                  className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50/80 px-4 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-900">{p.name}</p>
                    <p className="truncate text-xs text-slate-500">{p.port || "—"}</p>
                  </div>
                  <span className="shrink-0 text-xs text-slate-600">
                    {p.print_count == null ? "—" : `${p.print_count.toLocaleString()} prints`}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-medium text-slate-700">Email accounts</h2>
            <p className="text-xs text-slate-500">
              <span className="font-semibold text-slate-800">
                {machineEmails(r).length}
              </span>{" "}
              configured
            </p>
          </div>
          {machineEmails(r).length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">
              No POP/IMAP email accounts detected.
            </p>
          ) : (
            <ul className="mt-4 space-y-2">
              {machineEmails(r).map((a, i) => (
                <li
                  key={`${a.email}-${a.client}-${i}`}
                  className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50/80 px-4 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-900">
                      {a.email || "—"}
                    </p>
                    <p className="truncate text-xs text-slate-500">
                      {clientLabel(a.client)}
                      {a.incoming_host ? ` · ${a.incoming_host}` : ""}
                    </p>
                  </div>
                  {a.protocol && (
                    <span className="shrink-0 rounded-full bg-blue-50 px-2.5 py-0.5 text-[11px] font-semibold uppercase text-blue-700">
                      {a.protocol}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function HealthSection({
  health,
}: {
  health: Report["health"];
}) {
  const disks = health?.disks ?? [];
  const battery = health?.battery ?? null;

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-medium text-slate-700">Storage health</h2>
          <p className="text-xs text-slate-500">
            SSD / HDD type and SMART status
          </p>
        </div>

        {disks.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">
            No storage health data for this PC.
          </p>
        ) : (
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            {disks.map((d) => (
              <StorageHealthCard key={`${d.device}-${d.name}`} disk={d} />
            ))}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-medium text-slate-700">Battery health</h2>
          {battery?.condition && (
            <span
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                /good|normal|ok/i.test(battery.condition)
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-amber-50 text-amber-700"
              }`}
            >
              {battery.condition}
            </span>
          )}
        </div>

        {!battery ? (
          <p className="mt-4 text-sm text-slate-500">
            No battery detected (desktop or unsupported).
          </p>
        ) : (
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <StatCard
              label="Health"
              value={
                battery.health_percent != null
                  ? `${battery.health_percent}%`
                  : "—"
              }
              sub="of original design capacity"
              accent
            />
            <StatCard
              label="Cycle count"
              value={
                battery.cycle_count != null && battery.cycle_count > 0
                  ? String(battery.cycle_count)
                  : "—"
              }
              sub="Full charge cycles"
            />
            <StatCard
              label="Max capacity"
              value={
                battery.max_capacity_percent != null
                  ? `${battery.max_capacity_percent}%`
                  : "—"
              }
              sub="Current maximum charge"
            />
          </div>
        )}
      </div>
    </div>
  );
}

type HealthDisk = NonNullable<
  NonNullable<Report["health"]>["disks"]
>[number];

function StorageHealthCard({ disk }: { disk: HealthDisk }) {
  const ssd = disk.media_type === "ssd";
  const hdd = disk.media_type === "hdd";
  const mediaLabel = (disk.media_type || "unknown").toUpperCase();
  const mediaStyle = ssd
    ? "bg-blue-50 text-blue-700 ring-blue-200/70"
    : hdd
      ? "bg-amber-50 text-amber-700 ring-amber-200/70"
      : "bg-slate-50 text-slate-600 ring-slate-200/70";
  const tileStyle = ssd
    ? "bg-blue-50 text-blue-600"
    : hdd
      ? "bg-amber-50 text-amber-600"
      : "bg-slate-100 text-slate-500";

  return (
    <div className="group rounded-2xl border border-slate-100 bg-white p-5 shadow-sm shadow-slate-200/50 transition hover:border-blue-200/80 hover:shadow-md hover:shadow-blue-100/40">
      <div className="flex items-start gap-3.5">
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${tileStyle}`}
          aria-hidden
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-5 w-5"
          >
            <path d="M22 12H2" />
            <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
            <line x1="6" x2="6.01" y1="16" y2="16" />
            <line x1="10" x2="10.01" y1="16" y2="16" />
          </svg>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-semibold text-slate-900">
              {disk.name}
            </p>
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${mediaStyle}`}
            >
              {mediaLabel}
            </span>
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-slate-500">
            {disk.brand && (
              <span className="font-semibold text-slate-600">{disk.brand}</span>
            )}
            {disk.brand && disk.device && (
              <span className="text-slate-300">·</span>
            )}
            {disk.device && <span className="font-mono">{disk.device}</span>}
            {disk.internal != null && (
              <span className="text-slate-300">·</span>
            )}
            {disk.internal != null && (
              <span className="text-slate-500">
                {disk.internal ? "Internal" : "External"}
              </span>
            )}
          </p>
        </div>
      </div>

      <div className="mt-4 flex items-end justify-between gap-3 border-t border-slate-100 pt-3.5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
            Total storage
          </p>
          <p className="mt-0.5 text-2xl font-semibold tracking-tight text-slate-900">
            {disk.size_bytes != null ? fmtBytes(disk.size_bytes) : "—"}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          {disk.smart_status && (
            <span className="text-[11px] text-slate-500">
              SMART <span className="font-semibold text-slate-700">{disk.smart_status}</span>
            </span>
          )}
          <HealthBadge health={disk.health} />
        </div>
      </div>
    </div>
  );
}

function HealthBadge({ health }: { health: string }) {
  const map: Record<string, string> = {
    ok: "bg-emerald-50 text-emerald-700",
    warning: "bg-amber-50 text-amber-700",
    fail: "bg-red-50 text-red-700",
    unknown: "bg-slate-100 text-slate-600",
  };
  return (
    <span
      className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
        map[health] ?? map.unknown
      }`}
    >
      {health === "ok" ? "Healthy" : health === "fail" ? "Failing" : health === "warning" ? "Warning" : "Unknown"}
    </span>
  );
}

function UptimeState({
  uptime,
}: {
  uptime: NonNullable<Report["uptime"]>;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium text-slate-700">Uptime</h2>
        <p className="text-xs text-slate-500">Summary · full details in the Uptime tab</p>
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <StatCard
          label="Current session"
          value={fmtUptime(uptime.uptime_seconds)}
          sub={`Since boot · ${fmtTime(uptime.boot_time)}`}
          accent
        />
        <StatCard
          label="Days tracked"
          value={String(Object.keys(uptime.by_day ?? {}).length)}
          sub={`${uptime.day_timezone ?? "UTC"} buckets`}
        />
      </div>
    </div>
  );
}

function UptimeSection({
  uptime,
}: {
  uptime: NonNullable<Report["uptime"]>;
}) {
  const [visibleDays, setVisibleDays] = useState(14);
  const allDays = Object.entries(uptime.by_day ?? {}).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  const days = allDays.slice(-visibleDays);
  const maxSec = Math.max(1, ...allDays.map(([, s]) => s));
  const remaining = allDays.length - days.length;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium text-slate-700">Uptime</h2>
        <p className="text-xs text-slate-500">
          Days in UTC · labels also show Asia/Dhaka (BD)
        </p>
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <StatCard
          label="Current session"
          value={fmtUptime(uptime.uptime_seconds)}
          sub={`Since boot · ${fmtTime(uptime.boot_time)}`}
          accent
        />
        <StatCard
          label="Days tracked"
          value={String(allDays.length)}
          sub={`${uptime.day_timezone ?? "UTC"} buckets`}
        />
      </div>
      {days.length > 0 && (
        <ul className="mt-5 space-y-3">
          {days.map(([day, seconds]) => {
            const pct = Math.min(100, (seconds / maxSec) * 100);
            return (
              <li key={day}>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-sm text-slate-800">{formatUtcDayBd(day)}</p>
                  <p className="text-xs font-medium text-slate-600">
                    {fmtUptime(seconds)}
                  </p>
                </div>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-blue-500"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {remaining > 0 && (
        <button
          type="button"
          onClick={() => setVisibleDays((v) => v + 14)}
          className="mt-5 w-full rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Load {Math.min(remaining, 14)} more{" "}
          {remaining === 1 ? "day" : "days"} ({remaining} older remaining)
        </button>
      )}
    </div>
  );
}

function NetworkSection({
  network,
  series,
  live,
}: {
  network: Report["network"] | null;
  series: { time: string; upload: number; download: number }[];
  live?: LiveMetricsSample | null;
}) {
  const hasRates = series.some((p) => p.upload > 0 || p.download > 0);
  const bytesSent = live?.bytes_sent ?? network?.bytes_sent;
  const bytesRecv = live?.bytes_recv ?? network?.bytes_recv;
  const sendRate = live?.send_rate_bps ?? network?.send_rate_bps;
  const recvRate = live?.recv_rate_bps ?? network?.recv_rate_bps;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
      <h2 className="text-sm font-medium text-slate-700">Network bandwidth</h2>
      <p className="mt-1 text-xs text-slate-500">
        {live
          ? "Totals since boot · NIC rates live over WebSocket"
          : "Totals since boot · NIC rates sampled at report time"}
      </p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Sent total"
          value={fmtBytes(bytesSent)}
          sub="Since boot"
          live={live != null}
        />
        <StatCard
          label="Received total"
          value={fmtBytes(bytesRecv)}
          sub="Since boot"
          live={live != null}
        />
        <StatCard
          label="Upload rate"
          value={fmtRate(sendRate)}
          sub={live ? "Live" : "Current sample"}
          accent
          live={live != null}
        />
        <StatCard
          label="Download rate"
          value={fmtRate(recvRate)}
          sub={live ? "Live" : "Current sample"}
          accent
          live={live != null}
        />
      </div>

      {hasRates && (
        <div className="mt-6">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
            Bandwidth usage over time
          </h3>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={series}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="time" fontSize={11} stroke="#94a3b8" />
              <YAxis fontSize={11} stroke="#94a3b8" unit=" KiB/s" />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="upload"
                stroke="#2563eb"
                name="Upload KiB/s"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="download"
                stroke="#0f766e"
                name="Download KiB/s"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function PrintersTab({
  printers,
}: {
  printers: NonNullable<Report["printers"]>;
}) {
  const groups: { key: "usb" | "network" | "other"; label: string }[] = [
    { key: "usb", label: "USB" },
    { key: "network", label: "Network" },
    { key: "other", label: "Other" },
  ];
  const all = [
    ...(printers.usb ?? []),
    ...(printers.network ?? []),
    ...(printers.other ?? []),
  ];
  const count =
    all.length > 0 ? all.length : printers.count ?? 0;
  const totalPrints = all.reduce((s, p) => s + (p.print_count ?? 0), 0);
  const printed = all.filter((p) => p.print_count != null).length;
  const avgPrints = printed > 0 ? totalPrints / printed : 0;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Connected printers"
          value={String(count)}
          sub={`${groups.reduce((s, { key }) => s + (printers[key]?.length ?? 0), 0)} detected`}
          accent
        />
        <StatCard
          label="Total prints"
          value={totalPrints.toLocaleString()}
          sub={`${printed} printer${printed === 1 ? "" : "s"} reporting counts`}
          accent
        />
        <StatCard
          label="Avg prints / printer"
          value={avgPrints > 0 ? avgPrints.toFixed(1) : "—"}
          sub="Across printers with counts"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {groups.map(({ key, label }) => {
          const items = printers[key] ?? [];
          const groupPrints = items.reduce((s, p) => s + (p.print_count ?? 0), 0);
          return (
            <div
              key={key}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50"
            >
              <div className="flex items-baseline justify-between gap-2">
                <h3 className="text-sm font-semibold text-slate-700">{label}</h3>
                <span className="text-xs font-medium text-slate-700">
                  {items.length} · {groupPrints.toLocaleString()} prints
                </span>
              </div>
              {items.length === 0 ? (
                <p className="mt-3 text-sm text-slate-400">None</p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {items.map((p) => (
                    <li
                      key={`${p.name}-${p.port}`}
                      className="rounded-xl border border-slate-100 bg-slate-50/80 px-4 py-3"
                    >
                      <p className="truncate text-sm font-medium text-slate-900">
                        {p.name}
                      </p>
                      <p className="mt-0.5 truncate font-mono text-[11px] text-slate-500">
                        {p.port || "—"}
                      </p>
                      <div className="mt-1.5 flex items-center justify-between gap-2 text-xs text-slate-600">
                        {key === "network" ? (
                          <span>
                            IP:{" "}
                            <span className="font-medium text-slate-800">
                              {p.ip || "—"}
                            </span>
                          </span>
                        ) : (
                          <span />
                        )}
                        <span className="font-semibold text-slate-800">
                          {p.print_count == null
                            ? "—"
                            : `${p.print_count.toLocaleString()} prints`}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PrintersSection({
  printers,
}: {
  printers: NonNullable<Report["printers"]>;
}) {
  const groups: { key: "usb" | "network" | "other"; label: string }[] = [
    { key: "usb", label: "USB" },
    { key: "network", label: "Network" },
    { key: "other", label: "Other" },
  ];
  const count = printers.count ?? 0;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium text-slate-700">Printers</h2>
        <p className="text-xs text-slate-500">
          Connected:{" "}
          <span className="font-semibold text-slate-800">{count}</span>
        </p>
      </div>

      {count === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No printers detected.</p>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          {groups.map(({ key, label }) => {
            const items = printers[key] ?? [];
            return (
              <div
                key={key}
                className="rounded-xl border border-slate-100 bg-slate-50/80 p-4"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                    {label}
                  </h3>
                  <span className="text-xs font-medium text-slate-700">
                    {items.length}
                  </span>
                </div>
                {items.length === 0 ? (
                  <p className="mt-3 text-sm text-slate-400">None</p>
                ) : (
                  <ul className="mt-3 space-y-3">
                    {items.map((p) => (
                      <li key={`${p.name}-${p.port}`} className="min-w-0">
                        <p className="truncate text-sm font-medium text-slate-900">
                          {p.name}
                        </p>
                        <p className="truncate font-mono text-[11px] text-slate-500">
                          {p.port || "—"}
                        </p>
                        <p className="mt-1 text-xs text-slate-600">
                          {key === "network" ? (
                            <>
                              IP:{" "}
                              <span className="font-medium text-slate-800">
                                {p.ip || "—"}
                              </span>
                              <span className="mx-1.5 text-slate-300">·</span>
                            </>
                          ) : null}
                          Prints:{" "}
                          <span className="font-medium text-slate-800">
                            {p.print_count == null
                              ? "—"
                              : p.print_count.toLocaleString()}
                          </span>
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function EmailsTab({
  accounts,
}: {
  accounts: EmailAccountInfo[];
}) {
  const total = accounts.length;
  const protocols = [...new Set(accounts.map((a) => a.protocol).filter(Boolean))];
  const clients = [...new Set(accounts.map((a) => a.client).filter(Boolean))];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Email accounts"
          value={String(total)}
          sub="POP / IMAP accounts configured"
          accent
        />
        <StatCard
          label="Protocols"
          value={protocols.join(", ") || "—"}
          sub="Across configured accounts"
        />
        <StatCard
          label="Clients"
          value={clients.length ? String(clients.length) : "—"}
          sub={clients.map(clientLabel).join(", ") || "Mail clients"}
        />
      </div>

      {total === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
          No POP/IMAP email accounts detected on this PC.
        </div>
      ) : (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-medium text-slate-700">Configured accounts</h2>
            <p className="text-xs text-slate-500">
              Server config only — passwords stay in the OS keychain and are not read
            </p>
          </div>
          <ul className="mt-4 space-y-2">
            {accounts.map((a, i) => (
              <li
                key={`${a.email}-${a.client}-${i}`}
                className="rounded-xl border border-slate-100 bg-slate-50/80 px-4 py-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-900">
                      {a.email || a.username || "—"}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-slate-500">
                      {a.full_name ? `${a.full_name} · ` : ""}
                      {clientLabel(a.client)}
                      {a.username ? ` · ${a.username}` : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {a.protocol && (
                      <span className="rounded-full bg-blue-50 px-2.5 py-0.5 text-[11px] font-semibold uppercase text-blue-700">
                        {a.protocol}
                      </span>
                    )}
                    {a.security && (
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                          a.security === "none"
                            ? "bg-red-50 text-red-700"
                            : "bg-emerald-50 text-emerald-700"
                        }`}
                      >
                        {a.security.toUpperCase()}
                      </span>
                    )}
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-slate-500">
                  {a.incoming_host && (
                    <span>
                      IN {a.incoming_host}
                      {a.incoming_port ? `:${a.incoming_port}` : ""}
                    </span>
                  )}
                  {a.outgoing_host && (
                    <span>
                      OUT {a.outgoing_host}
                      {a.outgoing_port ? `:${a.outgoing_port}` : ""}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SecuritySection({
  security,
}: {
  security: NonNullable<Report["security"]>;
}) {
  const installed = security.installed ?? [];
  const protectedOk = installed.length > 0;

  return (
    <div
      className={`rounded-2xl border p-5 shadow-sm shadow-slate-200/50 ${
        protectedOk ? "border-emerald-200 bg-white" : "border-red-200 bg-white"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium text-slate-700">
            Internet Security
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">
            {security.platform === "windows"
              ? "From Windows Security Center"
              : "Detected apps, processes and launch items"}
          </p>
        </div>
        {protectedOk ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            {security.count} product{security.count === 1 ? "" : "s"} installed
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 px-3 py-1 text-xs font-semibold text-red-700">
            <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
            No security software detected
          </span>
        )}
      </div>

      {installed.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">
          No internet-security software was found on this PC.
        </p>
      ) : (
        <ul className="mt-4 grid gap-2 sm:grid-cols-2">
          {installed.map((p) => (
            <li
              key={`${p.name}-${p.vendor}`}
              className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50/80 px-4 py-3"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-900">
                  {p.name}
                </p>
                <p className="mt-0.5 text-xs text-slate-500">{p.vendor}</p>
                <SecurityExpiryLine product={p} />
              </div>
              {p.active === true && (
                <span className="shrink-0 text-[11px] font-semibold text-emerald-600">
                  Active
                </span>
              )}
              {p.active === false && (
                <span className="shrink-0 text-[11px] font-semibold text-red-600">
                  Inactive
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type SecurityProductInfo = NonNullable<
  NonNullable<Report["security"]>["installed"]
>[number];

function formatExpiryDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function SecurityExpiryLine({ product }: { product: SecurityProductInfo }) {
  if (product.expired) {
    return (
      <p className="mt-0.5 text-xs font-semibold text-red-600">Expired</p>
    );
  }
  if (!product.expiry_date) return null;
  const days = product.days_remaining ?? 0;
  const remaining = days === 1 ? "1 day remaining" : `${days} days remaining`;
  const soon = days <= 30;
  return (
    <p className={`mt-0.5 text-xs ${soon ? "font-medium text-amber-700" : "text-slate-500"}`}>
      {remaining} · expires {formatExpiryDate(product.expiry_date)}
    </p>
  );
}

function diskBarColor(percent: number): string {
  if (percent > 80) return "bg-red-500";
  if (percent >= 50) return "bg-amber-500";
  return "bg-blue-500";
}function DiskState({ disk }: { disk: NonNullable<Report["disk"]> }) {
  const devices = disk.devices ?? [];
  const total = devices.reduce((sum, d) => sum + (d.total ?? 0), 0);
  const used = devices.reduce((sum, d) => sum + (d.used ?? 0), 0);
  const free = devices.reduce((sum, d) => sum + (d.free ?? 0), 0);
  const pct =
    total > 0
      ? Math.min(100, Math.max(0, (used / total) * 100))
      : 0;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium text-slate-700">Storage</h2>
        <p className="text-xs text-slate-500">
          Summary · full details in the Storage tab
        </p>
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Devices"
          value={String(devices.length)}
          sub={`${disk.partitions?.length ?? 0} partitions`}
        />
        <StatCard
          label="Used"
          value={fmtBytes(used)}
          sub={`${fmtBytes(total)} total`}
          accent
        />
        <StatCard
          label="Free"
          value={fmtBytes(free)}
          sub={`${pct.toFixed(0)}% used`}
        />
      </div>
    </div>
  );
}

function StorageSection({ disk }: { disk: NonNullable<Report["disk"]> }) {
  const devices = disk.devices ?? [];
  const partitions = disk.partitions ?? [];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium text-slate-700">Storage</h2>
        <p className="text-xs text-slate-500">
          Physical devices:{" "}
          <span className="font-semibold text-slate-800">{devices.length}</span>
        </p>
      </div>

      {devices.length > 0 && (
        <ul className="mt-4 grid gap-3 sm:grid-cols-2">
          {devices.map((d) => (
            <li
              key={d.device}
              className="rounded-xl border border-slate-100 bg-slate-50/80 px-4 py-3"
            >
              <p className="truncate font-mono text-sm font-medium text-slate-900">
                {d.device}
              </p>
              <p className="mt-1 text-sm text-slate-600">
                Total {fmtBytes(d.total)}
                <span className="mx-1.5 text-slate-300">·</span>
                {fmtBytes(d.used)} used / {fmtBytes(d.free)} free
              </p>
            </li>
          ))}
        </ul>
      )}

      {partitions.length > 0 && (
        <div className="mt-5 space-y-4">
          <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
            Partitions
          </h3>
          <ul className="space-y-4">
            {partitions.map((p) => {
              const pct = Math.min(100, Math.max(0, p.percent ?? 0));
              return (
                <li key={`${p.device}-${p.mountpoint}`}>
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-900">
                        {p.mountpoint}
                      </p>
                      <p className="mt-0.5 truncate font-mono text-xs text-slate-500">
                        {p.device}
                        {p.fstype ? ` · ${p.fstype}` : ""}
                      </p>
                    </div>
                    <p className="shrink-0 text-xs text-slate-500">
                      {fmtBytes(p.used)} used · {fmtBytes(p.free)} free ·{" "}
                      {fmtBytes(p.total)} · {fmtPercent(p.percent)}
                    </p>
                  </div>
                  <div
                    className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100"
                    role="progressbar"
                    aria-valuenow={Math.round(pct)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`${p.mountpoint} disk usage`}
                  >
                    <div
                      className={`h-full rounded-full transition-[width] ${diskBarColor(pct)}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  accent,
  live,
  warn,
}: {
  label: string;
  value: string;
  sub: string;
  accent?: boolean;
  live?: boolean;
  warn?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border p-5 shadow-sm shadow-slate-200/50 ${
        warn
          ? "border-red-200 bg-red-50/80"
          : accent
            ? "border-blue-100 bg-blue-50/70"
            : "border-slate-200 bg-white"
      }`}
    >
      <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
        {label}
        {live && (
          <span
            className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[9px] font-bold tracking-wide ${
              warn
                ? "bg-red-500 text-white"
                : "bg-emerald-100 text-emerald-700"
            }`}
          >
            {warn && (
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-white" />
              </span>
            )}
            {warn ? "High" : "Live"}
          </span>
        )}
      </p>
      <p
        className={`mt-1 text-3xl font-semibold tracking-tight ${
          warn ? "text-red-700" : accent ? "text-blue-700" : "text-slate-900"
        }`}
      >
        {value}
      </p>
      <p className="mt-1 text-sm text-slate-500">{sub}</p>
    </div>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
      <h2 className="mb-4 text-sm font-medium text-slate-700">{title}</h2>
      {children}
    </div>
  );
}

function InfoBlock({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
      <h2 className="text-sm font-medium text-slate-700">{title}</h2>
      <div className="mt-1 text-sm leading-relaxed text-slate-500">
        {children}
      </div>
    </div>
  );
}

function IdentityItem({
  label,
  value,
}: {
  label: string;
  value?: string | null;
}) {
  return (
    <span className="flex items-baseline gap-1.5 text-xs">
      <span className="font-medium text-slate-500">{label}</span>
      <span className="font-mono text-sm font-medium text-slate-900">
        {value || "—"}
      </span>
    </span>
  );
}

function ReportRow({ r }: { r: Report }) {
  return (
    <tr className="hover:bg-slate-50/80">
      <td className="px-4 py-3 text-slate-600">{fmtTime(r.created_at)}</td>
      <td className="px-4 py-3 font-medium text-slate-900">
        {r.pc_name || r.os?.hostname || "—"}
      </td>
      <td className="px-4 py-3 text-slate-600">
        {r.private_ip ?? "—"}
        {r.public_ip ? ` / ${r.public_ip}` : ""}
      </td>
      <td className="px-4 py-3 font-mono text-slate-600">
        {machineMac(r) ?? "—"}
      </td>
      <td className="px-4 py-3 text-slate-600">
        {r.location?.country ?? "—"}
      </td>
      <td className="px-4 py-3 text-slate-600">
        {fmtPercent(r.resources?.cpu_percent)}
      </td>
      <td className="px-4 py-3 text-slate-600">
        {fmtPercent(r.resources?.ram_percent)}
      </td>
    </tr>
  );
}
