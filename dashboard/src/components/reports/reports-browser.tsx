"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  encodeMachineKey,
  fetchGroups,
  fetchReports,
  fmtBytes,
  fmtPercent,
  fmtRelative,
  groupMachines,
  groupOf,
  MachineSortKey,
  maxDiskPercent,
  networkTotalBytes,
  sortMachines,
} from "@/lib/api";
import { SignOutButton } from "@/components/dashboard/sign-out-button";
import { MachineDetail } from "@/components/dashboard/machine-detail";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const inputClass =
  "mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2";

function dateInputToTs(value: string, endOfDay: boolean): number | undefined {
  if (!value) return undefined;
  const d = new Date(value + (endOfDay ? "T23:59:59" : "T00:00:00"));
  const ts = d.getTime() / 1000;
  return Number.isFinite(ts) ? ts : undefined;
}

type AppliedFilters = {
  pcName: string;
  country: string;
  os: string;
  group: string;
  fromTs?: number;
  toTs?: number;
  sort: MachineSortKey;
  minCpu: number;
  minRam: number;
  minDisk: number;
};

const defaultApplied: AppliedFilters = {
  pcName: "",
  country: "",
  os: "",
  group: "",
  fromTs: undefined,
  toTs: undefined,
  sort: "cpu",
  minCpu: 0,
  minRam: 0,
  minDisk: 0,
};

export function ReportsBrowser() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;

  const [pcName, setPcName] = useState("");
  const [country, setCountry] = useState("");
  const [os, setOs] = useState("");
  const [group, setGroup] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [sort, setSort] = useState<MachineSortKey>("cpu");
  const [minCpu, setMinCpu] = useState("0");
  const [minRam, setMinRam] = useState("0");
  const [minDisk, setMinDisk] = useState("0");
  const [applied, setApplied] = useState<AppliedFilters>(defaultApplied);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const { data: groups = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: () => fetchGroups(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
  });

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["reports-browse", applied],
    queryFn: () =>
      fetchReports(API_URL, apiToken ?? "", 500, {
        pcName: applied.pcName || undefined,
        country: applied.country || undefined,
        os: applied.os || undefined,
        fromTs: applied.fromTs,
        toTs: applied.toTs,
      }),
    enabled: !!apiToken,
  });

  const machines = useMemo(() => {
    let list = groupMachines(data?.reports ?? []);
    list = list.filter((m) => {
      const r = m.latest;
      const cpu = r.resources?.cpu_percent ?? 0;
      const ram = r.resources?.ram_percent ?? 0;
      const disk = maxDiskPercent(r);
      if (cpu < applied.minCpu) return false;
      if (ram < applied.minRam) return false;
      if (disk < applied.minDisk) return false;
      if (applied.group) {
        const g = groupOf(m, groups);
        if (!g || g.id !== applied.group) return false;
      }
      return true;
    });
    return sortMachines(list, applied.sort);
  }, [data?.reports, applied, groups]);

  useEffect(() => {
    if (machines.length === 0) {
      setSelectedKey(null);
      return;
    }
    if (!selectedKey || !machines.some((m) => m.key === selectedKey)) {
      setSelectedKey(machines[0].key);
    }
  }, [machines, selectedKey]);

  const selected =
    machines.find((m) => m.key === selectedKey) ?? machines[0] ?? null;

  function onApply(e: FormEvent) {
    e.preventDefault();
    setApplied({
      pcName: pcName.trim(),
      country: country.trim(),
      os: os.trim(),
      group,
      fromTs: dateInputToTs(fromDate, false),
      toTs: dateInputToTs(toDate, true),
      sort,
      minCpu: Number(minCpu) || 0,
      minRam: Number(minRam) || 0,
      minDisk: Number(minDisk) || 0,
    });
  }

  function onClear() {
    setPcName("");
    setCountry("");
    setOs("");
    setGroup("");
    setFromDate("");
    setToDate("");
    setSort("cpu");
    setMinCpu("0");
    setMinRam("0");
    setMinDisk("0");
    setApplied(defaultApplied);
  }

  return (
    <div className="flex min-h-screen bg-[var(--bg)] text-[var(--ink)]">
      <aside className="flex w-80 shrink-0 flex-col border-r border-slate-800 bg-slate-950 text-slate-100">
        <div className="border-b border-slate-800 px-4 py-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
            System Info
          </p>
          <h1 className="mt-1 text-lg font-semibold tracking-tight text-white">
            Reports
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            {machines.length} PC{machines.length === 1 ? "" : "s"} · sorted by{" "}
            {applied.sort.replace("_", " ")}
          </p>
          <div className="mt-3 flex gap-2 text-xs">
            <Link
              href="/dashboard"
              className="rounded-md px-2 py-1 font-medium text-slate-300 hover:bg-slate-900 hover:text-white"
            >
              Fleet
            </Link>
            <span className="rounded-md bg-blue-600 px-2 py-1 font-medium text-white">
              Reports
            </span>
            <Link
              href="/api-keys"
              className="rounded-md px-2 py-1 font-medium text-slate-300 hover:bg-slate-900 hover:text-white"
            >
              API Keys
            </Link>
            <Link
              href="/groups"
              className="rounded-md px-2 py-1 font-medium text-slate-300 hover:bg-slate-900 hover:text-white"
            >
              Groups
            </Link>
          </div>
        </div>

        <form
          onSubmit={onApply}
          className="space-y-3 overflow-y-auto border-b border-slate-800 px-3 py-3"
        >
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Filters
          </p>
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
              value={group}
              onChange={(e) => setGroup(e.target.value)}
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
            Usage
          </p>
          <label className="block text-xs text-slate-400">
            Sort by (highest first)
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as MachineSortKey)}
              className={inputClass}
            >
              <option value="cpu">Most CPU</option>
              <option value="ram">Most RAM</option>
              <option value="disk">Most disk space used</option>
              <option value="network">Most network usage</option>
              <option value="last_seen">Last seen</option>
            </select>
          </label>
          <div className="grid grid-cols-3 gap-2">
            <label className="block text-xs text-slate-400">
              Min CPU %
              <input
                type="number"
                min={0}
                max={100}
                value={minCpu}
                onChange={(e) => setMinCpu(e.target.value)}
                className={inputClass}
              />
            </label>
            <label className="block text-xs text-slate-400">
              Min RAM %
              <input
                type="number"
                min={0}
                max={100}
                value={minRam}
                onChange={(e) => setMinRam(e.target.value)}
                className={inputClass}
              />
            </label>
            <label className="block text-xs text-slate-400">
              Min disk %
              <input
                type="number"
                min={0}
                max={100}
                value={minDisk}
                onChange={(e) => setMinDisk(e.target.value)}
                className={inputClass}
              />
            </label>
          </div>

          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              className="flex-1 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500"
            >
              Apply
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

        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {isLoading && (
            <p className="px-2 py-6 text-center text-sm text-slate-400">
              Loading…
            </p>
          )}
          {!isLoading && machines.length === 0 && (
            <p className="px-2 py-6 text-center text-sm text-slate-400">
              No PCs match.
            </p>
          )}
          <ul className="space-y-1">
            {machines.map((m) => {
              const active = m.key === selected?.key;
              const r = m.latest;
              const disk = maxDiskPercent(r);
              const net = networkTotalBytes(r);
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
                        {fmtRelative(r.created_at)}
                      </span>
                    </div>
                    <div
                      className={`mt-1 grid grid-cols-2 gap-x-2 text-[11px] ${
                        active ? "text-blue-100/90" : "text-slate-400"
                      }`}
                    >
                      <span>CPU {fmtPercent(r.resources?.cpu_percent)}</span>
                      <span>RAM {fmtPercent(r.resources?.ram_percent)}</span>
                      <span>Disk {fmtPercent(disk)}</span>
                      <span>Net {fmtBytes(net)}</span>
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
                  <span className="mx-1.5 text-slate-300">·</span>
                  <Link
                    href={`/reports/${encodeMachineKey(selected.key)}`}
                    className="text-blue-600 hover:underline"
                  >
                    Open permalink
                  </Link>
                </p>
              </div>
              <div className="flex flex-wrap gap-3 text-xs text-slate-500">
                <span>
                  CPU {fmtPercent(selected.latest.resources?.cpu_percent)}
                </span>
                <span>
                  RAM {fmtPercent(selected.latest.resources?.ram_percent)}
                </span>
                <span>Disk {fmtPercent(maxDiskPercent(selected.latest))}</span>
                <span>
                  Net {fmtBytes(networkTotalBytes(selected.latest))}
                </span>
              </div>
            </div>
          ) : (
            <div>
              <h2 className="text-xl font-semibold text-slate-900">
                No machine selected
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Adjust filters or wait for reports.
              </p>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          {isError && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              Failed to load reports from {API_URL}.
            </div>
          )}
          {selected && <MachineDetail machine={selected} />}
          {!isLoading && !isError && !selected && (
            <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/60 text-sm text-slate-500">
              No PCs match these filters.
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
