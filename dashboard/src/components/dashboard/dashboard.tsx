"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
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
  fetchReports,
  fmtBytes,
  fmtPercent,
  fmtRelative,
  fmtTime,
  groupMachines,
  MachineSummary,
  Report,
} from "@/lib/api";
import { SignOutButton } from "./sign-out-button";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export function Dashboard() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const [filter, setFilter] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["reports"],
    queryFn: () => fetchReports(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
    refetchInterval: 30_000,
  });

  const reports = data?.reports ?? [];
  const machines = useMemo(() => groupMachines(reports), [reports]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return machines;
    return machines.filter((m) => m.name.toLowerCase().includes(q));
  }, [machines, filter]);

  useEffect(() => {
    if (filtered.length === 0) {
      setSelectedKey(null);
      return;
    }
    if (!selectedKey || !filtered.some((m) => m.key === selectedKey)) {
      setSelectedKey(filtered[0].key);
    }
  }, [filtered, selectedKey]);

  const selected =
    filtered.find((m) => m.key === selectedKey) ?? filtered[0] ?? null;

  return (
    <div className="flex min-h-screen bg-[var(--bg)] text-[var(--ink)]">
      <aside className="flex w-72 shrink-0 flex-col border-r border-slate-800 bg-slate-950 text-slate-100">
        <div className="border-b border-slate-800 px-4 py-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
            System Info
          </p>
          <h1 className="mt-1 text-lg font-semibold tracking-tight text-white">
            Fleet
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            {machines.length} machine{machines.length === 1 ? "" : "s"} ·{" "}
            {reports.length} report{reports.length === 1 ? "" : "s"}
          </p>
        </div>

        <div className="px-3 pt-3">
          <label className="sr-only" htmlFor="pc-filter">
            Filter PCs
          </label>
          <input
            id="pc-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by PC name…"
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
          />
        </div>

        <nav className="mt-3 flex-1 overflow-y-auto px-2 pb-4">
          {isLoading && (
            <p className="px-2 py-6 text-center text-sm text-slate-400">
              Loading machines…
            </p>
          )}
          {!isLoading && filtered.length === 0 && (
            <p className="px-2 py-6 text-center text-sm text-slate-400">
              No machines match.
            </p>
          )}
          <ul className="space-y-1">
            {filtered.map((m) => {
              const active = m.key === selected?.key;
              const cpu = m.latest.resources?.cpu_percent;
              return (
                <li key={m.key}>
                  <button
                    type="button"
                    onClick={() => setSelectedKey(m.key)}
                    className={`w-full rounded-lg px-3 py-2.5 text-left transition ${
                      active
                        ? "bg-blue-600 text-white shadow-sm shadow-blue-900/40"
                        : "text-slate-200 hover:bg-slate-900"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="truncate text-sm font-medium">
                        {m.name}
                      </span>
                      <span
                        className={`shrink-0 text-[11px] ${
                          active ? "text-blue-100" : "text-slate-500"
                        }`}
                      >
                        {fmtRelative(m.latest.created_at)}
                      </span>
                    </div>
                    <div
                      className={`mt-1 flex items-center gap-2 text-[11px] ${
                        active ? "text-blue-100/90" : "text-slate-400"
                      }`}
                    >
                      <span>CPU {fmtPercent(cpu)}</span>
                      <span aria-hidden>·</span>
                      <span>RAM {fmtPercent(m.latest.resources?.ram_percent)}</span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="border-t border-slate-800 p-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => refetch()}
              className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-100 hover:bg-slate-800 disabled:opacity-50"
              disabled={isFetching}
            >
              {isFetching ? "Refreshing…" : "Refresh"}
            </button>
            <SignOutButton />
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-slate-200 bg-white/80 px-6 py-4 backdrop-blur">
          {selected ? (
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-slate-900">
                  {selected.name}
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  {selected.latest.os?.system ?? "—"}{" "}
                  {selected.latest.os?.release ?? ""}
                  <span className="mx-1.5 text-slate-300">·</span>
                  Last seen {fmtRelative(selected.latest.created_at)}
                  {selected.deviceId ? (
                    <>
                      <span className="mx-1.5 text-slate-300">·</span>
                      <span className="font-mono text-xs text-slate-400">
                        {selected.deviceId.slice(0, 8)}…
                      </span>
                    </>
                  ) : null}
                </p>
              </div>
              <p className="text-xs text-slate-400">
                {selected.reports.length} report
                {selected.reports.length === 1 ? "" : "s"} for this PC
              </p>
            </div>
          ) : (
            <div>
              <h2 className="text-xl font-semibold text-slate-900">
                No machine selected
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Reports will appear here once the desktop app posts data.
              </p>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          {isError && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              Failed to load reports from the API at {API_URL}. Is it running?
            </div>
          )}

          {!isLoading && !isError && selected && (
            <MachineDetail machine={selected} />
          )}

          {!isLoading && !isError && !selected && (
            <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/60 text-sm text-slate-500">
              Waiting for the first report…
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function MachineDetail({ machine }: { machine: MachineSummary }) {
  const host = machine.latest;
  const timeSeries = machine.reports.map((r) => ({
    time: fmtTime(r.created_at),
    cpu: r.resources?.cpu_percent ?? 0,
    ram: r.resources?.ram_percent ?? 0,
    swap: r.resources?.swap_percent ?? 0,
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
                  <ul className="mt-3 space-y-2">
                    {items.map((p) => (
                      <li key={`${p.name}-${p.port}`} className="min-w-0">
                        <p className="truncate text-sm font-medium text-slate-900">
                          {p.name}
                        </p>
                        <p className="truncate font-mono text-[11px] text-slate-500">
                          {p.port || "—"}
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
