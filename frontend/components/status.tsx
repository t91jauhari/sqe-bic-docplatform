"use client";
import { statusMeta, sopMeta } from "@/lib/status";

const TONE_CLASS: Record<string, string> = {
  neutral: "neutral",
  info: "info",
  warn: "warn",
  error: "bad",
  ok: "good",
};

/**
 * Canonical workflow-status badge. Every status cell in every table renders
 * through this component, so identical states always share identical wording
 * and tone. Never returns null or blank — unknown values fall back to a
 * neutral badge so no status cell is ever empty.
 */
export function StatusBadge({ value }: { value: string | null | undefined }) {
  const { label, tone } = statusMeta((value || "").trim());
  return (
    <span className={"badge " + (TONE_CLASS[tone] || "neutral")} title={value || undefined}>
      {label}
    </span>
  );
}

/**
 * Canonical SOP-result badge. Renders "Not run" instead of blank when no SOP
 * evaluation has happened yet.
 */
export function SopBadge({ value }: { value: string | null | undefined }) {
  const key = (value || "").trim().toLowerCase();
  const { label, tone } = sopMeta(key === "" || key === "pending" ? "none" : key);
  return <span className={"badge " + (TONE_CLASS[tone] || "neutral")}>{label}</span>;
}
