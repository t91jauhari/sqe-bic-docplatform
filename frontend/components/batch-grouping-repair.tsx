"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { ErrorNotice } from "@/components/ui";
import { GroupingDialog, type GroupingRow } from "./grouping-dialog";
const EMPTY_FILES: File[] = [];
type BatchPreview = {
  batch_id: string;
  revision: string;
  rows: (GroupingRow & { document_id: string; current_customer: string })[];
};

export function BatchGroupingRepair({ batchIds }: { batchIds: string[] }) {
  const router = useRouter();
  const [batch, setBatch] = useState(batchIds[0] || "");
  const [preview, setPreview] = useState<BatchPreview | null>(null);
  const [reason, setReason] = useState(
    "Correct customer grouping for this upload batch.",
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const open = async () => {
    setBusy(true);
    setError("");
    try {
      setPreview(await api<BatchPreview>("/batches/" + batch + "/grouping"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Grouping unavailable.");
    } finally {
      setBusy(false);
    }
  };
  const confirm = async (rows: GroupingRow[]) => {
    if (!preview || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ case_ids: string[] }>(
        "/batches/" + preview.batch_id + "/grouping",
        {
          method: "POST",
          body: JSON.stringify({
            labels: Object.fromEntries(
              rows.map((r) => [r.filename, r.customer]),
            ),
            revision: preview.revision,
            reason,
          }),
        },
      );
      setPreview(null);
      router.push(
        result.case_ids.length === 1
          ? "/cases/" + result.case_ids[0]
          : "/cases",
      );
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save grouping.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="panel" style={{ padding: 16, marginBottom: 18 }}>
      <strong>Repair customer grouping</strong>
      <p>
        Review all documents in the selected upload batch. Saved extraction
        results are retained.
      </p>
      {batchIds.length > 1 && (
        <label>
          Upload batch
          <select value={batch} onChange={(e) => setBatch(e.target.value)}>
            {batchIds.map((id) => (
              <option key={id} value={id}>
                {id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
      )}
      <button
        className="secondary"
        disabled={busy || !batch}
        onClick={() => void open()}
      >
        {busy && !preview ? "Loading…" : "Review batch grouping"}
      </button>
      {error && !preview && <ErrorNotice message={error} />}
      {preview && (
        <GroupingDialog
          rows={preview.rows}
          files={EMPTY_FILES}
          busy={busy}
          previewUrls={Object.fromEntries(
            preview.rows.map((r) => [
              r.filename,
              "/api/documents/" + r.document_id + "/file",
            ]),
          )}
          onClose={() => {
            if (!busy) {
              setPreview(null);
              setError("");
            }
          }}
          onConfirm={(rows) => void confirm(rows)}
          confirmDisabled={reason.trim().length < 5}
          confirmationNote={
            <>
              <label>
                Reason for regrouping
                <input
                  value={reason}
                  maxLength={1000}
                  disabled={busy}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <p className="muted">
                Existing assignments:{" "}
                {Array.from(
                  new Set(preview.rows.map((r) => r.current_customer)),
                ).join(", ")}
                . Processing must be stopped before saving.
              </p>
              {error && <ErrorNotice message={error} />}
            </>
          }
        />
      )}
    </div>
  );
}
