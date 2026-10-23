"use client";
import { useState } from "react";
import { api } from "@/lib/api";
export function SpiderResubmit({
  documentId,
  onSaved,
}: {
  documentId: string;
  onSaved: () => void;
}) {
  const [reason, setReason] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <div>
      <p>
        The previous Spider-AI request may have completed remotely or returned
        unusable output. Resubmit replaces the cached failed stage with a new
        request and may incur another charge. Retry keeps the cached output.
      </p>
      <label>
        Reason
        <input value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <label>
        <input
          type="checkbox"
          checked={accepted}
          onChange={(e) => setAccepted(e.target.checked)}
        />
        Authorize a new request despite possible duplicate processing/charges
      </label>
      <button
        disabled={busy || !accepted || reason.trim().length < 5}
        onClick={async () => {
          setBusy(true);
          try {
            await api(`/documents/${documentId}/spider-resubmit`, {
              method: "POST",
              body: JSON.stringify({
                reason,
                accept_possible_duplicate_charge: true,
              }),
            });
            onSaved();
          } catch (e) {
            setError(e instanceof Error ? e.message : "Unable to resubmit");
          } finally {
            setBusy(false);
          }
        }}
      >
        Resubmit Spider-AI request
      </button>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
