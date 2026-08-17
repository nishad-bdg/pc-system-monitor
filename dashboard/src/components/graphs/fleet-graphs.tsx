"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchGroups,
  fetchReports,
  Group,
  groupMachines,
  groupOf,
  MachineSummary,
} from "@/lib/api";
import { DashboardShell } from "@/components/dashboard/shell";
import { StatusDot } from "@/components/dashboard/status-dot";
import { useRealtime } from "@/components/realtime-provider";
import type { LiveMetricsSample } from "@/components/realtime-provider";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const HISTORY_MS = 15 * 60 * 1000;
const SAMPLE_MS = 5_000;

const PALETTE = [
  "#2563eb",
  "#0f766e",
  "#c2410c",
  "#7c3aed",
  "#db2777",
  "#0891b2",
  "#65a30d",
  "#ea580c",
  "#4f46e5",
  "#b45309",
  "#0d9488",
  "#be123c",
];

type HistPoint = {
  t: number;
  time: string;
  cpu: Record<string, number>;
  ram: Record<string, number>;
  net: Record<string, number>;
};

function formatClock(ts: number): string {
  return new Date(ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function seriesKey(m: MachineSummary): string {
  return (m.deviceId || m.key).replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 48);
}

function liveSnapshot(
  machines: MachineSummary[],
  metricsFor: (id?: string | null) => LiveMetricsSample | null,
) {
  const cpu: Record<string, number> = {};
  const ram: Record<string, number> = {};
  const net: Record<string, number> = {};
  for (const m of machines) {
    const key = seriesKey(m);
    const live = metricsFor(m.deviceId);
    cpu[key] = live?.cpu_percent ?? m.latest.resources?.cpu_percent ?? 0;
    ram[key] = live?.ram_percent ?? m.latest.resources?.ram_percent ?? 0;
    const send =
      live?.eth_send_rate_bps ?? live?.send_rate_bps ?? m.latest.network?.send_rate_bps ?? 0;
    const recv =
      live?.eth_recv_rate_bps ?? live?.recv_rate_bps ?? m.latest.network?.recv_rate_bps ?? 0;
    net[key] = ((Math.max(0, send) + Math.max(0, recv)) * 8) / 1_000_000;
  }
  return { cpu, ram, net };
}

export function FleetGraphs() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const { connected, isOnline, metricsFor, refreshAll } = useRealtime();
  const [groupFilter, setGroupFilter] = useState("");
  const [history, setHistory] = useState<HistPoint[]>([]);

  const { data, isLoading, isError, isFetching } = useQuery({
    queryKey: ["reports"],
    queryFn: () => fetchReports(API_URL, apiToken ?? "", 500),
    enabled: !!apiToken,
    refetchInterval: 30_000,
  });

  const { data: groups = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: () => fetchGroups(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
  });

  const machines = useMemo(
    () => groupMachines(data?.reports ?? []),
    [data?.reports],
  );

  const filtered = useMemo(() => {
    if (!groupFilter) return machines;
    return machines.filter((m) => {
      const g = groupOf(m, groups);
      return g?.id === groupFilter;
    });
  }, [machines, groupFilter, groups]);

  const series = useMemo(
    () =>
      filtered.map((m, i) => ({
        key: seriesKey(m),
        name: m.name,
        color: PALETTE[i % PALETTE.length],
        deviceId: m.deviceId,
      })),
    [filtered],
  );

  const filteredRef = useRef(filtered);
  filteredRef.current = filtered;
  const metricsRef = useRef(metricsFor);
  metricsRef.current = metricsFor;

  const pushPoint = () => {
    const t = Date.now();
    const snap = liveSnapshot(filteredRef.current, metricsRef.current);
    setHistory((prev) => {
      const point: HistPoint = {
        t,
        time: formatClock(t),
        cpu: snap.cpu,
        ram: snap.ram,
        net: snap.net,
      };
      const cutoff = t - HISTORY_MS;
      return [...prev, point].filter((p) => p.t >= cutoff);
    });
  };

  useEffect(() => {
    setHistory([]);
    pushPoint();
    const id = setInterval(pushPoint, SAMPLE_MS);
    return () => clearInterval(id);
  }, [groupFilter, filtered.length]);

  const cpuData = useMemo(
    () => history.map((p) => ({ time: p.time, ...p.cpu })),
    [history],
  );
  const ramData = useMemo(
    () => history.map((p) => ({ time: p.time, ...p.ram })),
    [history],
  );
  const netData = useMemo(
    () => history.map((p) => ({ time: p.time, ...p.net })),
    [history],
  );

  const sidebarPcs = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const aOn = isOnline(a.deviceId) ?? a.latest.online ? 1 : 0;
      const bOn = isOnline(b.deviceId) ?? b.latest.online ? 1 : 0;
      if (aOn !== bOn) return bOn - aOn;
      return a.name.localeCompare(b.name);
    });
  }, [filtered, isOnline]);

  return (
    <DashboardShell
      title="Graphs"
      nav="graphs"
      role={session?.user?.role}
      widthClass="w-80"
      subtitle={
        <>
          {filtered.length} PC{filtered.length === 1 ? "" : "s"}
          {connected ? " · live" : " · connecting"}
        </>
      }
      sidebar={
        <>
          <div className="px-3 pt-3">
            <label className="sr-only" htmlFor="graphs-group-filter">
              Filter by group
            </label>
            <select
              id="graphs-group-filter"
              value={groupFilter}
              onChange={(e) => setGroupFilter(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
            >
              <option value="">All groups</option>
              {groups.map((g: Group) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>
          <nav className="mt-3 flex-1 overflow-y-auto px-2 pb-4">
            {isLoading && (
              <p className="px-2 py-6 text-center text-sm text-slate-400">
                Loading machines…
              </p>
            )}
            {!isLoading && sidebarPcs.length === 0 && (
              <p className="px-2 py-6 text-center text-sm text-slate-400">
                No PCs in this view.
              </p>
            )}
            <ul className="space-y-1">
              {sidebarPcs.map((m, i) => {
                const live = metricsFor(m.deviceId);
                const cpu = live?.cpu_percent ?? m.latest.resources?.cpu_percent;
                return (
                  <li key={m.key}>
                    <Link
                      href={`/reports/${encodeURIComponent(m.key)}`}
                      className="flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-slate-200 hover:bg-slate-900"
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <span
                          className="h-2 w-2 shrink-0 rounded-full"
                          style={{ background: PALETTE[i % PALETTE.length] }}
                        />
                        <StatusDot
                          online={isOnline(m.deviceId) ?? m.latest.online}
                        />
                        <span className="truncate text-sm">{m.name}</span>
                      </span>
                      <span className="shrink-0 text-xs text-slate-400">
                        {cpu != null ? `${Math.round(cpu)}%` : "—"}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </>
      }
      sidebarFooter={
        <button
          type="button"
          onClick={() => refreshAll()}
          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-100 hover:bg-slate-800 disabled:opacity-50"
          disabled={isFetching}
        >
          {isFetching ? "Refreshing…" : "Refresh"}
        </button>
      }
      header={
        <div className="border-b border-slate-200 bg-white/80 px-6 py-4 backdrop-blur">
          <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
            <span
              className={`h-2 w-2 rounded-full ${
                connected ? "bg-emerald-500" : "bg-slate-300"
              }`}
            />
            Live graphs
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            CPU, RAM, and network for every PC from live WebSocket samples
            (last 15 minutes). Offline PCs use the last saved report.
          </p>
        </div>
      }
    >
      <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
        {isError && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Failed to load reports from the API at {API_URL}. Is it running?
          </div>
        )}
        <UsageChart
          title="CPU usage"
          unit="%"
          domain={[0, 100]}
          data={cpuData}
          series={series}
          empty={filtered.length === 0}
        />
        <UsageChart
          title="RAM usage"
          unit="%"
          domain={[0, 100]}
          data={ramData}
          series={series}
          empty={filtered.length === 0}
        />
        <UsageChart
          title="Network usage"
          unit=" Mbps"
          data={netData}
          series={series}
          empty={filtered.length === 0}
          hint="Send + receive on the preferred NIC (live) or last report sample"
        />
      </div>
    </DashboardShell>
  );
}

function UsageChart({
  title,
  unit,
  domain,
  data,
  series,
  empty,
  hint,
}: {
  title: string;
  unit: string;
  domain?: [number, number];
  data: Record<string, string | number>[];
  series: { key: string; name: string; color: string }[];
  empty: boolean;
  hint?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
      <h3 className="text-sm font-medium text-slate-700">{title}</h3>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
      {empty ? (
        <p className="mt-8 text-center text-sm text-slate-500">
          Waiting for PCs…
        </p>
      ) : (
        <div className="mt-2 h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="time" fontSize={11} stroke="#94a3b8" minTickGap={32} />
              <YAxis
                fontSize={11}
                stroke="#94a3b8"
                domain={domain}
                unit={unit}
                width={56}
              />
              <Tooltip
                formatter={(value, name) => [
                  `${Number(value ?? 0).toFixed(1)}${unit}`,
                  String(name),
                ]}
              />
              <Legend />
              {series.map((s) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.name}
                  stroke={s.color}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
