"use client";

import Link from "next/link";

export type NavKey =
  | "overview"
  | "graphs"
  | "fleet"
  | "reports"
  | "prints"
  | "keys"
  | "groups"
  | "export"
  | "users";

const BASE_NAV_ITEMS: { key: NavKey; label: string; href: string; superOnly?: boolean }[] = [
  { key: "overview", label: "Overview", href: "/overview" },
  { key: "graphs", label: "Graphs", href: "/graphs" },
  { key: "fleet", label: "Fleet", href: "/dashboard" },
  { key: "reports", label: "Reports", href: "/reports" },
  { key: "prints", label: "Print Activity", href: "/print-jobs" },
  { key: "export", label: "Export", href: "/reports/export" },
  { key: "groups", label: "Groups", href: "/groups" },
  { key: "keys", label: "API Keys", href: "/api-keys", superOnly: true },
  { key: "users", label: "Users", href: "/users", superOnly: true },
];

/** Top-bar page navigation (horizontal, scrolls on small screens). */
export function SidebarNav({
  current,
  role,
}: {
  current: NavKey;
  role?: string;
}) {
  const items = BASE_NAV_ITEMS.filter((i) => !i.superOnly || role === "super_admin");
  return (
    <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto text-sm">
      {items.map((item) => {
        const active = item.key === current;
        return active ? (
          <span
            key={item.key}
            className="shrink-0 rounded-lg bg-blue-600 px-3 py-1.5 font-medium text-white"
          >
            {item.label}
          </span>
        ) : (
          <Link
            key={item.key}
            href={item.href}
            className="shrink-0 rounded-lg px-3 py-1.5 font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
