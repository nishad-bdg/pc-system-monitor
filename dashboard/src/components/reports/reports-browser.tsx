"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  encodeMachineKey,
  fetchReports,
  fmtPercent,
  fmtRelative,
  groupMachines,
} from "@/lib/api";
import { SignOutButton } from "@/components/dashboard/sign-out-button";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

function dateInputToTs(value: string, endOfDay: boolean): number | undefined {
  if (!value) return undefined;
  const d = new Date(value + (endOfDay ? "T23:59:59" : "T00:00:00"));
  const ts = d.getTime() / 1000;
  return Number.isFinite(ts) ? ts : undefined;
}

export function ReportsBrowser() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;

  const [pcName, setPcName] = useState("");
  const [country, setCountry] = useState("");
  const [os, setOs] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [applied, setApplied] = useState({
    pcName: "",
    country: "",
    os: "",
    fromTs: undefined as number | undefined,
    toTs: undefined as number | undefined,
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

  const machines = useMemo(
    () => groupMachines(data?.reports ?? []),
    [data?.reports],
  );

  function onApply(e: FormEvent) {
    e.preventDefault();
    setApplied({
      pcName: pcName.trim(),
      country: country.trim(),
      os: os.trim(),
      fromTs: dateInputToTs(fromDate, false),
      toTs: dateInputToTs(toDate, true),
    });
  }

  function onClear() {
    setPcName("");
    setCountry("");
    setOs("");
    setFromDate("");
    setToDate("");
    setApplied({
      pcName: "",
      country: "",
      os: "",
      fromTs: undefined,
      toTs: undefined,
    });
  }

  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--ink)]">
      <header className="border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-6 py-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-blue-600">
              System Info
            </p>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900">
              Reports
            </h1>
            <p className="mt-0.5 text-sm text-slate-500">
              Filter by date and machine · one row per PC
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/dashboard"
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Fleet
            </Link>
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              disabled={isFetching}
            >
              {isFetching ? "Refreshing…" : "Refresh"}
            </button>
            <SignOutButton variant="light" />
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl space-y-6 px-6 py-6">
        <form
          onSubmit={onApply}
          className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm shadow-slate-200/50"
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <label className="block text-xs font-medium text-slate-600">
              From
              <input
                type="date"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              To
              <input
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              PC name
              <input
                value={pcName}
                onChange={(e) => setPcName(e.target.value)}
                placeholder="Contains…"
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              Country
              <input
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                placeholder="Name or code"
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              OS
              <input
                value={os}
                onChange={(e) => setOs(e.target.value)}
                placeholder="Darwin, Windows…"
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/30"
              />
            </label>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="submit"
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              Apply filters
            </button>
            <button
              type="button"
              onClick={onClear}
              className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Clear
            </button>
            <p className="self-center text-xs text-slate-500">
              {machines.length} PC{machines.length === 1 ? "" : "s"} ·{" "}
              {data?.total ?? 0} report{(data?.total ?? 0) === 1 ? "" : "s"}
            </p>
          </div>
        </form>

        {isError && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Failed to load reports from {API_URL}.
          </div>
        )}

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm shadow-slate-200/60">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">PC</th>
                <th className="px-4 py-3">Last seen</th>
                <th className="px-4 py-3">OS</th>
                <th className="px-4 py-3">Country</th>
                <th className="px-4 py-3">IP</th>
                <th className="px-4 py-3">CPU</th>
                <th className="px-4 py-3">RAM</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-slate-500">
                    Loading…
                  </td>
                </tr>
              )}
              {!isLoading && machines.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-slate-500">
                    No PCs match these filters.
                  </td>
                </tr>
              )}
              {machines.map((m) => {
                const r = m.latest;
                return (
                  <tr key={m.key} className="hover:bg-slate-50/80">
                    <td className="px-4 py-3">
                      <Link
                        href={`/reports/${encodeMachineKey(m.key)}`}
                        className="font-medium text-blue-700 hover:underline"
                      >
                        {m.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {fmtRelative(r.created_at)}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {r.os?.system ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {r.location?.country ?? r.location?.country_code ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {r.private_ip ?? "—"}
                      {r.public_ip ? ` / ${r.public_ip}` : ""}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {fmtPercent(r.resources?.cpu_percent)}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {fmtPercent(r.resources?.ram_percent)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
