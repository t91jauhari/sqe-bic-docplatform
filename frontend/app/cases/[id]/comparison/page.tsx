"use client";
import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Check,
  Download,
  FileSpreadsheet,
  FileJson,
  Pencil,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { Badge, Busy, ErrorNotice, Modal, display } from "@/components/ui";
import type { Document } from "@/lib/types";
import { api } from "@/lib/api";
import { usePlatform } from "@/components/platform-provider";

type ReferenceRow = {
  id: string;
  section: number;
  document_type: string;
  document_label: string;
  field: string | null;
  label: string;
  kind: string;
  values: Record<string, unknown>;
  document_available: Record<string, boolean>;
  requirement: string | null;
  comparison_note: string | null;
};
type Row = ReferenceRow & {
  original_value: unknown;
  dataset_value: unknown;
  effective_value: unknown;
  similarity?: number;
  method?: string;
  effective_edit_value?: unknown;
  effective_original_value?: unknown;
  document_id?: string;
  status: string;
  message: string;
  edited: boolean;
  filename?: string;
  edit?: { reason: string; actor: string };
};
type Result = {
  revision: number;
  sample_id: string | null;
  sample_name?: string;
  customer?: string;
  result: string;
  rows: Row[];
  document_selection?: Record<string, string>;
  documents: {
    id: string;
    filename: string;
    doc_type: string;
    status: string;
  }[];
  summary: {
    counts?: Record<string, number>;
    match_rate?: number | null;
    compared_fields?: number;
    complete?: boolean;
  };
  fingerprint?: string;
  document_groups?: {
    id: string;
    document_label: string;
    filename?: string;
    result: string;
    match_rate: number | null;
    exact_match_rate: number | null;
    coverage_rate: number | null;
    compared_fields: number;
    applicable_fields: number;
    counts: Record<string, number>;
  }[];
};
type Dataset = {
  samples: { id: string; name: string }[];
  rows: ReferenceRow[];
};

function editedValue(value: string): unknown {
  const text = value.trim();
  if (
    text.startsWith("{") ||
    text.startsWith("[") ||
    ["true", "false", "null"].includes(text)
  ) {
    try {
      return JSON.parse(text);
    } catch {
      /* Keep literal annotations such as [BLANK]. */
    }
  }
  return value;
}

export default function ComparisonPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { notify } = usePlatform();
  const [sourceDocuments, setSourceDocuments] = useState<Document[]>([]);
  const [exceptionsOnly, setExceptionsOnly] = useState(true);
  const [dataset, setDataset] = useState<Dataset>();
  const [result, setResult] = useState<Result>();
  const [canWrite, setCanWrite] = useState(false);
  const [canReview, setCanReview] = useState(false);
  const [effectiveEditor, setEffectiveEditor] = useState<Row | null>(null);
  const [effectiveDraft, setEffectiveDraft] = useState("");
  const [effectiveReason, setEffectiveReason] = useState("");
  const [effectiveError, setEffectiveError] = useState("");
  const [sample, setSample] = useState("");
  const [documents, setDocuments] = useState<Record<string, string>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");
  const [status, setStatus] = useState("");
  const [docGroupFilter, setDocGroupFilter] = useState("");
  const load = useCallback(async () => {
    try {
      const [reference, comparison, detail] = await Promise.all([
        api<Dataset>(`/dataset-sample?case_id=${id}`),
        api<Result>(`/cases/${id}/comparison`),
        api<{
          can_write: boolean;
          can_review: boolean;
          customer: string;
          documents: Document[];
        }>(`/cases/${id}`),
      ]);
      setSourceDocuments(detail.documents);
      setDataset(reference);
      setResult({ ...comparison, customer: detail.customer });
      setCanWrite(detail.can_write);
      setCanReview(detail.can_review);
      setSample(comparison.sample_id || "");
      setDocuments(comparison.document_selection || {});
      setDrafts({});
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load comparison.");
    }
  }, [id]);
  useEffect(() => {
    void load();
  }, [load]);
  const save = async () => {
    if (!result) return;
    setBusy(true);
    try {
      const edits = Object.fromEntries(
        Object.entries(drafts).map(([key, value]) => [key, editedValue(value)]),
      );
      const next = await api<Result>(`/cases/${id}/comparison`, {
        method: "PUT",
        body: JSON.stringify({
          expected_revision: result.revision,
          sample_id: sample,
          documents,
          edits,
          reason:
            reason.trim() || "Selected reference sample and source documents",
        }),
      });
      setResult(next);
      setDrafts({});
      setReason("");
      setError("");
      notify("Comparison saved and recalculated.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setBusy(false);
    }
  };
  const correctEffective = async () => {
    if (!effectiveEditor?.document_id) return;
    setBusy(true);
    setEffectiveError("");
    try {
      await api(
        `/documents/${effectiveEditor.document_id}/effective-corrections`,
        {
          method: "POST",
          body: JSON.stringify({
            field: effectiveEditor.field,
            value: editedValue(effectiveDraft),
            expected_value: effectiveEditor.effective_original_value,
            reason: effectiveReason,
          }),
        },
      );
      setEffectiveEditor(null);
      notify(
        "Correction accepted. Effective values and comparisons update after revalidation.",
      );
      await load();
    } catch (e) {
      setEffectiveError(e instanceof Error ? e.message : "Correction failed.");
    } finally {
      setBusy(false);
    }
  };
  const generateEvidence = async () => {
    setBusy(true);
    try {
      const ids = new Set(
        (result?.rows || []).map((r) => r.document_id).filter(Boolean),
      );
      for (const doc of sourceDocuments.filter(
        (d) => ids.has(d.id) && d.status === "COMPLETED",
      )) {
        await api(`/documents/${doc.id}/field-evidence`, { method: "POST" });
      }
      await load();
      notify(
        "Source crops refreshed from existing extraction evidence. Values were not re-extracted.",
      );
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Unable to refresh evidence. Some documents may already have refreshed crops.",
      );
    } finally {
      setBusy(false);
    }
  };
  const dirty =
    !!result &&
    (sample !== (result.sample_id || "") ||
      JSON.stringify(documents) !==
        JSON.stringify(result.document_selection || {}) ||
      Object.keys(drafts).length > 0);
  const sections = [
    ...new Map((dataset?.rows || []).map((row) => [row.section, row])).values(),
  ].filter((row) => row.document_available[sample]);
  const rows = (result?.rows || []).filter(
    (row) =>
      (!exceptionsOnly || !["MATCH", "NOT_APPLICABLE"].includes(row.status)) &&
      (!status || row.status === status) &&
      (!docGroupFilter || row.document_label === docGroupFilter) &&
      (!filter ||
        `${row.document_label} ${row.label} ${row.field}`
          .toLowerCase()
          .includes(filter.toLowerCase())),
  );
  useEffect(() => {
    if (
      dirty ||
      effectiveEditor ||
      !result?.documents.some(
        (d) =>
          !["COMPLETED", "ERROR", "NEEDS_CLASSIFICATION"].includes(d.status),
      )
    )
      return;
    const timer = window.setTimeout(() => {
      void api<Result>(`/cases/${id}/comparison`)
        .then(async (next) => {
          setResult((previous) => ({
            ...next,
            customer: next.customer || previous?.customer,
          }));
          const detail = await api<{ documents: Document[] }>(`/cases/${id}`);
          setSourceDocuments(detail.documents);
        })
        .catch(() => {});
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [dirty, effectiveEditor, id, result]);
  return (
    <Shell
      title="Dataset comparison"
      subtitle={result?.customer || "Compare effective extraction values"}
      action={
        <Link className="secondary" href={`/cases/${id}`}>
          <ArrowLeft size={16} />
          Back to case
        </Link>
      }
    >
      {error && (
        <ErrorNotice
          message={error}
          retry={dirty ? undefined : () => void load()}
        />
      )}
      {!dataset || !result ? (
        <Busy />
      ) : (
        <>
          <section className="comparison-panel">
            <div className="comparison-heading">
              <span className="case-symbol">
                <SlidersHorizontal size={20} />
              </span>
              <div>
                <span className="eyebrow">REFERENCE WORKSPACE</span>
                <h2>Set up your comparison</h2>
              </div>
              <a className="secondary" href="/api/comparisons/export">
                <FileSpreadsheet size={16} />
                All comparisons · Excel
              </a>
            </div>
            <p>
              Compare the final normalized extraction with the reference sample.
              Reference edits affect this case comparison only. Original values
              remain visible. Visual fields compare presence; they do not verify
              signature or image identity.
            </p>
            <label>
              Customer sample{" "}
              <select
                disabled={!canWrite || busy}
                value={sample}
                onChange={(e) => {
                  setSample(e.target.value);
                  setDocuments({});
                  setDrafts({});
                }}
              >
                <option value="">Select a sample</option>
                {dataset.samples.map((s) => (
                  <option key={s.id} value={s.id}>
                    Sample {s.id}: {s.name}
                  </option>
                ))}
              </select>
            </label>
            {sample && (
              <div className="comparison-source-grid">
                {sections.map((section) => (
                  <label key={section.section}>
                    {section.document_label}
                    <select
                      disabled={!canWrite || busy}
                      value={documents[String(section.section)] || ""}
                      onChange={(e) =>
                        setDocuments((previous) => {
                          const next = { ...previous };
                          if (e.target.value)
                            next[String(section.section)] = e.target.value;
                          else delete next[String(section.section)];
                          return next;
                        })
                      }
                    >
                      <option value="">
                        Automatic only when one document matches
                      </option>
                      {result.documents
                        .filter((doc) => doc.doc_type === section.document_type)
                        .map((doc) => (
                          <option key={doc.id} value={doc.id}>
                            {doc.filename} · {doc.status}
                          </option>
                        ))}
                    </select>
                  </label>
                ))}
              </div>
            )}
            {canWrite && (
              <div className="comparison-save-row">
                <label>
                  Reason for reference edits
                  <input
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Required when editing reference values"
                  />
                </label>
                <button
                  className="primary"
                  disabled={
                    busy ||
                    !sample ||
                    (Object.keys(drafts).length > 0 && reason.trim().length < 5)
                  }
                  onClick={() => void save()}
                >
                  <Check size={16} />
                  {busy ? "Saving…" : "Save and compare"}
                </button>
              </div>
            )}
            <button
              className="secondary"
              disabled={busy || dirty}
              onClick={() => void load()}
            >
              <RefreshCw size={15} />
              Refresh effective values
            </button>
            {dirty && (
              <>
                <p>
                  Unsaved changes. Results and downloads below represent the
                  last saved comparison. Saving a different sample starts a new
                  reference without the previous sample's edits.
                </p>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => void load()}
                >
                  Discard unsaved changes and reload
                </button>
              </>
            )}
          </section>
          {result.sample_id && (
            <>
              <section className="comparison-panel">
                <div className="comparison-heading">
                  <span className="case-symbol">
                    <ShieldCheck size={20} />
                  </span>
                  <div>
                    <span className="eyebrow">COMPARISON RESULTS</span>
                    <h2>Review the effective values</h2>
                  </div>
                  <Badge value={result.result} />
                </div>
                <strong>
                  {result.sample_name} · revision {result.revision}
                </strong>{" "}
                <Badge value={result.result} />
                <p className="comparison-metric">
                  {result.summary.match_rate ?? "—"}% match among{" "}
                  {result.summary.compared_fields ?? 0} compared fields.
                  Coverage:{" "}
                  {result.summary.complete
                    ? "complete"
                    : "incomplete; review pending/unmapped fields"}
                  .
                </p>
                <p>
                  {Object.entries(result.summary.counts || {})
                    .map(
                      ([name, count]) =>
                        `${name === "REVIEW" ? "Unresolved checks" : name}: ${count}`,
                    )
                    .join(" · ")}
                </p>
                <a
                  className="text-link"
                  href={`/api/cases/${id}/comparison/export?format=csv`}
                >
                  <Download size={15} />
                  Comparison CSV
                </a>{" "}
                <a
                  className="text-link"
                  href={`/api/cases/${id}/comparison/export?format=json`}
                >
                  <FileJson size={15} />
                  Complete JSON
                </a>
                <p>
                  Exports recalculate from the latest saved reference and
                  current effective values. Refresh this view after extraction
                  or correction changes.
                </p>
              </section>
              <section className="comparison-panel">
                <div className="comparison-heading">
                  <span className="case-symbol">
                    <FileSpreadsheet size={20} />
                  </span>
                  <div>
                    <span className="eyebrow">DOCUMENT BREAKDOWN</span>
                    <h2>Matching by document</h2>
                  </div>
                </div>
                {docGroupFilter && (
                  <div className="button-row" style={{ marginBottom: 12 }}>
                    <span className="count-pill">
                      Filtered by document: {docGroupFilter}
                    </span>
                    <button
                      type="button"
                      className="text-link"
                      onClick={() => setDocGroupFilter("")}
                    >
                      Show all documents
                    </button>
                  </div>
                )}
                <div className="comparison-source-grid">
                  {result.document_groups?.map((group) => (
                    <article
                      className={
                        "comparison-editor-context clickable-doc-card " +
                        (docGroupFilter === group.document_label ? "active" : "")
                      }
                      key={group.id}
                      onClick={() =>
                        setDocGroupFilter((prev) =>
                          prev === group.document_label
                            ? ""
                            : group.document_label,
                        )
                      }
                      title="Click to filter comparison rows to this document"
                    >
                      <strong>{group.document_label}</strong>
                      <p>{group.filename || "No selected document"}</p>
                      <Badge value={group.result} />
                      <p className="comparison-metric">
                        {group.match_rate ?? "—"}% match
                      </p>
                      <p>
                        Exact: {group.exact_match_rate ?? "—"}% · Coverage:{" "}
                        {group.coverage_rate ?? "—"}%
                      </p>
                      <p>
                        {group.compared_fields} / {group.applicable_fields}{" "}
                        applicable fields compared ·{" "}
                        {group.counts.FUZZY_MATCH || 0} fuzzy matches
                      </p>
                    </article>
                  ))}
                </div>
                <p>
                  Match percentage includes accepted fuzzy matches. Coverage
                  shows how many applicable fields were compared; review and
                  unmapped fields remain visible.
                </p>
              </section>
              <section className="comparison-panel comparison-table-panel">
                {canWrite && (
                  <button
                    className="secondary"
                    disabled={busy || dirty}
                    onClick={() => void generateEvidence()}
                  >
                    {busy
                      ? "Updating…"
                      : "Generate / refresh source crops for selected documents"}
                  </button>
                )}
                <p>
                  Source crops show the cited observation, not independent proof
                  of correctness. Reference agreement and fuzzy similarity do
                  not verify the source value.
                </p>
                <label>
                  <input
                    type="checkbox"
                    checked={exceptionsOnly}
                    onChange={(e) => setExceptionsOnly(e.target.checked)}
                  />{" "}
                  Show exceptions first (including fuzzy matches)
                </label>
                <p>
                  {rows.length} visible / {result.rows.length} total fields
                </p>
                <div className="comparison-toolbar">
                  <label className="comparison-search">
                    <Search size={16} />
                    <input
                      aria-label="Filter fields"
                      placeholder="Filter document or field"
                      value={filter}
                      onChange={(e) => setFilter(e.target.value)}
                    />
                  </label>
                  <select
                    aria-label="Filter result"
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                  >
                    <option value="">All results</option>
                    {Object.keys(result.summary.counts || {}).map((s) => (
                      <option key={s} value={s}>
                        {s === "REVIEW" ? "Unresolved checks" : s}
                      </option>
                    ))}
                  </select>
                  <span className="muted">{rows.length} fields</span>
                </div>
                <div className="table-scroll">
                  <table className="comparison-table">
                    <thead>
                      <tr>
                        <th>Document / field</th>
                        <th>Dataset reference</th>
                        <th>Effective normalized value</th>
                        <th>Source crop & original</th>
                        <th>Comparison</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <tr key={row.id}>
                          <td>
                            <strong>{row.label}</strong>
                            <p>{row.document_label}</p>
                            <small>
                              {row.filename || "No source document selected"} ·{" "}
                              {row.field || "Unmapped"}
                            </small>
                            <details>
                              <summary>Requirements and notes</summary>
                              <p>{row.requirement}</p>
                              <p>{row.comparison_note}</p>
                            </details>
                          </td>
                          <td className="field-value">
                            {Object.prototype.hasOwnProperty.call(
                              drafts,
                              row.id,
                            ) ? (
                              <textarea
                                aria-label={`Reference ${row.label}`}
                                rows={4}
                                value={drafts[row.id]}
                                onChange={(e) =>
                                  setDrafts((previous) => ({
                                    ...previous,
                                    [row.id]: e.target.value,
                                  }))
                                }
                              />
                            ) : (
                              <>
                                {display(row.dataset_value)}
                                {canWrite && sample === result.sample_id && (
                                  <button
                                    className="text-link comparison-edit"
                                    onClick={() =>
                                      setDrafts((previous) => ({
                                        ...previous,
                                        [row.id]:
                                          row.dataset_value === null
                                            ? "null"
                                            : typeof row.dataset_value ===
                                                "object"
                                              ? JSON.stringify(
                                                  row.dataset_value,
                                                  null,
                                                  2,
                                                )
                                              : String(row.dataset_value),
                                      }))
                                    }
                                  >
                                    <Pencil size={13} />
                                    Edit reference
                                  </button>
                                )}
                              </>
                            )}
                            {row.edited && (
                              <small>Edited: {row.edit?.reason}</small>
                            )}
                            {Object.prototype.hasOwnProperty.call(
                              drafts,
                              row.id,
                            ) && (
                              <button
                                className="text-link comparison-edit"
                                onClick={() =>
                                  setDrafts((previous) => {
                                    const next = { ...previous };
                                    delete next[row.id];
                                    return next;
                                  })
                                }
                              >
                                <X size={13} />
                                Cancel edit
                              </button>
                            )}
                          </td>
                          <td className="field-value">
                            <strong>{display(row.effective_value)}</strong>
                            {canReview &&
                              row.field &&
                              row.document_id &&
                              !dirty &&
                              result.documents.find(
                                (d) => d.id === row.document_id,
                              )?.status === "COMPLETED" &&
                              row.status !== "NOT_APPLICABLE" && (
                                <button
                                  className="text-link comparison-edit"
                                  disabled={busy}
                                  onClick={() => {
                                    setEffectiveEditor(row);
                                    const value = row.effective_edit_value;
                                    setEffectiveDraft(
                                      value === null
                                        ? "null"
                                        : typeof value === "object"
                                          ? JSON.stringify(value, null, 2)
                                          : String(value ?? ""),
                                    );
                                    setEffectiveReason("");
                                    setEffectiveError("");
                                  }}
                                >
                                  <Pencil size={13} />
                                  Correct effective value
                                </button>
                              )}
                          </td>
                          <td className="field-crop-cell">
                            {row.document_id && row.field && (
                              <ComparisonEvidence
                                document={sourceDocuments.find(
                                  (d) => d.id === row.document_id,
                                )}
                                field={row.field}
                              />
                            )}
                            <small className="muted" style={{ display: "block", marginTop: 4 }}>
                              Original dataset: {display(row.original_value)}
                            </small>
                          </td>
                          <td>
                            <Badge value={row.status} />
                            {row.similarity !== undefined && (
                              <small>
                                Similarity: {row.similarity}% ·{" "}
                                {row.method?.replaceAll("_", " ")}
                              </small>
                            )}
                            <p>{row.message}</p>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p>
                  Text uses case/whitespace normalization. Identifiers keep
                  every digit and leading zero. Dates compare calendar values.
                  Ambiguous numeric separators require review. Composite values
                  can use an explicit JSON reference; no partial matching is
                  assumed.
                </p>
              </section>
            </>
          )}
        </>
      )}
      {effectiveEditor && (
        <Modal
          title="Correct effective value"
          onClose={() => {
            if (!busy) setEffectiveEditor(null);
          }}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void correctEffective();
            }}
          >
            <div className="comparison-editor-context">
              <span className="eyebrow">{effectiveEditor.document_label}</span>
              <h3>{effectiveEditor.label}</h3>
              <p>{effectiveEditor.filename}</p>
            </div>
            {effectiveEditor.field && (
              <ComparisonEvidence
                document={sourceDocuments.find(
                  (d) => d.id === effectiveEditor.document_id,
                )}
                field={effectiveEditor.field}
              />
            )}
            <label>
              Corrected value
              <textarea
                rows={
                  typeof effectiveEditor.effective_edit_value === "object"
                    ? 8
                    : 3
                }
                value={effectiveDraft}
                onChange={(e) => setEffectiveDraft(e.target.value)}
                disabled={busy}
              />
            </label>
            <label>
              Correction reason
              <textarea
                rows={2}
                value={effectiveReason}
                onChange={(e) => setEffectiveReason(e.target.value)}
                placeholder="Explain the correction using the source document"
                disabled={busy}
              />
            </label>
            <p className="muted">
              Your correction runs through the existing field validation and
              normalization. Source OCR is preserved. Computed totals and item
              tables must be corrected through their source inputs in the case
              editor.
            </p>
            {effectiveError && <ErrorNotice message={effectiveError} />}
            <div className="modal-actions">
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => setEffectiveEditor(null)}
              >
                Cancel
              </button>
              <Link className="text-link" href={`/cases/${id}`}>
                Open source-field editor
              </Link>
              <button
                className="primary"
                disabled={busy || effectiveReason.trim().length < 5}
              >
                <Check size={16} />
                {busy ? "Saving…" : "Save correction"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </Shell>
  );
}

function ComparisonEvidence({
  document: doc,
  field,
}: {
  document?: Document;
  field: string;
}) {
  if (!doc) return <p>Source document unavailable.</p>;
  const text = (doc.validation?.field_evidence || []).filter(
    (e) => e.field === field || e.field.startsWith(field + "."),
  );
  const visual = (doc.validation?.visual_evidence || []).filter(
    (e) => e.field === field || e.field.startsWith(field + "."),
  );
  const crops = [
    ...text.flatMap((e) => e.crops || []),
    ...visual
      .filter((e) => e.available && e.storage_key)
      .map((e) => ({
        page_number: e.page_number,
        revision: e.revision,
        storage_key: e.storage_key!,
      })),
  ].filter(
    (crop, idx, arr) =>
      arr.findIndex((other) => other.storage_key === crop.storage_key) === idx
  );
  return (
    <div className="comparison-source-evidence">
      {crops.length ? (
        crops.map((crop) => (
          <a
            key={crop.storage_key}
            href={`/api/documents/${doc.id}/file`}
            target="_blank"
            rel="noreferrer"
          >
            <img
              loading="lazy"
              alt={`Source evidence for ${field}, page ${crop.page_number}`}
              src={`/api/documents/${doc.id}/evidence/${crop.revision}/${crop.storage_key
                .split("/")
                .pop()
                ?.slice(crop.revision.length + 1, -4)}`}
            />
            <small>Source page {crop.page_number} · open original</small>
          </a>
        ))
      ) : (
        <p>
          No localized source crop available. Open the case to generate crops or
          select the correct region.
        </p>
      )}
      <small>
        {[...text, ...visual]
          .map(
            (e) =>
              `${e.field}: ${e.review_status === "REVIEW" ? "" : e.review_status}${e.error ? " · " + e.error : ""}`,
          )
          .join("; ")}
      </small>
    </div>
  );
}
