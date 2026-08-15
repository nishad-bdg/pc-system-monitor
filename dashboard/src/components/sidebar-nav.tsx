"use client";

import Link from "next/link";

export type NavKey =
  | "fleet"
  | "reports"
  | "prints"
  | "keys"
  | "groups"
  | "export"
  | "users";

const BASE_NAV_ITEMS: { key: NavKey; label: string; href: string; superOnly?: boolean }[] = [
  { key: "fleet", label: "Fleet", href: "/dashboard" },
  { key: "reports", label: "Reports", href: "/reports" },
  { key: "prints", label: "Print Activity", href: "/print-jobs" },
  { key: "export", label: "Export", href: "/reports/export" },
  { key: "groups", label: "Groups", href: "/groups" },
  { key: "keys", label: "API Keys", href: "/api-keys", superOnly: true },
  { key: "users", label: "Users", href: "/users", superOnly: true },
];

/** Sidebar navigation pills (wraps on narrow sidebars, no overflow). */
export function SidebarNav({
  current,
  role,
}: {
  current: NavKey;
  role?: string;
}) {
  const items = BASE_NAV_ITEMS.filter((i) => !i.superOnly || role === "super_admin");
  return (
    <nav className="mt-3 flex flex-wrap gap-1.5 text-xs">
      {items.map((item) => {
        const active = item.key === current;
        return active ? (
          <span
            key={item.key}
            className="rounded-md bg-blue-600 px-2.5 py-1.5 font-medium text-white"
          >
            {item.label}
          </span>
        ) : (
          <Link
            key={item.key}
            href={item.href}
            className="rounded-md px-2.5 py-1.5 font-medium text-slate-300 hover:bg-slate-900 hover:text-white"
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
