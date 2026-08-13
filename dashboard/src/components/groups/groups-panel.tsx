"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  createGroup,
  deleteGroup,
  fetchGroups,
  fetchReports,
  fmtRelative,
  Group,
  groupMachines,
  groupOf,
  updateGroup,
} from "@/lib/api";
import { DashboardShell } from "@/components/dashboard/shell";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const inputClass =
  "w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2";

type ModalState =
  | { kind: "create"; name: string; error?: string }
  | { kind: "rename"; group: Group; name: string; error?: string }
  | { kind: "delete"; group: Group }
  | null;

export function GroupsPanel() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const isUser = session?.user?.role === "user";
  const queryClient = useQueryClient();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState>(null);
  const [status, setStatus] = useState<string | null>(null);

  const { data: groups = [], isLoading: loadingGroups } = useQuery({
    queryKey: ["groups"],
    queryFn: () => fetchGroups(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
    refetchInterval: 30_000,
  });

  const { data: reportsRes, isLoading: loadingReports } = useQuery({
    queryKey: ["groups-reports"],
    queryFn: () => fetchReports(API_URL, apiToken ?? "", 500),
    enabled: !!apiToken,
    refetchInterval: 30_000,
  });

  const machines = useMemo(
    () => groupMachines(reportsRes?.reports ?? []),
    [reportsRes?.reports],
  );

  const selected = groups.find((g) => g.id === selectedId) ?? groups[0] ?? null;

  useEffect(() => {
    if (selectedId && !groups.some((g) => g.id === selectedId)) {
      setSelectedId(groups[0]?.id ?? null);
    } else if (!selectedId && groups.length > 0) {
      setSelectedId(groups[0].id);
    }
  }, [groups, selectedId]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["groups"] });
  };

  const createMut = useMutation({
    mutationFn: (name: string) => createGroup(API_URL, apiToken ?? "", name),
    onSuccess: (g) => {
      invalidate();
      setSelectedId(g.id);
      setModal(null);
      setStatus(`Group "${g.name}" created.`);
    },
    onError: (e) =>
      setModal((m) =>
        m?.kind === "create"
          ? { ...m, error: (e as Error).message }
          : m,
      ),
  });

  const renameMut = useMutation({
    mutationFn: (v: { id: string; name: string }) =>
      updateGroup(API_URL, apiToken ?? "", v.id, { name: v.name }),
    onSuccess: () => {
      invalidate();
      setModal(null);
      setStatus("Group renamed.");
    },
    onError: (e) =>
      setModal((m) =>
        m?.kind === "rename"
          ? { ...m, error: (e as Error).message }
          : m,
      ),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteGroup(API_URL, apiToken ?? "", id),
    onSuccess: (_d, id) => {
      invalidate();
      setModal(null);
      setSelectedId(null);
      setStatus("Group deleted.");
    },
    onError: (e) => setStatus(`Delete failed: ${(e as Error).message}`),
  });

  /** Reassign one machine to a group (or None). Single-group enforced by the API. */
  const assignMut = useMutation({
    mutationFn: (v: { key: string; groupId: string | null }) => {
      const ops: Promise<unknown>[] = [];
      const target = groups.find((g) => g.id === v.groupId);
      if (v.groupId && target) {
        const keys = target.machine_keys.includes(v.key)
          ? target.machine_keys
          : [...target.machine_keys, v.key];
        ops.push(updateGroup(API_URL, apiToken ?? "", v.groupId, { machineKeys: keys }));
      } else {
        const current = groupOf(
          machines.find((m) => m.key === v.key) ?? ({ key: v.key } as never),
          groups,
        );
        if (current) {
          ops.push(
            updateGroup(API_URL, apiToken ?? "", current.id, {
              machineKeys: current.machine_keys.filter((k) => k !== v.key),
            }),
          );
        }
      }
      return Promise.all(ops);
    },
    onSuccess: () => invalidate(),
    onError: (e) => setStatus(`Assign failed: ${(e as Error).message}`),
  });

  function onCreateSubmit(e: FormEvent) {
    e.preventDefault();
    if (modal?.kind !== "create") return;
    const name = modal.name.trim();
    if (!name) return;
    createMut.mutate(name);
  }

  function onRenameSubmit(e: FormEvent) {
    e.preventDefault();
    if (modal?.kind !== "rename") return;
    const name = modal.name.trim();
    if (!name) return;
    renameMut.mutate({ id: modal.group.id, name });
  }

  const loading = loadingGroups || loadingReports;

  return (
    <>
    <DashboardShell
      title="Groups"
      nav="groups"
      role={session?.user?.role}
      subtitle={
        <>
          {groups.length} group{groups.length === 1 ? "" : "s"} ·{" "}
          {machines.length} PC{machines.length === 1 ? "" : "s"}
        </>
      }
      sidebar={
        <div className="px-2 py-3">
          {!isUser && (
            <button
              type="button"
              onClick={() => setModal({ kind: "create", name: "" })}
              className="mb-3 w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500"
            >
              + New group
            </button>
          )}
          {loadingGroups && (
            <p className="px-2 py-6 text-center text-sm text-slate-400">
              Loading groups…
            </p>
          )}
          {!loadingGroups && groups.length === 0 && (
            <p className="px-2 py-6 text-center text-sm text-slate-400">
              No groups yet. Create one to organize PCs.
            </p>
          )}
          <ul className="space-y-1">
            {groups.map((g) => {
              const active = g.id === selected?.id;
              return (
                <li key={g.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(g.id)}
                    className={`w-full rounded-lg px-3 py-2.5 text-left transition ${
                      active
                        ? "bg-blue-600 text-white shadow-sm shadow-blue-900/40"
                        : "text-slate-200 hover:bg-slate-900"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">
                        {g.name}
                      </span>
                      <span
                        className={`shrink-0 text-[11px] ${
                          active ? "text-blue-100" : "text-slate-500"
                        }`}
                      >
                        {g.machine_keys.length} PC
                        {g.machine_keys.length === 1 ? "" : "s"}
                      </span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      }
      header={
        <div className="border-b border-slate-200 bg-white/80 px-6 py-4 backdrop-blur">
          {selected ? (
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-slate-900">
                  {selected.name}
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  {selected.machine_keys.length} PC
                  {selected.machine_keys.length === 1 ? "" : "s"} in this group
                  <span className="mx-1.5 text-slate-300">·</span>
                  Each PC can be in only one group
                </p>
              </div>
              <div className="flex gap-2">
                {!isUser && (
                  <>
                    <button
                      type="button"
                      onClick={() =>
                        setModal({ kind: "rename", group: selected, name: selected.name })
                      }
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      onClick={() => setModal({ kind: "delete", group: selected })}
                      className="rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
                    >
                      Delete
                    </button>
                  </>
                )}
              </div>
            </div>
          ) : (
            <div>
              <h2 className="text-xl font-semibold text-slate-900">Groups</h2>
              <p className="mt-1 text-sm text-slate-500">
                Create a group, then assign PCs below.
              </p>
            </div>
          )}
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

          {!selected && !loadingGroups && (
            <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/60 text-sm text-slate-500">
              {groups.length === 0
                ? "No groups yet. Click “+ New group” to create one."
                : "Select a group from the sidebar."}
            </div>
          )}

          {selected && !isUser && (
            <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-200 px-5 py-4">
                <h3 className="text-sm font-semibold text-slate-900">
                  Assign PCs to “{selected.name}”
                </h3>
                <p className="mt-0.5 text-xs text-slate-500">
                  Pick a group per PC. Moving a PC reassigns it (one group only).
                </p>
              </div>

              {loadingReports && (
                <p className="px-5 py-10 text-center text-sm text-slate-400">
                  Loading PCs…
                </p>
              )}

              {!loadingReports && machines.length === 0 && (
                <p className="px-5 py-10 text-center text-sm text-slate-400">
                  No PCs detected yet. Run{" "}
                  <code className="font-mono">system-info</code> on a machine to
                  see it here.
                </p>
              )}

              {!loadingReports && machines.length > 0 && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                      <th className="px-5 py-3">PC</th>
                      <th className="px-5 py-3">Last seen</th>
                      <th className="px-5 py-3">Group</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {machines.map((m) => {
                      const current = groupOf(m, groups);
                      return (
                        <tr key={m.key} className="hover:bg-slate-50/60">
                          <td className="px-5 py-3.5">
                            <div className="font-medium text-slate-900">
                              {m.name}
                            </div>
                            {m.deviceId && (
                              <div className="mt-0.5 font-mono text-[11px] text-slate-400">
                                {m.deviceId.slice(0, 8)}…
                              </div>
                            )}
                          </td>
                          <td className="px-5 py-3.5 text-slate-500">
                            {fmtRelative(m.latest.created_at)}
                          </td>
                          <td className="px-5 py-3.5">
                            <select
                              value={current?.id ?? ""}
                              disabled={assignMut.isPending}
                              onChange={(e) =>
                                assignMut.mutate({
                                  key: m.key,
                                  groupId: e.target.value || null,
                                })
                              }
                              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-800 outline-none focus:border-blue-500"
                            >
                              <option value="">No group</option>
                              {groups.map((g) => (
                                <option key={g.id} value={g.id}>
                                  {g.name}
                                </option>
                              ))}
                            </select>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </section>
          )}

          {selected && isUser && (
            <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-200 px-5 py-4">
                <h3 className="text-sm font-semibold text-slate-900">
                  PCs in “{selected.name}”
                </h3>
                <p className="mt-0.5 text-xs text-slate-500">
                  {selected.machine_keys.length} PC
                  {selected.machine_keys.length === 1 ? "" : "s"} assigned to this group.
                </p>
              </div>
              {machines.length === 0 && (
                <p className="px-5 py-10 text-center text-sm text-slate-400">
                  No PC reports yet.
                </p>
              )}
              {machines.length > 0 && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                      <th className="px-5 py-3">PC</th>
                      <th className="px-5 py-3">Last seen</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {machines
                      .filter((m) => selected.machine_keys.includes(m.key))
                      .map((m) => (
                        <tr key={m.key} className="hover:bg-slate-50/60">
                          <td className="px-5 py-3.5 font-medium text-slate-900">
                            {m.name}
                          </td>
                          <td className="px-5 py-3.5 text-slate-500">
                            {fmtRelative(m.latest.created_at)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              )}
            </section>
          )}
        </div>
    </DashboardShell>

      {/* Create modal */}
      {modal?.kind === "create" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm">
          <form
            onSubmit={onCreateSubmit}
            className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"
          >
            <h3 className="text-lg font-semibold text-slate-900">New group</h3>
            <p className="mt-1 text-sm text-slate-500">
              A group collects PCs, e.g.{" "}
              <span className="font-medium text-slate-700">Operations</span>.
            </p>
            <label className="mt-4 block text-xs font-medium text-slate-600">
              Name
              <input
                autoFocus
                value={modal.name}
                onChange={(e) =>
                  setModal({ ...modal, name: e.target.value, error: undefined })
                }
                placeholder="Operations"
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
              />
            </label>
            {modal.error && (
              <p className="mt-2 text-xs text-red-600">{modal.error}</p>
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
                disabled={!modal.name.trim() || createMut.isPending}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {createMut.isPending ? "Creating…" : "Create group"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Rename modal */}
      {modal?.kind === "rename" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm">
          <form
            onSubmit={onRenameSubmit}
            className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"
          >
            <h3 className="text-lg font-semibold text-slate-900">
              Rename group
            </h3>
            <label className="mt-4 block text-xs font-medium text-slate-600">
              Name
              <input
                autoFocus
                value={modal.name}
                onChange={(e) =>
                  setModal({ ...modal, name: e.target.value, error: undefined })
                }
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2"
              />
            </label>
            {modal.error && (
              <p className="mt-2 text-xs text-red-600">{modal.error}</p>
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
                disabled={!modal.name.trim() || renameMut.isPending}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {renameMut.isPending ? "Saving…" : "Save"}
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
              Delete group?
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              <span className="font-medium text-slate-700">{modal.group.name}</span>{" "}
              will be removed. PCs stay in the fleet but lose their group.
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
                onClick={() => deleteMut.mutate(modal.group.id)}
                disabled={deleteMut.isPending}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
              >
                {deleteMut.isPending ? "Deleting…" : "Delete group"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
