"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  fetchReports,
  fmtPercent,
  fmtRelative,
  groupMachines,
} from "@/lib/api";
import { SignOutButton } from "./sign-out-button";
import { MachineDetail } from "./machine-detail";

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
          <div className="mt-3 flex gap-2 text-xs">
            <span className="rounded-md bg-blue-600 px-2 py-1 font-medium text-white">
              Fleet
            </span>
            <Link
              href="/reports"
              className="rounded-md px-2 py-1 font-medium text-slate-300 hover:bg-slate-900 hover:text-white"
            >
              Reports
            </Link>
          </div>
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
