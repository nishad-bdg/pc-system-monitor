"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  decodeMachineKey,
  fetchReports,
  filtersForMachineKey,
  fmtRelative,
  groupMachines,
} from "@/lib/api";
import { MachineDetail } from "@/components/dashboard/machine-detail";
import { SignOutButton } from "@/components/dashboard/sign-out-button";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export function ReportPcDetail({ encodedKey }: { encodedKey: string }) {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const key = decodeMachineKey(encodedKey);
  const baseFilters = filtersForMachineKey(key);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["report-pc", key],
    queryFn: () =>
      fetchReports(API_URL, apiToken ?? "", 500, {
        ...baseFilters,
        // For mac-only keys without device/name, load broadly then group-match.
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
    <div className="min-h-screen bg-[var(--bg)] text-[var(--ink)]">
      <header className="border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-6 py-4">
          <div>
            <Link
              href="/reports"
              className="text-xs font-medium text-blue-600 hover:underline"
            >
              ← Back to reports
            </Link>
            <h1 className="mt-1 text-xl font-semibold tracking-tight text-slate-900">
              {machine?.name ?? "PC detail"}
            </h1>
            {machine && (
              <p className="mt-0.5 text-sm text-slate-500">
                {machine.latest.os?.system ?? "—"}{" "}
                {machine.latest.os?.release ?? ""}
                <span className="mx-1.5 text-slate-300">·</span>
                Last seen {fmtRelative(machine.latest.created_at)}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/dashboard"
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Fleet
            </Link>
            <SignOutButton variant="light" />
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-6">
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
    </div>
  );
}
