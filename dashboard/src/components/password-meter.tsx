"use client";

import { passwordStrength, PasswordStrength } from "@/lib/password-strength";

const STYLES: Record<
  PasswordStrength,
  { label: string; text: string; bar: string }
> = {
  poor: { label: "Poor", text: "text-red-600", bar: "bg-red-500" },
  good: { label: "Good", text: "text-amber-600", bar: "bg-amber-500" },
  strong: { label: "Strong", text: "text-blue-600", bar: "bg-blue-600" },
  high: { label: "High security", text: "text-emerald-600", bar: "bg-emerald-600" },
};

const SEGMENTS: Record<PasswordStrength, number> = {
  poor: 1,
  good: 2,
  strong: 3,
  high: 4,
};

/** Strength meter shown under new-password fields. Poor passwords are rejected. */
export function PasswordMeter({ value }: { value: string }) {
  const level = passwordStrength(value);
  const active = value.length === 0 ? 0 : SEGMENTS[level];
  const style = STYLES[level];

  return (
    <div className="mt-1.5" aria-live="polite">
      <div className="flex gap-1.5">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors ${
              active >= i ? style.bar : "bg-slate-300/70"
            }`}
          />
        ))}
      </div>
      <div className="mt-1 flex items-baseline justify-between gap-2">
        <p
          className={`text-xs font-medium ${
            value.length === 0 ? "text-slate-400" : style.text
          }`}
        >
          {value.length === 0
            ? "Enter a password"
            : level === "poor"
              ? "Poor — too weak"
              : style.label}
        </p>
        {value.length > 0 && level === "poor" && (
          <p className="text-xs text-red-600">
            Use 6+ chars with mixed case, numbers &amp; symbols
          </p>
        )}
      </div>
    </div>
  );
}
