"use client";

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
  fmtBytes,
  fmtMbps,
  fmtPercent,
  fmtRate,
  fmtTime,
  fmtUptime,
  formatUtcDayBd,
  MachineSummary,
  Report,
} from "@/lib/api";
import { LiveSpeedTest } from "./live-speed-test";

export function MachineDetail({ machine }: { machine: MachineSummary }) {
  const host = machine.latest;
  const timeSeries = machine.reports.map((r) => ({
    time: fmtTime(r.created_at),
    cpu: r.resources?.cpu_percent ?? 0,
    ram: r.resources?.ram_percent ?? 0,
    swap: r.resources?.swap_percent ?? 0,
  }));
  const bandwidthSeries = machine.reports.map((r) => ({
    time: fmtTime(r.created_at),
    upload: (r.network?.send_rate_bps ?? 0) / 1000,
    download: (r.network?.recv_rate_bps ?? 0) / 1000,
  }));

  return (
    <div className="space-y-6">
      {host.resources && (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard
            label="CPU usage"
            value={fmtPercent(host.resources.cpu_percent)}
            sub={`${host.resources.cpu_count ?? "?"} cores · ${
              host.resources.cpu_freq_mhz ?? "?"
            } MHz`}
            accent
          />
          <StatCard
            label="Memory (RAM)"
            value={fmtPercent(host.resources.ram_percent)}
            sub={`${fmtBytes(host.resources.ram_used)} / ${fmtBytes(
              host.resources.ram_total,
            )}`}
          />
          <StatCard
            label="Swap"
            value={fmtPercent(host.resources.swap_percent)}
            sub={`${fmtBytes(host.resources.swap_used)} / ${fmtBytes(
              host.resources.swap_total,
            )}`}
          />
        </div>
      )}

      {host.uptime && <UptimeSection uptime={host.uptime} />}

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
            <span className="mx-1 text-slate-300">·</span>
            {host.private_ip ?? "—"}
            {host.public_ip ? ` / ${host.public_ip}` : ""}
          </InfoBlock>
        )}
      </div>

      {host.disk &&
        ((host.disk.devices?.length ?? 0) > 0 ||
          (host.disk.partitions?.length ?? 0) > 0) && (
          <StorageSection disk={host.disk} />
        )}

      <NetworkSection network={host.network ?? null} series={bandwidthSeries} />

      {host.printers && <PrintersSection printers={host.printers} />}

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

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm shadow-slate-200/60">
        <div className="border-b border-slate-100 px-4 py-3">
          <h3 className="text-sm font-medium text-slate-700">Report history</h3>
        </div>
        <table className="w-full text-left text-sm">
          <thead className="border-b bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">PC</th>
              <th className="px-4 py-3">IP</th>
              <th className="px-4 py-3">Country</th>
              <th className="px-4 py-3">CPU</th>
              <th className="px-4 py-3">RAM</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {machine.reports
              .slice()
              .reverse()
              .map((r) => (
                <ReportRow
                  key={r._id ?? `${r.created_at}-${r.public_ip}`}
                  r={r}
                />
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function UptimeSection({
  uptime,
}: {
  uptime: NonNullable<Report["uptime"]>;
}) {
  const days = Object.entries(uptime.by_day ?? {})
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-14);
  const maxSec = Math.max(1, ...days.map(([, s]) => s));

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
          value={String(Object.keys(uptime.by_day ?? {}).length)}
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
    </div>
  );
}

function NetworkSection({
  network,
  series,
}: {
  network: Report["network"] | null;
  series: { time: string; upload: number; download: number }[];
}) {
  const hasRates = series.some((p) => p.upload > 0 || p.download > 0);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
      <h2 className="text-sm font-medium text-slate-700">Network bandwidth</h2>
      <p className="mt-1 text-xs text-slate-500">
        Totals since boot · NIC rates at report time · internet probe approx
      </p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          label="Sent total"
          value={fmtBytes(network?.bytes_sent)}
          sub="Since boot"
        />
        <StatCard
          label="Received total"
          value={fmtBytes(network?.bytes_recv)}
          sub="Since boot"
        />
        <StatCard
          label="Upload rate"
          value={fmtRate(network?.send_rate_bps)}
          sub="Current sample"
          accent
        />
        <StatCard
          label="Download rate"
          value={fmtRate(network?.recv_rate_bps)}
          sub="Current sample"
          accent
        />
        <StatCard
          label="Internet speed"
          value={fmtMbps(network?.download_mbps)}
          sub="Approx download probe"
          accent
        />
      </div>

      <LiveSpeedTest />

      {hasRates && (
        <div className="mt-6">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
            Bandwidth usage over time
          </h3>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={series}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="time" fontSize={11} stroke="#94a3b8" />
              <YAxis fontSize={11} stroke="#94a3b8" unit=" KB/s" />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="upload"
                stroke="#2563eb"
                name="Upload KB/s"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="download"
                stroke="#0f766e"
                name="Download KB/s"
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

function diskBarColor(percent: number): string {
  if (percent > 80) return "bg-red-500";
  if (percent >= 50) return "bg-amber-500";
  return "bg-blue-500";
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
}: {
  label: string;
  value: string;
  sub: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border p-5 shadow-sm shadow-slate-200/50 ${
        accent
          ? "border-blue-100 bg-blue-50/70"
          : "border-slate-200 bg-white"
      }`}
    >
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
        {label}
      </p>
      <p
        className={`mt-1 text-3xl font-semibold tracking-tight ${
          accent ? "text-blue-700" : "text-slate-900"
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
      <p className="mt-1 text-sm leading-relaxed text-slate-500">{children}</p>
    </div>
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
