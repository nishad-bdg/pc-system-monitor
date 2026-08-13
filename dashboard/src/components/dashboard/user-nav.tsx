"use client";

import { signOut } from "next-auth/react";
import { useState } from "react";
import { useSession } from "next-auth/react";

const ROLE_LABELS: Record<string, string> = {
  super_admin: "Super admin",
  admin: "Admin",
  user: "User",
};

/** Top-bar profile menu: avatar dropdown with change-password + sign out. */
export function UserNav({ apiUrl }: { apiUrl?: string }) {
  const { data: session } = useSession();
  const [menuOpen, setMenuOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const username = session?.user?.name ?? "—";
  const role = session?.user?.role ?? "";
  const apiToken = session?.user?.apiToken;
  const baseUrl = apiUrl ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    if (next !== confirm) {
      setError("New passwords do not match");
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(`${baseUrl}/auth/change-password`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiToken ?? ""}`,
        },
        body: JSON.stringify({ current_password: current, new_password: next }),
        cache: "no-store",
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail ?? "Could not change password");
        return;
      }
      setMessage("Password changed. Re-sign in on next login.");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch {
      setError("Could not reach the API");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="relative">
        <button
          type="button"
          onClick={() => setMenuOpen((o) => !o)}
          className="flex items-center gap-2 rounded-full border border-slate-200 bg-white py-1 pl-1 pr-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 lg:pr-3"
          aria-expanded={menuOpen}
          aria-haspopup="menu"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
            {(username[0] ?? "?").toUpperCase()}
          </span>
          <span className="hidden max-w-44 truncate sm:block">{username}</span>
          <svg
            className={`h-3.5 w-3.5 text-slate-400 transition-transform ${
              menuOpen ? "rotate-180" : ""
            }`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="m6 9 6 6 6-6"
            />
          </svg>
        </button>

        {menuOpen && (
          <>
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setMenuOpen(false)}
              className="fixed inset-0 z-40 cursor-default"
            />
            <div
              role="menu"
              className="absolute right-0 top-full z-50 mt-2 w-64 max-h-[calc(100vh-5rem)] overflow-y-auto rounded-xl border border-slate-200 bg-white p-3 shadow-xl"
            >
              <div className="flex items-center gap-3 border-b border-slate-100 pb-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white">
                  {(username[0] ?? "?").toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-slate-900">
                    {username}
                  </p>
                  <p
                    className={`text-[11px] font-semibold uppercase tracking-wide ${
                      role === "super_admin"
                        ? "text-violet-600"
                        : role === "admin"
                          ? "text-blue-600"
                          : "text-slate-400"
                    }`}
                  >
                    {ROLE_LABELS[role] ?? role ?? "Signed in"}
                  </p>
                </div>
              </div>

              <div className="mt-2 flex flex-col gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpen(false);
                    setOpen(true);
                  }}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Change password
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    setLoading(true);
                    await signOut({ callbackUrl: "/login" });
                  }}
                  disabled={loading}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                >
                  {loading ? "Signing out…" : "Sign out"}
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4">
          <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-slate-900">
              Change password
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              You&apos;ll need to sign in with the new password next time.
            </p>
            <form onSubmit={onSubmit} className="mt-5 space-y-4">
              {error && (
                <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
                  {error}
                </p>
              )}
              {message && (
                <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                  {message}
                </p>
              )}
              <div>
                <label
                  htmlFor="user-nav-current"
                  className="block text-sm font-medium text-gray-700"
                >
                  Current password
                </label>
                <input
                  id="user-nav-current"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={current}
                  onChange={(e) => setCurrent(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </div>
              <div>
                <label
                  htmlFor="user-nav-new"
                  className="block text-sm font-medium text-gray-700"
                >
                  New password
                </label>
                <input
                  id="user-nav-new"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={6}
                  value={next}
                  onChange={(e) => setNext(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </div>
              <div>
                <label
                  htmlFor="user-nav-confirm"
                  className="block text-sm font-medium text-gray-700"
                >
                  Confirm new password
                </label>
                <input
                  id="user-nav-confirm"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="flex-1 rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}