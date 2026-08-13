"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "next-auth/react";
import {
  ApiKey,
  createApiKey,
  deleteApiKey,
  fetchApiKeys,
  fmtRelative,
  updateApiKey,
} from "@/lib/api";
import { SignOutButton } from "@/components/dashboard/sign-out-button";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const inputClass =
  "w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 outline-none ring-blue-500/40 focus:border-blue-500 focus:ring-2";

type ModalState =
  | { kind: "create"; name: string; error?: string }
  | { kind: "created"; name: string; key: string; copied: boolean }
  | { kind: "rename"; key: ApiKey; name: string; error?: string }
  | { kind: "delete"; key: ApiKey }
  | null;

export function ApiKeysPanel() {
  const { data: session } = useSession();
  const apiToken = session?.user?.apiToken;
  const queryClient = useQueryClient();

  const [modal, setModal] = useState<ModalState>(null);
  const [status, setStatus] = useState<string | null>(null);
  const copyInputRef = useRef<HTMLInputElement>(null);

  const { data: keys = [], isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["api-keys"],
    queryFn: () => fetchApiKeys(API_URL, apiToken ?? ""),
    enabled: !!apiToken,
    refetchInterval: 30_000,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["api-keys"] });

  const createMut = useMutation({
    mutationFn: (name: string) => createApiKey(API_URL, apiToken ?? "", name),
    onSuccess: (res) => {
      invalidate();
      setModal({ kind: "created", name: res.name, key: res.api_key, copied: false });
    },
    onError: (e) =>
      setModal((m) => (m?.kind === "create" ? { ...m, error: (e as Error).message } : m)),
  });

  const updateMut = useMutation({
    mutationFn: (changes: { id: string; name?: string; active?: boolean }) =>
      updateApiKey(API_URL, apiToken ?? "", changes.id, changes),
    onSuccess: () => {
      invalidate();
      setStatus("API key updated.");
      setModal(null);
    },
    onError: (e) =>
      setModal((m) =>
        m?.kind === "rename"
          ? { ...m, error: (e as Error).message }
          : m,
      ),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteApiKey(API_URL, apiToken ?? "", id),
    onSuccess: () => {
      invalidate();
      setStatus("API key deleted.");
      setModal(null);
    },
    onError: (e) => setStatus(`Delete failed: ${(e as Error).message}`),
  });

  useEffect(() => {
    if (modal?.kind === "created") {
      copyInputRef.current?.select();
    }
  }, [modal]);

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
    updateMut.mutate({ id: modal.key.id, name });
  }

  function toggleKey(key: ApiKey) {
    updateMut.mutate({ id: key.id, active: !key.active });
  }

  async function copyKey() {
    if (modal?.kind !== "created") return;
    try {
      await navigator.clipboard.writeText(modal.key);
      setModal({ ...modal, copied: true });
    } catch {
      setStatus("Copy failed — select the key and copy manually.");
    }
  }

  return (
    <div className="flex min-h-screen bg-[var(--bg)] text-[var(--ink)]">
      <aside className="flex w-72 shrink-0 flex-col border-r border-slate-800 bg-slate-950 text-slate-100">
        <div className="border-b border-slate-800 px-4 py-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
            System Info
          </p>
          <h1 className="mt-1 text-lg font-semibold tracking-tight text-white">
            API Keys
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            {keys.length} key{keys.length === 1 ? "" : "s"} for desktop agents
          </p>
          <div className="mt-3 flex gap-2 text-xs">
            <Link
              href="/dashboard"
              className="rounded-md px-2 py-1 font-medium text-slate-300 hover:bg-slate-900 hover:text-white"
            >
              Fleet
            </Link>
            <Link
              href="/reports"
              className="rounded-md px-2 py-1 font-medium text-slate-300 hover:bg-slate-900 hover:text-white"
            >
              Reports
            </Link>
            <span className="rounded-md bg-blue-600 px-2 py-1 font-medium text-white">
              API Keys
            </span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            About API keys
          </p>
          <p className="mt-2 text-xs leading-relaxed text-slate-400">
            Desktop agents authenticate with{" "}
            <code className="rounded bg-slate-900 px-1 py-0.5 font-mono text-[11px] text-blue-300">
              Authorization: Bearer sk-…
            </code>{" "}
            when posting reports. Keys are hashed at rest — the full secret is
            shown only once, right after creation.
          </p>
          <p className="mt-3 text-xs leading-relaxed text-slate-500">
            Inactive keys are rejected by the API. Delete a key to revoke it
            permanently.
          </p>
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
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-slate-900">
                API Keys
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Manage keys that desktop PCs use to submit reports.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setModal({ kind: "create", name: "" })}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm shadow-blue-900/40 hover:bg-blue-500"
            >
              New API key
            </button>
          </div>
        </div>

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
              Failed to load API keys from {API_URL}. Is it running?
            </div>
          )}

          {isLoading && (
            <p className="py-12 text-center text-sm text-slate-400">
              Loading API keys…
            </p>
          )}

          {!isLoading && !isError && keys.length === 0 && (
            <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/60 text-sm text-slate-500">
              No API keys yet. Create one for each desktop PC.
            </div>
          )}

          {!isLoading && !isError && keys.length > 0 && (
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                    <th className="px-5 py-3">Name</th>
                    <th className="px-5 py-3">Prefix</th>
                    <th className="px-5 py-3">Created</th>
                    <th className="px-5 py-3">Status</th>
                    <th className="px-5 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {keys.map((k) => (
                    <tr key={k.id} className="hover:bg-slate-50/60">
                      <td className="px-5 py-3.5 font-medium text-slate-900">
                        {k.name}
                      </td>
                      <td className="px-5 py-3.5">
                        <code className="rounded-md bg-slate-100 px-2 py-1 font-mono text-xs text-slate-600">
                          {k.prefix}…
                        </code>
                      </td>
                      <td className="px-5 py-3.5 text-slate-500">
                        {k.created_at ? fmtRelative(k.created_at) : "—"}
                      </td>
                      <td className="px-5 py-3.5">
                        <button
                          type="button"
                          onClick={() => toggleKey(k)}
                          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold transition ${
                            k.active
                              ? "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                              : "bg-slate-100 text-slate-500 hover:bg-slate-200"
                          }`}
                        >
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              k.active ? "bg-emerald-500" : "bg-slate-400"
                            }`}
                          />
                          {k.active ? "Active" : "Inactive"}
                        </button>
                      </td>
                      <td className="px-5 py-3.5">
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              setModal({ kind: "rename", key: k, name: k.name })
                            }
                            className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
                          >
                            Rename
                          </button>
                          <button
                            type="button"
                            onClick={() => setModal({ kind: "delete", key: k })}
                            className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
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
      </main>

      {/* Create modal */}
      {modal?.kind === "create" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm">
          <form
            onSubmit={onCreateSubmit}
            className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"
          >
            <h3 className="text-lg font-semibold text-slate-900">
              New API key
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              Give it a name you can recognize, e.g.{" "}
              <span className="font-medium text-slate-700">Office-PC-3</span>.
            </p>
            <label className="mt-4 block text-xs font-medium text-slate-600">
              Name
              <input
                autoFocus
                value={modal.name}
                onChange={(e) =>
                  setModal({ ...modal, name: e.target.value, error: undefined })
                }
                placeholder="desktop-agent"
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
                {createMut.isPending ? "Creating…" : "Create key"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Created — show secret once */}
      {modal?.kind === "created" && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl">
            <h3 className="text-lg font-semibold text-slate-900">
              API key created
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              Copy <span className="font-medium text-slate-700">{modal.name}</span>{" "}
              now — <span className="font-semibold text-amber-600">it won&apos;t be
              shown again.</span> Use it in{" "}
              <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">
                --api-key
              </code>{" "}
              or <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">
                SYSTEM_INFO_API_KEY
              </code>
              .
            </p>
            <div className="mt-4 flex items-center gap-2">
              <input
                ref={copyInputRef}
                readOnly
                value={modal.key}
                onFocus={(e) => e.currentTarget.select()}
                className="w-full rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-800 outline-none"
              />
              <button
                type="button"
                onClick={copyKey}
                className={`shrink-0 rounded-lg px-4 py-2 text-sm font-medium transition ${
                  modal.copied
                    ? "bg-emerald-600 text-white"
                    : "bg-blue-600 text-white hover:bg-blue-500"
                }`}
              >
                {modal.copied ? "Copied" : "Copy"}
              </button>
            </div>
            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={() => setModal(null)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                Done
              </button>
            </div>
          </div>
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
              Rename API key
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
                disabled={!modal.name.trim() || updateMut.isPending}
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
              Delete API key?
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              <span className="font-medium text-slate-700">{modal.key.name}</span>{" "}
              will be revoked permanently. Desktop PCs using it can no longer
              post reports.
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
                onClick={() => deleteMut.mutate(modal.key.id)}
                disabled={deleteMut.isPending}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
              >
                {deleteMut.isPending ? "Deleting…" : "Delete key"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
