"use client";

import Link from "next/link";

export type NavKey = "fleet" | "reports" | "keys" | "groups" | "export";

const NAV_ITEMS: { key: NavKey; label: string; href: string }[] = [
  { key: "fleet", label: "Fleet", href: "/dashboard" },
  { key: "reports", label: "Reports", href: "/reports" },
  { key: "keys", label: "API Keys", href: "/api-keys" },
  { key: "groups", label: "Groups", href: "/groups" },
  { key: "export", label: "Export", href: "/reports/export" },
];

/** Sidebar navigation pills (wraps on narrow sidebars, no overflow). */
export function SidebarNav({ current }: { current: NavKey }) {
  return (
    <nav className="mt-3 flex flex-wrap gap-1.5 text-xs">
      {NAV_ITEMS.map((item) => {
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
