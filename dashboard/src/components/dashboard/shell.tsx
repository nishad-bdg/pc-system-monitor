"use client";

import {
  createContext,
  ReactNode,
  useContext,
  useMemo,
  useState,
} from "react";
import { UserNav } from "./user-nav";
import { SidebarNav, NavKey } from "@/components/sidebar-nav";

const SidebarDrawerContext = createContext<{
  setOpen: (open: boolean) => void;
}>({ setOpen: () => {} });

export function useSidebarDrawer() {
  return useContext(SidebarDrawerContext);
}

export function DetailBackButton({
  label,
  onClick,
  className = "",
}: {
  label: string;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`mb-1 inline-flex items-center text-xs font-medium text-blue-600 hover:underline ${className}`}
    >
      ← {label}
    </button>
  );
}

/** Opens the mobile PC list. Render inside DashboardShell header/children. */
export function OpenSidebarBackButton({
  label,
  className = "",
}: {
  label: string;
  className?: string;
}) {
  const { setOpen } = useSidebarDrawer();
  return (
    <DetailBackButton
      label={label}
      className={className}
      onClick={() => setOpen(true)}
    />
  );
}

/** Select a sidebar row and close the mobile drawer so details are visible. */
export function SidebarSelectButton({
  onSelect,
  className,
  children,
}: {
  onSelect: () => void;
  className?: string;
  children: ReactNode;
}) {
  const { setOpen } = useSidebarDrawer();
  return (
    <button
      type="button"
      className={className}
      onClick={() => {
        onSelect();
        setOpen(false);
      }}
    >
      {children}
    </button>
  );
}

/**
 * Shared app shell: dark collapsible sidebar (slide-over on mobile) for the
 * page's PC/filter list, plus a sticky top bar with page navigation and
 * the user profile on the right.
 */
export function DashboardShell({
  title,
  subtitle,
  nav,
  role,
  sidebar,
  sidebarFooter,
  header,
  children,
  widthClass = "w-72",
}: {
  title: string;
  subtitle?: ReactNode;
  nav: NavKey;
  role?: string;
  sidebar: ReactNode;
  sidebarFooter?: ReactNode;
  header: ReactNode;
  children: ReactNode;
  widthClass?: string;
}) {
  const [open, setOpen] = useState(false);
  const drawer = useMemo(() => ({ setOpen }), []);

  return (
    <SidebarDrawerContext.Provider value={drawer}>
      <div className="flex min-h-screen bg-[var(--bg)] text-[var(--ink)]">
        {open && (
          <button
            type="button"
            aria-label="Close menu"
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-30 bg-slate-950/60 lg:hidden"
          />
        )}

        <aside
          className={`fixed inset-y-0 left-0 z-40 flex ${widthClass} shrink-0 flex-col border-r border-slate-800 bg-slate-950 text-slate-100 transition-transform duration-200 lg:static lg:translate-x-0 ${
            open ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="border-b border-slate-800 px-4 py-5">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                {title}
              </p>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-slate-400 hover:text-white lg:hidden"
                aria-label="Close menu"
              >
                ✕
              </button>
            </div>
            {subtitle && (
              <p className="mt-1 text-xs text-slate-400">{subtitle}</p>
            )}
          </div>

          <div className="flex-1 overflow-y-auto">{sidebar}</div>

          {sidebarFooter && (
            <div className="border-t border-slate-800 p-3">{sidebarFooter}</div>
          )}
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="relative z-50 flex items-center gap-3 border-b border-slate-200 bg-white/80 px-4 py-2.5 backdrop-blur lg:px-6">
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="shrink-0 rounded-lg border border-slate-300 p-2 text-slate-600 hover:bg-slate-100 lg:hidden"
              aria-label="Open menu"
            >
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 6h16M4 12h16M4 18h16"
                />
              </svg>
            </button>

            <p className="hidden shrink-0 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400 sm:block">
              System Info
            </p>

            <SidebarNav current={nav} role={role} />

            <div className="ml-auto shrink-0">
              <UserNav />
            </div>
          </div>

          {header}

          <div className="flex-1 overflow-y-auto">{children}</div>
        </main>
      </div>
    </SidebarDrawerContext.Provider>
  );
}
