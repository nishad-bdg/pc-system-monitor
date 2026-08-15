"use client";

/**
 * Green/red presence indicator for a PC.
 * online === true -> green dot + "Online"
 * online === false -> red dot + "Offline"
 */
export function StatusDot({
  online,
  showLabel = false,
}: {
  online?: boolean | null;
  showLabel?: boolean;
}) {
  const onlineFlag = online === true;
  return (
    <span
      className="inline-flex items-center gap-1.5"
      title={online === true ? "Online" : "Offline"}
    >
      <span
        className={`inline-block h-2 w-2 shrink-0 rounded-full ${
          onlineFlag ? "bg-emerald-500" : "bg-red-500"
        }`}
        aria-hidden
      />
      {showLabel && (
        <span
          className={`text-[11px] ${
            onlineFlag ? "text-emerald-400" : "text-red-400"
          }`}
        >
          {onlineFlag ? "Online" : "Offline"}
        </span>
      )}
    </span>
  );
}