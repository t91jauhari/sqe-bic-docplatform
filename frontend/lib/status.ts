export type StatusTone = "neutral" | "info" | "warn" | "error" | "ok";

// Canonical lifecycle vocabulary. Keys are matched case-insensitively against
// both lowercase raw values and the UPPERCASE values returned by the API.
export const STATUS_LABELS: Record<
  string,
  { label: string; tone: StatusTone }
> = {
  queued: { label: "Queued", tone: "neutral" },
  pending: { label: "Queued", tone: "neutral" },
  processing: { label: "Processing", tone: "info" },
  waiting_documents: { label: "Waiting Documents", tone: "warn" },
  processing_error: { label: "Processing Error", tone: "error" },
  error: { label: "Error", tone: "error" },
  needs_review: { label: "Needs Review", tone: "warn" },
  needs_classification: { label: "Needs Classification", tone: "warn" },
  ready: { label: "Ready", tone: "info" },
  completed: { label: "Completed", tone: "info" },
  pass: { label: "Pass", tone: "ok" },
  finalized: { label: "Finalized", tone: "ok" },
  final: { label: "Finalized", tone: "ok" },
  failed: { label: "Fail", tone: "error" },
  fail: { label: "Fail", tone: "error" },
  review: { label: "Needs Review", tone: "warn" },
  merged: { label: "Merged", tone: "neutral" },
};

// Canonical SOP-result vocabulary. "none" renders as "Not run", never blank.
export const SOP_LABELS: Record<string, { label: string; tone: StatusTone }> = {
  pass: { label: "Pass", tone: "ok" },
  review: { label: "Needs Review", tone: "warn" },
  fail: { label: "Fail", tone: "error" },
  pending: { label: "Not run", tone: "neutral" },
  none: { label: "Not run", tone: "neutral" },
};

export function statusMeta(key: string): {
  label: string;
  tone: StatusTone;
} {
  const hit = STATUS_LABELS[key.toLowerCase()];
  return hit ?? { label: key ? key.replaceAll("_", " ") : "—", tone: "neutral" };
}

export function sopMeta(key: string): { label: string; tone: StatusTone } {
  const hit = SOP_LABELS[key.toLowerCase()];
  return hit ?? { label: key ? key.replaceAll("_", " ") : "Not run", tone: "neutral" };
}
