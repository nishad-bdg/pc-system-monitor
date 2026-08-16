"use client";

export const LIVE_LOAD_WARN_PERCENT = 90;

export function isHighLiveLoad(percent?: number | null): boolean {
  return percent != null && Number.isFinite(percent) && percent >= LIVE_LOAD_WARN_PERCENT;
}

type LoadWarningBadgeProps = {
  cpu?: number | null;
  ram?: number | null;
};

/**
 * Blinking warning on a PC card when live CPU or RAM is at 90% or higher.
 * Hidden when there is no live sample.
 */
export function LoadWarningBadge({ cpu, ram }: LoadWarningBadgeProps) {
  const highCpu = isHighLiveLoad(cpu);
  const highRam = isHighLiveLoad(ram);
  if (!highCpu && !highRam) return null;
  const label =
    highCpu && highRam ? "CPU+RAM high" : highCpu ? "CPU high" : "RAM high";
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white shadow-sm shadow-red-900/40">
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-white" />
      </span>
      {label}
    </span>
  );
}
