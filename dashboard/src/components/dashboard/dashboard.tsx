"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  fetchGroups,
  fetchReports,
  fmtPercent,
  fmtRelative,
  Group,
  groupMachines,
  groupOf,
  machineMac,
  fmtAppVersion,
} from "@/lib/api";
import { DashboardShell } from "./shell";
import { MachineDetail } from "./machine-detail";
import { StatusDot } from "./status-dot";
import { PrintingBadge } from "./printing-badge";
import { LoadWarningBadge, isHighLiveLoad } from "./load-warning-badge";
import { UpdateAppsButton } from "./update-apps-button";
import { useRealtime } from "../realtime-provider";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export function Dashboard() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const { connected, isOnline, lastSeenFor, isPrinting, printingCount, metricsFor, refreshAll } =
    useRealtime();
  const [filter, setFilter] = useState("");
  const [groupFilter, setGroupFilter] = useState("");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const { data, isLoading, isError, isFetching } = useQuery({
    queryKey: ["reports"],
    queryFn: () => fetchReports(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
    refetchInterval: 30_000,
  });

  const { data: groups = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: () => fetchGroups(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
  });

  const reports = data?.reports ?? [];
  const machines = useMemo(() => groupMachines(reports), [reports]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return machines.filter((m) => {
      if (q && !m.name.toLowerCase().includes(q)) return false;
      if (groupFilter) {
        const g = groupOf(m, groups);
        if (!g || g.id !== groupFilter) return false;
      }
      return true;
    });
  }, [machines, filter, groupFilter, groups]);

  const selected =
    (selectedKey && filtered.find((m) => m.key === selectedKey)) ||
    filtered[0] ||
    null;

  return (
    <DashboardShell
      title="Fleet"
      nav="fleet"
      role={session?.user?.role}
      subtitle={
        <>
          {machines.length} machine{machines.length === 1 ? "" : "s"}
          {connected ? " · live" : " · connecting"} ·{" "}
          {reports.length} report{reports.length === 1 ? "" : "s"}
        </>
      }
      sidebar={
        <>
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

        <div className="px-3 pt-2">
          <label className="sr-only" htmlFor="pc-group-filter">
            Filter by group
          </label>
          <select
            id="pc-group-filter"
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
          {!isLoading && filtered.length === 0 && (
            <p className="px-2 py-6 text-center text-sm text-slate-400">
              No machines match.
            </p>
          )}
          <ul className="space-y-1">
            {filtered.map((m) => {
              const active = m.key === selected?.key;
              const live = metricsFor(m.deviceId);
              const cpu = live?.cpu_percent ?? m.latest.resources?.cpu_percent;
              const ram = live?.ram_percent ?? m.latest.resources?.ram_percent;
              const online = isOnline(m.deviceId) ?? m.latest.online;
              const printing = isPrinting(m.deviceId);
              const printCount = printingCount(m.deviceId);
              const lastSeen = lastSeenFor(m.deviceId, m.latest.created_at);
              return (
                <li key={m.key}>
                  <button
                    type="button"
                    onClick={() => setSelectedKey(m.key)}
                    className={`relative w-full rounded-lg px-3 py-2.5 text-left transition ${
                      active
                        ? "bg-blue-600 text-white shadow-sm shadow-blue-900/40"
                        : "text-slate-200 hover:bg-slate-900"
                    }`}
                  >
                    {(printing ||
                      isHighLiveLoad(live?.cpu_percent) ||
                      isHighLiveLoad(live?.ram_percent)) && (
                      <span className="absolute right-2 top-1.5 flex flex-col items-end gap-1">
                        {printing && <PrintingBadge count={printCount} />}
                        <LoadWarningBadge
                          cpu={live?.cpu_percent}
                          ram={live?.ram_percent}
                        />
                      </span>
                    )}
                    <div className="flex items-start justify-between gap-2">
                      <span className="flex items-center gap-1.5 truncate text-sm font-medium">
                        <StatusDot online={online} />
                        {m.name}
                      </span>
                      <span
                        className={`shrink-0 text-[11px] ${
                          active ? "text-blue-100" : "text-slate-500"
                        }`}
                      >
                        {fmtRelative(lastSeen)}
                      </span>
                    </div>
                    <div
                      className={`mt-1 flex items-center gap-2 text-[11px] ${
                        active ? "text-blue-100/90" : "text-slate-400"
                      }`}
                    >
                      <span
                        className={
                          isHighLiveLoad(live?.cpu_percent) ? "font-semibold text-red-300" : undefined
                        }
                      >
                        CPU {fmtPercent(cpu)}
                      </span>
                      <span aria-hidden>·</span>
                      <span
                        className={
                          isHighLiveLoad(live?.ram_percent) ? "font-semibold text-red-300" : undefined
                        }
                      >
                        RAM {fmtPercent(ram)}
                      </span>
                    </div>
                    {(m.latest.private_ip ||
                      machineMac(m.latest) ||
                      m.latest.app_version) && (
                      <div
                        className={`mt-1 truncate font-mono text-[10px] ${
                          active ? "text-blue-100/70" : "text-slate-500"
                        }`}
                      >
                        {m.latest.private_ip ?? "—"}
                        {machineMac(m.latest)
                          ? ` · ${machineMac(m.latest)}`
                          : ""}
                        {fmtAppVersion(m.latest.app_version)
                          ? ` · ${fmtAppVersion(m.latest.app_version)}`
                          : ""}
                      </div>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
        </>
      }
      sidebarFooter={
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => refreshAll()}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-100 hover:bg-slate-800 disabled:opacity-50"
            disabled={isFetching}
          >
            {isFetching ? "Refreshing…" : "Refresh"}
          </button>
          {session?.user?.role === "super_admin" && (
            <UpdateAppsButton apiUrl={API_URL} apiToken={apiToken ?? ""} />
          )}
        </div>
      }
      header={
        <div className="border-b border-slate-200 bg-white/80 px-6 py-4 backdrop-blur">
          {selected ? (
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
                  <StatusDot
                    online={isOnline(selected.deviceId) ?? selected.latest.online}
                    showLabel
                  />
                  {selected.name}
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  {selected.latest.os?.system ?? "—"}{" "}
                  {selected.latest.os?.release ?? ""}
                  <span className="mx-1.5 text-slate-300">·</span>
                  Last seen{" "}
                  {fmtRelative(
                    lastSeenFor(selected.deviceId, selected.latest.created_at),
                  )}
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
      }
    >
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
    </DashboardShell>
  );
}
