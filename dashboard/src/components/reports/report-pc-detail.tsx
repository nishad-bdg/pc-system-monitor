"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  decodeMachineKey,
  fetchReports,
  filtersForMachineKey,
  fmtBytes,
  fmtPercent,
  fmtRelative,
  groupMachines,
  maxDiskPercent,
  networkTotalBytes,
} from "@/lib/api";
import { MachineDetail } from "@/components/dashboard/machine-detail";
import { SignOutButton } from "@/components/dashboard/sign-out-button";
import { SidebarNav } from "@/components/sidebar-nav";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export function ReportPcDetail({ encodedKey }: { encodedKey: string }) {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const key = decodeMachineKey(encodedKey);
  const baseFilters = filtersForMachineKey(key);

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ["report-pc", key],
    queryFn: () =>
      fetchReports(API_URL, apiToken ?? "", 500, {
        ...baseFilters,
        ...(baseFilters.deviceId || baseFilters.pcName
          ? {}
          : { pcName: undefined }),
      }),
    enabled: !!apiToken,
  });

  const machine = useMemo(() => {
    const machines = groupMachines(data?.reports ?? []);
    return (
      machines.find((m) => m.key === key) ||
      machines.find((m) => m.deviceId && key === `id:${m.deviceId}`) ||
      machines[0] ||
      null
    );
  }, [data?.reports, key]);

  return (
    <div className="flex min-h-screen bg-[var(--bg)] text-[var(--ink)]">
      <aside className="flex w-72 shrink-0 flex-col border-r border-slate-800 bg-slate-950 text-slate-100">
        <div className="border-b border-slate-800 px-4 py-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
            System Info
          </p>
          <h1 className="mt-1 text-lg font-semibold tracking-tight text-white">
            PC detail
          </h1>
          <SidebarNav current="reports" />
        </div>
        <div className="flex-1 px-4 py-4 text-sm text-slate-300">
          <p className="font-medium text-white">{machine?.name ?? "…"}</p>
          {machine && (
            <ul className="mt-3 space-y-1 text-xs text-slate-400">
              <li>CPU {fmtPercent(machine.latest.resources?.cpu_percent)}</li>
              <li>RAM {fmtPercent(machine.latest.resources?.ram_percent)}</li>
              <li>Disk {fmtPercent(maxDiskPercent(machine.latest))}</li>
              <li>Net {fmtBytes(networkTotalBytes(machine.latest))}</li>
              <li>Seen {fmtRelative(machine.latest.created_at)}</li>
            </ul>
          )}
        </div>
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
          <Link
            href="/reports"
            className="text-xs font-medium text-blue-600 hover:underline"
          >
            ← Back to reports
          </Link>
          <h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-900">
            {machine?.name ?? "PC detail"}
          </h2>
          {machine && (
            <p className="mt-1 text-sm text-slate-500">
              {machine.latest.os?.system ?? "—"}{" "}
              {machine.latest.os?.release ?? ""}
              <span className="mx-1.5 text-slate-300">·</span>
              Last seen {fmtRelative(machine.latest.created_at)}
            </p>
          )}
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {isLoading && (
            <p className="text-center text-sm text-slate-500">Loading…</p>
          )}
          {isError && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              Failed to load PC reports.
            </div>
          )}
          {!isLoading && !isError && !machine && (
            <p className="text-center text-sm text-slate-500">
              No reports found for this PC.
            </p>
          )}
          {machine && <MachineDetail machine={machine} />}
        </div>
      </main>
    </div>
  );
}
