"use client";

import { signOut } from "next-auth/react";
import { useState } from "react";

export function SignOutButton({
  variant = "dark",
}: {
  variant?: "dark" | "light";
}) {
  const [loading, setLoading] = useState(false);
  const className =
    variant === "light"
      ? "rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      : "rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-100 hover:bg-slate-800 disabled:opacity-50";
  return (
    <button
      onClick={async () => {
        setLoading(true);
        await signOut({ callbackUrl: "/login" });
      }}
      disabled={loading}
      className={className}
    >
      {loading ? "…" : "Sign out"}
    </button>
  );
}
