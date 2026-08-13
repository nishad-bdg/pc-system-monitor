"use client";

import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  createUser,
  deleteUser,
  fetchGroups,
  fetchUsers,
  Group,
  updateUser,
  User,
} from "@/lib/api";
import { DashboardShell } from "@/components/dashboard/shell";
import { PasswordMeter } from "@/components/password-meter";
import { passwordStrength } from "@/lib/password-strength";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const inputClass =
  "w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2";

const ROLE_LABELS: Record<string, string> = {
  super_admin: "Super admin",
  admin: "Admin",
  user: "User",
};

type ModalState =
  | { kind: "create"; username: string; password: string; role: string; groups: string[]; error?: string }
  | { kind: "edit"; user: User; role: string; groups: string[]; password: string; error?: string }
  | { kind: "delete"; user: User }
  | null;

export function UsersPanel() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const queryClient = useQueryClient();

  const [modal, setModal] = useState<ModalState>(null);
  const [status, setStatus] = useState<string | null>(null);

  const { data: users = [], isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["users"],
    queryFn: () => fetchUsers(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
    refetchInterval: 30_000,
  });

  const { data: groups = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: () => fetchGroups(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["users"] });
    queryClient.invalidateQueries({ queryKey: ["groups"] });
  };

  const currentUser = session?.user?.name;

  const createMut = useMutation({
    mutationFn: (v: { username: string; password: string; role: string; groups: string[] }) =>
      createUser(API_URL, apiToken ?? "", v),
    onSuccess: () => {
      invalidate();
      setModal(null);
      setStatus("User created.");
    },
    onError: (e) =>
      setModal((m) =>
        m?.kind === "create" ? { ...m, error: (e as Error).message } : m,
      ),
  });

  const updateMut = useMutation({
    mutationFn: (v: { id: string; role?: string; groups?: string[]; password?: string }) =>
      updateUser(API_URL, apiToken ?? "", v.id, v),
    onSuccess: () => {
      invalidate();
      setModal(null);
      setStatus("User updated.");
    },
    onError: (e) =>
      setModal((m) =>
        m?.kind === "edit" ? { ...m, error: (e as Error).message } : m,
      ),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteUser(API_URL, apiToken ?? "", id),
    onSuccess: () => {
      invalidate();
      setModal(null);
      setStatus("User deleted.");
    },
    onError: (e) => setStatus(`Delete failed: ${(e as Error).message}`),
  });

  const sorted = useMemo(
    () =>
      [...users].sort((a, b) =>
        a.username.localeCompare(b.username, undefined, { sensitivity: "base" }),
      ),
    [users],
  );

  function groupName(id: string, all: Group[]): string {
    return all.find((g) => g.id === id)?.name ?? id;
  }

  function onCreateSubmit(e: FormEvent) {
    e.preventDefault();
    if (modal?.kind !== "create") return;
    if (!modal.username.trim()) return;
    createMut.mutate({
      username: modal.username.trim(),
      password: modal.password,
      role: modal.role,
      groups: modal.groups,
    });
  }

  function onEditSubmit(e: FormEvent) {
    e.preventDefault();
    if (modal?.kind !== "edit") return;
    updateMut.mutate({
      id: modal.user.id,
      role: modal.role,
      groups: modal.groups,
      ...(modal.password ? { password: modal.password } : {}),
    });
  }

  const isEditingSelf = modal?.kind === "edit" && modal.user.username === currentUser;

  return (
    <>
    <DashboardShell
      title="Users"
      nav="users"
      role={session?.user?.role}
      subtitle={
        <>
          {users.length} user{users.length === 1 ? "" : "s"} · super admin only
        </>
      }
      sidebar={
        <div className="px-3 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Roles
          </p>
          <ul className="mt-2 space-y-2 text-xs leading-relaxed text-slate-400">
            <li>
              <span className="font-medium text-slate-200">Super admin</span> — full
              access: users, API keys, groups, all reports.
            </li>
            <li>
              <span className="font-medium text-slate-200">Admin</span> — groups and
              all reports, no API keys or user management.
            </li>
            <li>
              <span className="font-medium text-slate-200">User</span> — sees only PCs
              in their assigned groups.
            </li>
          </ul>
          <p className="mt-4 text-xs leading-relaxed text-slate-500">
            A user can belong to multiple groups. They&apos;ll see the PCs of every
            assigned group.
          </p>
        </div>
      }
      sidebarFooter={
        <button
          type="button"
          onClick={() => refetch()}
          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-100 hover:bg-slate-800 disabled:opacity-50"
          disabled={isFetching}
        >
          {isFetching ? "Refreshing…" : "Refresh"}
        </button>
      }
      header={
        <div className="border-b border-slate-200 bg-white/80 px-6 py-4 backdrop-blur">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-slate-900">
                Users
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Create and manage dashboard logins with group-scoped access.
              </p>
            </div>
            <button
              type="button"
              onClick={() =>
                setModal({
                  kind: "create",
                  username: "",
                  password: "",
                  role: "user",
                  groups: [],
                })
              }
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm shadow-blue-900/40 hover:bg-blue-500"
            >
              New user
            </button>
          </div>
        </div>
      }
    >
      <div className="flex-1 overflow-y-auto px-6 py-6">
          {status && (
            <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
              <span>{status}</span>
              <button
                type="button"
                onClick={() => setStatus(null)}
                className="text-slate-400 hover:text-slate-600"
                aria-label="Dismiss"
              >
                ✕
              </button>
            </div>
          )}

          {isError && (
            <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              Failed to load users from {API_URL}. Is it running?
            </div>
          )}

          {isLoading && (
            <p className="py-12 text-center text-sm text-slate-400">
              Loading users…
            </p>
          )}

          {!isLoading && !isError && sorted.length === 0 && (
            <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/60 text-sm text-slate-500">
              No users yet. Create one to grant dashboard access.
            </div>
          )}

          {!isLoading && !isError && sorted.length > 0 && (
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                    <th className="px-5 py-3">Username</th>
                    <th className="px-5 py-3">Role</th>
                    <th className="px-5 py-3">Groups</th>
                    <th className="px-5 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {sorted.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-50/60">
                      <td className="px-5 py-3.5 font-medium text-slate-900">
                        {u.username}
                        {u.username === currentUser && (
                          <span className="ml-2 rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-blue-700">
                            you
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3.5">
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                            u.role === "super_admin"
                              ? "bg-violet-50 text-violet-700"
                              : u.role === "admin"
                                ? "bg-blue-50 text-blue-700"
                                : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {ROLE_LABELS[u.role] ?? u.role}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex flex-wrap gap-1">
                          {(u.groups ?? []).length === 0 && (
                            <span className="text-xs text-slate-400">—</span>
                          )}
                          {(u.groups ?? []).map((gid) => (
                            <span
                              key={gid}
                              className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
                            >
                              {groupName(gid, groups)}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              setModal({
                                kind: "edit",
                                user: u,
                                role: u.role,
                                groups: [...(u.groups ?? [])],
                                password: "",
                              })
                            }
                            className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => setModal({ kind: "delete", user: u })}
                            disabled={u.username === currentUser}
                            className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
    </DashboardShell>

      {/* Create modal */}
      {modal?.kind === "create" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm">
          <form
            onSubmit={onCreateSubmit}
            className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"
          >
            <h3 className="text-lg font-semibold text-slate-900">New user</h3>
            <p className="mt-1 text-sm text-slate-500">
              Set a role and assign the groups this user can see.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block text-xs font-medium text-slate-600">
                Username
                <input
                  autoFocus
                  value={modal.username}
                  onChange={(e) =>
                    setModal({ ...modal, username: e.target.value, error: undefined })
                  }
                  placeholder="e.g. ops-team"
                  className={inputClass}
                />
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Password
                <input
                  type="password"
                  value={modal.password}
                  onChange={(e) =>
                    setModal({ ...modal, password: e.target.value, error: undefined })
                  }
                  placeholder="min 6 characters"
                  className={inputClass}
                />
                <PasswordMeter value={modal.password} />
              </label>
              <label className="block text-xs font-medium text-slate-600">
                Role
                <select
                  value={modal.role}
                  onChange={(e) =>
                    setModal({ ...modal, role: e.target.value, error: undefined })
                  }
                  className={inputClass}
                >
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                  <option value="super_admin">Super admin</option>
                </select>
              </label>
              <div>
                <p className="text-xs font-medium text-slate-600">Groups</p>
                {groups.length === 0 && (
                  <p className="mt-1 text-xs text-slate-400">
                    No groups yet — create groups first to scope access.
                  </p>
                )}
                <div className="mt-2 flex max-h-40 flex-wrap gap-2 overflow-y-auto">
                  {groups.map((g) => {
                    const checked = modal.groups.includes(g.id);
                    return (
                      <label
                        key={g.id}
                        className={`flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
                          checked
                            ? "border-blue-300 bg-blue-50 text-blue-700"
                            : "border-slate-200 text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() =>
                            setModal({
                              ...modal,
                              groups: checked
                                ? modal.groups.filter((id) => id !== g.id)
                                : [...modal.groups, g.id],
                            })
                          }
                          className="h-3.5 w-3.5 accent-blue-600"
                        />
                        {g.name}
                      </label>
                    );
                  })}
                </div>
              </div>
            </div>
            {modal.error && <p className="mt-2 text-xs text-red-600">{modal.error}</p>}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setModal(null)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={
                  !modal.username.trim() ||
                  passwordStrength(modal.password) === "poor" ||
                  createMut.isPending
                }
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {createMut.isPending ? "Creating…" : "Create user"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Edit modal */}
      {modal?.kind === "edit" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm">
          <form
            onSubmit={onEditSubmit}
            className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"
          >
            <h3 className="text-lg font-semibold text-slate-900">
              Edit {modal.user.username}
            </h3>
            <div className="mt-4 space-y-3">
              <label className="block text-xs font-medium text-slate-600">
                Role
                <select
                  value={modal.role}
                  disabled={isEditingSelf}
                  onChange={(e) =>
                    setModal({ ...modal, role: e.target.value, error: undefined })
                  }
                  className={`${inputClass} disabled:opacity-50`}
                >
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                  <option value="super_admin">Super admin</option>
                </select>
              </label>
              <label className="block text-xs font-medium text-slate-600">
                New password (leave blank to keep current)
                <input
                  type="password"
                  value={modal.password}
                  onChange={(e) =>
                    setModal({ ...modal, password: e.target.value, error: undefined })
                  }
                  placeholder="min 6 characters"
                  className={inputClass}
                />
                {modal.password.length > 0 && (
                  <PasswordMeter value={modal.password} />
                )}
              </label>
              <div>
                <p className="text-xs font-medium text-slate-600">Groups</p>
                <div className="mt-2 flex max-h-40 flex-wrap gap-2 overflow-y-auto">
                  {groups.map((g) => {
                    const checked = modal.groups.includes(g.id);
                    return (
                      <label
                        key={g.id}
                        className={`flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
                          checked
                            ? "border-blue-300 bg-blue-50 text-blue-700"
                            : "border-slate-200 text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() =>
                            setModal({
                              ...modal,
                              groups: checked
                                ? modal.groups.filter((id) => id !== g.id)
                                : [...modal.groups, g.id],
                            })
                          }
                          className="h-3.5 w-3.5 accent-blue-600"
                        />
                        {g.name}
                      </label>
                    );
                  })}
                </div>
              </div>
            </div>
            {modal.error && <p className="mt-2 text-xs text-red-600">{modal.error}</p>}
            {isEditingSelf && (
              <p className="mt-2 text-xs text-slate-400">
                You can&apos;t change your own role.
              </p>
            )}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setModal(null)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={
                  updateMut.isPending ||
                  (modal.password.length > 0 &&
                    passwordStrength(modal.password) === "poor")
                }
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {updateMut.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Delete confirm */}
      {modal?.kind === "delete" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
            <h3 className="text-lg font-semibold text-slate-900">
              Delete {modal.user.username}?
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              They&apos;ll lose dashboard access immediately. This cannot be undone.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setModal(null)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => deleteMut.mutate(modal.user.id)}
                disabled={deleteMut.isPending}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
              >
                {deleteMut.isPending ? "Deleting…" : "Delete user"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
