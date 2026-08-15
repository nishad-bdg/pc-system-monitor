"use client";

type PrintingBadgeProps = {
  count?: number;
  active?: boolean;
};

/**
 * Small live "printing" badge shown over a PC card while the machine is
 * reporting `print.job` events in realtime over the WebSocket.
 */
export function PrintingBadge({ count = 1, active = true }: PrintingBadgeProps) {
  if (!active) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-400 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-amber-950 shadow-sm shadow-amber-900/30">
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-900 opacity-75" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-950" />
      </span>
      {count > 1 ? `${count} prints` : "printing"}
    </span>
  );
}