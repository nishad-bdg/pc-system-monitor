"use client";

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
  BarChart,
  Bar,
  Legend,
} from "recharts";
import { fetchReports, fmtBytes, fmtPercent, fmtTime, Report } from "@/lib/api";
import { SignOutButton } from "./sign-out-button";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export function Dashboard() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["reports"],
    queryFn: () => fetchReports(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
    refetchInterval: 30_000,
  });

  const reports = data?.reports ?? [];
  const host = reports[reports.length - 1];

  const timeSeries = reports.map((r) => ({
    time: fmtTime(r.created_at),
    cpu: r.resources?.cpu_percent ?? 0,
    ram: r.resources?.ram_percent ?? 0,
    swap: r.resources?.swap_percent ?? 0,
  }));

  const nameSeries = reports.map((r) => ({
    name: r.os?.hostname ?? r.public_ip ?? r._id?.slice(-4) ?? "?",
    cpu: r.resources?.cpu_percent ?? 0,
    ram: r.resources?.ram_percent ?? 0,
  }));

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">
            System Monitoring
          </h1>
          <p className="text-sm text-gray-500">
            {reports.length} report{reports.length === 1 ? "" : "s"} ·{" "}
            {host?.os?.hostname ?? "—"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => refetch()}
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Refresh
          </button>
          <SignOutButton />
        </div>
      </div>

      {isLoading && (
        <p className="mt-10 text-center text-gray-500">Loading reports…</p>
      )}
      {isError && (
        <div className="mt-10 rounded-lg bg-red-50 p-4 text-sm text-red-700">
          Failed to load reports from the API at {API_URL}. Is it running?
        </div>
      )}

      {!isLoading && !isError && (
        <div className="mt-8 space-y-8">
          {host?.resources && (
            <div className="grid gap-4 sm:grid-cols-3">
              <StatCard
                label="CPU usage"
                value={fmtPercent(host.resources.cpu_percent)}
                sub={`${host.resources.cpu_count ?? "?"} cores · ${
                  host.resources.cpu_freq_mhz ?? "?"
                } MHz`}
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

          {host?.location && (
            <div className="rounded-xl border border-gray-200 bg-white p-5">
              <h2 className="text-sm font-medium text-gray-700">Location</h2>
              <p className="mt-1 text-sm text-gray-500">
                {host.location.city ?? "—"}, {host.location.region ?? "—"},{" "}
                {host.location.country ?? "—"} ({host.location.country_code ?? "—"})
                <span className="mx-1 text-gray-300">·</span>
                ISP: {host.location.isp ?? "—"}
                <span className="mx-1 text-gray-300">·</span>
                {host.location.lat ?? "—"}, {host.location.lon ?? "—"}
              </p>
            </div>
          )}

          {host?.os && (
            <div className="rounded-xl border border-gray-200 bg-white p-5">
              <h2 className="text-sm font-medium text-gray-700">Machine</h2>
              <p className="mt-1 text-sm text-gray-500">
                {host.os.system ?? "—"} {host.os.release ?? "—"} ·{" "}
                {host.os.machine ?? "—"} · {host.os.platform_detail ?? "—"}
              </p>
            </div>
          )}

          <ChartCard title="CPU / RAM / Swap over time">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={timeSeries}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" fontSize={11} />
                <YAxis domain={[0, 100]} fontSize={11} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="cpu" stroke="#3b82f6" name="CPU %" />
                <Line
                  type="monotone"
                  dataKey="ram"
                  stroke="#10b981"
                  name="RAM %"
                />
                <Line
                  type="monotone"
                  dataKey="swap"
                  stroke="#f59e0b"
                  name="Swap %"
                />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard title="Per-machine resource usage">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={nameSeries}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" fontSize={11} />
                <YAxis domain={[0, 100]} fontSize={11} />
                <Tooltip />
                <Legend />
                <Bar dataKey="cpu" fill="#3b82f6" name="CPU %" radius={[3, 3, 0, 0]} />
                <Bar dataKey="ram" fill="#10b981" name="RAM %" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-4 py-3">Time</th>
                  <th className="px-4 py-3">Host</th>
                  <th className="px-4 py-3">IP</th>
                  <th className="px-4 py-3">Country</th>
                  <th className="px-4 py-3">CPU</th>
                  <th className="px-4 py-3">RAM</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {reports.slice().reverse().map((r) => (
                  <ReportRow key={r._id ?? `${r.created_at}-${r.public_ip}`} r={r} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5">
      <p className="text-xs uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-1 text-3xl font-semibold text-gray-900">{value}</p>
      <p className="mt-1 text-sm text-gray-500">{sub}</p>
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
    <div className="rounded-xl border border-gray-200 bg-white p-5">
      <h2 className="mb-4 text-sm font-medium text-gray-700">{title}</h2>
      {children}
    </div>
  );
}

function ReportRow({ r }: { r: Report }) {
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-3 text-gray-600">{fmtTime(r.created_at)}</td>
      <td className="px-4 py-3 font-medium text-gray-900">
        {r.os?.hostname ?? "—"}
      </td>
      <td className="px-4 py-3 text-gray-600">
        {r.private_ip ?? "—"}
        {r.public_ip ? ` / ${r.public_ip}` : ""}
      </td>
      <td className="px-4 py-3 text-gray-600">
        {r.location?.country ?? "—"}
      </td>
      <td className="px-4 py-3 text-gray-600">
        {fmtPercent(r.resources?.cpu_percent)}
      </td>
      <td className="px-4 py-3 text-gray-600">
        {fmtPercent(r.resources?.ram_percent)}
      </td>
    </tr>
  );
}