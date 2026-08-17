"use client";

type ConnectionBadgeProps = {
  kind?: string | null;
  ssid?: string | null;
};

/**
 * Small pill on a PC card showing the live network connection type
 * (Wi-Fi vs Ethernet). Hidden when there is no live sample or the
 * adapter type is unknown.
 */
export function ConnectionBadge({ kind, ssid }: ConnectionBadgeProps) {
  if (!kind || (kind !== "wifi" && kind !== "ethernet")) return null;
  const wifi = kind === "wifi";
  const label = wifi ? (ssid ? `${ssid}` : "Wi-Fi") : "Ethernet";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none ${
        wifi
          ? "bg-blue-500/25 text-blue-200"
          : "bg-slate-500/25 text-slate-200"
      }`}
    >
      <svg
        className="h-2.5 w-2.5"
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={2.5}
        stroke="currentColor"
        aria-hidden
      >
        {wifi ? (
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M4.5 10.5a12.6 12.6 0 0 1 15 0M7 13.5a8 8 0 0 1 10 0M9.6 16.5a4 4 0 0 1 4.8 0M12 21h.008v.008H12V21z"
          />
        ) : (
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244"
          />
        )}
      </svg>
      <span className="max-w-[96px] truncate">{label}</span>
    </span>
  );
}