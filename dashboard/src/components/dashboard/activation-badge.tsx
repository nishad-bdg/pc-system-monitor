"use client";

import type { Report } from "@/lib/api";
import { fmtWindowsActivation, isWindowsNotActivated } from "@/lib/api";

/**
 * Warning on a PC card when Windows is not licensed.
 * Hidden on macOS and on reports that predate the collector.
 */
export function ActivationBadge({ os }: { os?: Report["os"] | null }) {
  if (!isWindowsNotActivated(os)) return null;
  const label = fmtWindowsActivation(os) || "Not activated";
  return (
    <span className="inline-flex items-center rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white shadow-sm shadow-amber-900/40">
      {label}
    </span>
  );
}
