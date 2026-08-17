"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
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
} from "@/lib/api";
import { DashboardShell } from "@/components/dashboard/shell";
import { StatusDot } from "@/components/dashboard/status-dot";
import { deviceIdsOf } from "@/components/dashboard/sidebar-remote-actions";
import { useRealtime } from "@/components/realtime-provider";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const ONLINE_COLOR = "#10b981";
const OFFLINE_COLOR = "#ef4444";
const INSTALLED_COLOR = "#2563eb";

const HISTORY_MS = 15 * 60 * 1000;
const SAMPLE_MS = 5_000;

type HistoryPoint = {
  t: number;
  label: string;
  installed: number;
  online: number;
  offline: number;
};

function formatClock(ts: number): string {
  return new Date(ts).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function FleetOverview() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const { connected, isOnline, refreshAll } = useRealtime();
  const [groupFilter, setGroupFilter] = useState("");
  const [history, setHistory] = useState<HistoryPoint[]>([]);

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

  const counts = useMemo(() => {
    let online = 0;
    let offline = 0;
    for (const m of filtered) {
      if (isOnline(m.deviceId) ?? m.latest.online) online += 1;
      else offline += 1;
    }
    return { installed: filtered.length, online, offline };
  }, [filtered, isOnline]);

  const countsRef = useRef(counts);
  countsRef.current = counts;

  const pushPoint = (next = countsRef.current) => {
    const t = Date.now();
    setHistory((prev) => {
      const last = prev[prev.length - 1];
      if (
        last &&
        t - last.t < 400 &&
        last.online === next.online &&
        last.offline === next.offline &&
        last.installed === next.installed
      ) {
        return prev;
      }
      const point: HistoryPoint = {
        t,
        label: formatClock(t),
        installed: next.installed,
        online: next.online,
        offline: next.offline,
      };
      const cutoff = t - HISTORY_MS;
      return [...prev, point].filter((p) => p.t >= cutoff);
    });
  };

  useEffect(() => {
    pushPoint(counts);
  }, [counts.installed, counts.online, counts.offline]);

  useEffect(() => {
    setHistory([]);
  }, [groupFilter]);

  useEffect(() => {
    const id = setInterval(() => pushPoint(), SAMPLE_MS);
    return () => clearInterval(id);
  }, []);

  const pieData = useMemo(
    () => [
      { name: "Online", value: counts.online, color: ONLINE_COLOR },
      { name: "Offline", value: counts.offline, color: OFFLINE_COLOR },
    ],
    [counts.online, counts.offline],
  );

  const onlinePct =
    counts.installed > 0
      ? Math.round((counts.online / counts.installed) * 100)
      : 0;

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
      title="Overview"
      nav="overview"
      role={session?.user?.role}
      widthClass="w-80"
      connectDeviceIds={deviceIdsOf(filtered)}
      subtitle={
        <>
          {counts.installed} installed
          {connected ? " · live" : " · connecting"}
        </>
      }
      sidebar={
        <>
          <div className="px-3 pt-3">
            <div className="mb-3 flex items-center justify-between text-xs">
              <span className="font-semibold uppercase tracking-[0.12em] text-slate-400">
                Fleet status
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
            <label className="sr-only" htmlFor="overview-group-filter">
              Filter by group
            </label>
            <select
              id="overview-group-filter"
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
                No machines yet.
              </p>
            )}
            <ul className="space-y-1">
              {sidebarPcs.map((m) => {
                const online = isOnline(m.deviceId) ?? m.latest.online;
                return (
                  <li key={m.key}>
                    <Link
                      href={`/reports/${encodeURIComponent(m.key)}`}
                      className="flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-slate-200 hover:bg-slate-900"
                    >
                      <span className="flex min-w-0 items-center gap-1.5 truncate text-sm font-medium">
                        <StatusDot online={online} />
                        <span className="truncate">{m.name}</span>
                      </span>
                      <span className="shrink-0 text-[11px] text-slate-500">
                        {online ? "Online" : "Offline"}
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
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
                <span
                  className={`h-2 w-2 rounded-full ${
                    connected ? "bg-emerald-500" : "bg-slate-300"
                  }`}
                />
                Live fleet
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Installed, online, and offline counts update over the WebSocket
                as PCs connect or drop.
              </p>
            </div>
            <p className="text-xs text-slate-400">{onlinePct}% online</p>
          </div>
        </div>
      }
    >
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {isError && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Failed to load reports from the API at {API_URL}. Is it running?
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard
            label="Total installed"
            value={counts.installed}
            hint="PCs that have sent a report"
            color={INSTALLED_COLOR}
          />
          <StatCard
            label="Total online"
            value={counts.online}
            hint="Live agent socket or heartbeat"
            color={ONLINE_COLOR}
          />
          <StatCard
            label="Total offline"
            value={counts.offline}
            hint="No live presence right now"
            color={OFFLINE_COLOR}
          />
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-5">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50 lg:col-span-2">
            <h3 className="text-sm font-medium text-slate-700">
              Online vs offline
            </h3>
            {counts.installed === 0 ? (
              <p className="mt-8 text-center text-sm text-slate-500">
                Waiting for the first report…
              </p>
            ) : (
              <div className="mt-2 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={58}
                      outerRadius={88}
                      paddingAngle={counts.online && counts.offline ? 2 : 0}
                    >
                      {pieData.map((row) => (
                        <Cell key={row.name} fill={row.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value) => [
                        `${value} PC${value === 1 ? "" : "s"}`,
                        "",
                      ]}
                    />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50 lg:col-span-3">
            <h3 className="text-sm font-medium text-slate-700">
              Live online / offline (last 15 min)
            </h3>
            {history.length === 0 ? (
              <p className="mt-8 text-center text-sm text-slate-500">
                Chart starts as soon as presence events arrive.
              </p>
            ) : (
              <div className="mt-2 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={history}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis
                      dataKey="label"
                      fontSize={10}
                      stroke="#94a3b8"
                      interval="preserveStartEnd"
                      minTickGap={40}
                    />
                    <YAxis
                      allowDecimals={false}
                      fontSize={11}
                      stroke="#94a3b8"
                      width={32}
                    />
                    <Tooltip
                      formatter={(value, name) => [
                        `${value} PC${value === 1 ? "" : "s"}`,
                        String(name),
                      ]}
                    />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="online"
                      name="Online"
                      stroke={ONLINE_COLOR}
                      fill={ONLINE_COLOR}
                      fillOpacity={0.18}
                      strokeWidth={2}
                      isAnimationActive={false}
                    />
                    <Area
                      type="monotone"
                      dataKey="offline"
                      name="Offline"
                      stroke={OFFLINE_COLOR}
                      fill={OFFLINE_COLOR}
                      fillOpacity={0.12}
                      strokeWidth={2}
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardShell>
  );
}

function StatCard({
  label,
  value,
  hint,
  color,
}: {
  label: string;
  value: number;
  hint: string;
  color: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm shadow-slate-200/50">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
        {label}
      </p>
      <p className="mt-2 text-4xl font-semibold tabular-nums text-slate-900">
        {value}
      </p>
      <p className="mt-2 flex items-center gap-2 text-xs text-slate-500">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: color }}
        />
        {hint}
      </p>
    </div>
  );
}
