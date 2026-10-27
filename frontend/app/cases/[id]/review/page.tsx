"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCheck,
  CircleX,
  ExternalLink,
  Eye,
  FileText,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { useData, usePlatform } from "@/components/platform-provider";
import { Badge, Busy, Empty, ErrorNotice, display } from "@/components/ui";
import { api } from "@/lib/api";
import { FieldCrops } from "@/components/field-crops";
import type { CaseDetail, Finding, Document } from "@/lib/types";

type Observation = { document_id: string; page: number; region: string };
type Draft = {
  reportId: string;
  result: string;
  reason: string;
  observations: Observation[];
};
type ReviewEvidence = {
  path?: string;
  other_path?: string;
  supporting_paths?: string[];
  document_ids?: string[];
  reference_document_ids?: string[];
  review?: {
    result: string;
    reason: string;
    actor: string;
    observations: Observation[];
  };
};
const evidenceFor = (finding: Finding) =>
  (finding.evidence || {}) as ReviewEvidence;
const relatedIds = (finding: Finding) => [
  ...new Set([
    ...(evidenceFor(finding).document_ids || []),
    ...(evidenceFor(finding).reference_document_ids || []),
  ]),
];
function initialDraft(
  finding: Finding,
  reportId: string,
  documents: Document[],
): Draft {
  const savedReview = evidenceFor(finding).review;
  if (savedReview)
    return {
      reportId,
      result: savedReview.result,
      reason: savedReview.reason,
      observations: savedReview.observations,
    };
  const ids = relatedIds(finding);
  const available = documents.filter((doc) => ids.includes(doc.id));
  return {
    reportId,
    result: "",
    reason: "",
    observations: available.map((doc) => {
      const field = finding.field.split(".").slice(1).join(".");
      const value = doc?.normalized?.[field];
      const page =
        value && typeof value === "object" && "page_number" in value
          ? Number(value.page_number)
          : 1;
      return {
        document_id: doc.id,
        page: Number.isInteger(page) && page > 0 ? page : 1,
        region: "",
      };
    }),
  };
}

function EvidencePreview({
  documentId,
  page,
  filename,
}: {
  documentId: string;
  page: number;
  filename: string;
}) {
  const [zoom, setZoom] = useState(100);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  return (
    <div className="review-preview">
      <div className="review-zoom">
        <span>Original page {page}</span>
        <div>
          <button
            type="button"
            aria-label={`Zoom out ${filename}`}
            disabled={zoom <= 100}
            onClick={() => setZoom(Math.max(100, zoom - 50))}
          >
            −
          </button>
          <span>{zoom}%</span>
          <button
            type="button"
            aria-label={`Zoom in ${filename}`}
            disabled={zoom >= 300}
            onClick={() => setZoom(Math.min(300, zoom + 50))}
          >
            +
          </button>
        </div>
      </div>
      {failed ? (
        <p className="review-preview-error" role="alert">
          This page could not be displayed. Check the page number or open the
          original document.
        </p>
      ) : (
        <>
          {!loaded && <Busy label="Loading original page…" />}
          <div
            className="review-page-image"
            tabIndex={0}
            role="region"
            aria-label={`Page ${page} of ${filename}. Scroll to inspect at the selected zoom.`}
          >
            <img
              src={`/api/documents/${documentId}/pages/${Math.max(1, page)}`}
              alt={`Original ${filename}, page ${page}`}
              style={{ width: `${zoom}%`, maxWidth: "none" }}
              onLoad={() => setLoaded(true)}
              onError={() => setFailed(true)}
            />
          </div>
        </>
      )}
    </div>
  );
}

export default function ReviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data, loading, error, refresh } = useData<CaseDetail>(`/cases/${id}`);
  const { notify, user } = usePlatform();
  const [selected, setSelected] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("pending");
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [saving, setSaving] = useState(false);
  const [waiting, setWaiting] = useState<{
    report: string;
    rule: string;
  } | null>(null);
  const [saveError, setSaveError] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const report = data?.reports[0];
  const all = report?.snapshot.findings || [];
  const visual = all.filter(
    (f) =>
      f.evaluation_type === "VISUAL" &&
      f.eligible !== false &&
      f.result !== "NOT_APPLICABLE",
  );
  const pending = visual.filter((f) => f.result === "REVIEW");
  const completed = visual.filter((f) => !!evidenceFor(f).review);
  const queue = (filter === "pending" ? pending : completed).filter((f) =>
    `${f.field} ${f.message} ${f.rule_id}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const finding = queue.find((f) => f.rule_id === selected) || queue[0];
  const currentRun = data?.sop_runs?.[0];
  const running =
    !!currentRun &&
    !["COMPLETED", "ERROR", "SUPERSEDED"].includes(currentRun.status);
  const blocked =
    !data ||
    data.completed_count !== data.documents_count ||
    running ||
    !!waiting;
  const draft =
    finding && report && data
      ? drafts[finding.rule_id] ||
        initialDraft(finding, report.id, data.documents)
      : null;
  const stale = !!draft && !!report && draft.reportId !== report.id;
  const updateDraft = (update: Partial<Draft>) => {
    if (finding && draft)
      setDrafts((previous) => ({
        ...previous,
        [finding.rule_id]: { ...draft, ...update },
      }));
  };
  const hasDraft = Object.values(drafts).some(
    (item) =>
      item.result || item.reason || item.observations.some((o) => o.region),
  );
  useEffect(() => {
    if (!hasDraft) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [hasDraft]);
  useEffect(() => {
    if (waiting && report && report.id !== waiting.report) {
      const resolved = report.snapshot.findings.find(
        (f) => f.rule_id === waiting.rule,
      );
      if (resolved && resolved.result !== "REVIEW") {
        setConfirmation(
          `Decision applied. ${resolved.result === "PASS" ? "One point awarded" : "Zero points awarded"}. Continue with the next check.`,
        );
        setSelected("");
      } else {
        setSaveError(
          "A new report is available, but this check still needs review. Reload its evidence before submitting again.",
        );
      }
      setWaiting(null);
    }
  }, [report, waiting]);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!finding || !draft || !report || saving || blocked || stale) return;
    setSaving(true);
    setSaveError("");
    setConfirmation("");
    try {
      await api(`/cases/${id}/sop-review`, {
        method: "POST",
        body: JSON.stringify({
          report_id: draft.reportId,
          rule_id: finding.rule_id,
          result: draft.result,
          reason: draft.reason,
          observations: draft.observations,
        }),
      });
      setWaiting({ report: report.id, rule: finding.rule_id });
      setDrafts((previous) => {
        const next = { ...previous };
        delete next[finding.rule_id];
        return next;
      });
      notify("Decision recorded. SOP points are being updated.");
      setConfirmation(
        "Decision recorded. Updating the report using stored extraction values…",
      );
      await refresh();
    } catch (cause) {
      const message =
        cause instanceof Error ? cause.message : "Unable to save the decision.";
      setSaveError(message);
      notify(message, "error");
    } finally {
      setSaving(false);
    }
  };
  return (
    <Shell
      title={data ? `Visual review · ${data.customer}` : "Visual review"}
      subtitle={
        data
          ? `${data.reference} · ${data.transaction_flow_label || data.template} · Inspect, decide, and record evidence`
          : "Opening review workspace…"
      }
      action={
        <Link className="secondary" href={`/cases/${id}`}>
          <ArrowLeft size={16} /> Back to case
        </Link>
      }
    >
      {error && <ErrorNotice message={error} retry={() => void refresh()} />}
      {loading && !data && <Busy />}
      {data && (
        <>
          <section className="review-overview panel">
            <div className="review-intro">
              <span className="review-entry-icon">
                <ShieldCheck size={25} aria-hidden />
              </span>
              <div>
                <h2>One check. Clear evidence. An accountable decision.</h2>
                <p>
                  Choose a visual check, inspect its original documents, then
                  record PASS or FAIL with what you observed.
                </p>
              </div>
            </div>
            <div className="review-metrics">
              <div>
                <span>Awaiting review</span>
                <strong>{pending.length}</strong>
              </div>
              <div>
                <span>Human decisions</span>
                <strong>{completed.length}</strong>
              </div>
              <div>
                <span>Rule points</span>
                <strong>
                  {report?.snapshot.sop_summary
                    ? `${report.snapshot.sop_summary.earned}/${report.snapshot.sop_summary.possible}`
                    : "Rerun required"}
                </strong>
              </div>
            </div>
            <p className="subtext">
              PASS earns 1 point; FAIL earns 0. Pending reviews remain in
              possible points. Data failures are resolved through field
              corrections or case context in the case page.
            </p>
          </section>
          {!data.can_review && (
            <div className="review-callout">
              You have read access. A user with review permission must record
              decisions.
            </div>
          )}
          {data.maker_checker && data.created_by === user?.id && (
            <div className="review-callout">
              The case maker cannot review their own case. A different reviewer
              must record the decision.
            </div>
          )}
          {confirmation && (
            <div className="review-callout success" role="status">
              <CheckCheck size={18} />
              {confirmation}
            </div>
          )}
          {saveError && <ErrorNotice message={saveError} />}
          {currentRun?.status === "ERROR" && (
            <ErrorNotice
              message={
                currentRun.error ||
                "SOP processing failed. Retry the checks from the case page."
              }
            />
          )}
          {blocked && (
            <div className="review-callout" role="status">
              {waiting
                ? "Decision saved. Waiting for the updated SOP report before the next decision."
                : "Document or SOP processing is in progress. Review decisions become available when the latest report is ready."}
            </div>
          )}
          {!report ? (
            <Empty
              title="A completed SOP report is needed"
              detail="Finish document processing and run SOP checks from the case page to create the review queue."
            />
          ) : !report.snapshot.sop_summary ? (
            <Empty
              title="Update this case to the current review workflow"
              detail="Use Rerun SOP checks on the case page. It uses stored extraction and creates the current visual review queue without a model call."
              action={
                <Link className="primary" href={`/cases/${id}#case-sop`}>
                  Go to SOP checks <ArrowRight size={16} />
                </Link>
              }
            />
          ) : (
            <div className="review-layout">
              <aside
                className="panel review-queue"
                id="review-queue"
                aria-label="Visual review queue"
              >
                <div className="section-head">
                  <h2>Review queue</h2>
                  <span className="count-pill">{pending.length} pending</span>
                </div>
                <div
                  className="review-segments"
                  aria-label="Review queue filter"
                >
                  <button
                    type="button"
                    aria-pressed={filter === "pending"}
                    onClick={() => {
                      setFilter("pending");
                      setSelected("");
                    }}
                  >
                    Pending ({pending.length})
                  </button>
                  <button
                    type="button"
                    aria-pressed={filter === "completed"}
                    onClick={() => {
                      setFilter("completed");
                      setSelected("");
                    }}
                  >
                    Reviewed ({completed.length})
                  </button>
                </div>
                <label className="review-search">
                  <Search size={16} aria-hidden />
                  <input
                    aria-label="Search visual checks"
                    placeholder="Search visual checks…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </label>
                <div className="review-queue-items">
                  {queue.map((item, index) => (
                    <button
                      className="review-queue-item"
                      key={item.rule_id}
                      aria-current={
                        finding?.rule_id === item.rule_id ? "true" : undefined
                      }
                      onClick={() => {
                        setSelected(item.rule_id);
                        setSaveError("");
                      }}
                    >
                      <span className="review-queue-number">
                        {filter === "completed" ? (
                          <Check size={15} />
                        ) : (
                          String(index + 1).padStart(2, "0")
                        )}
                      </span>
                      <span>
                        <strong>
                          {item.field
                            .split(".")
                            .slice(1)
                            .join(" ")
                            .replaceAll("_", " ") || item.field}
                        </strong>
                        <small>{item.rule_id}</small>
                        <span className="review-queue-message">
                          {item.message}
                        </span>
                        {drafts[item.rule_id] &&
                          (drafts[item.rule_id].result ||
                            drafts[item.rule_id].reason ||
                            drafts[item.rule_id].observations.some(
                              (observation) => observation.region,
                            )) && <small>Unsaved draft</small>}
                      </span>
                      <ArrowRight size={15} aria-hidden />
                    </button>
                  ))}
                </div>
                {!queue.length && (
                  <p>
                    {query
                      ? "No matching checks. Clear the search to see the queue."
                      : filter === "pending"
                        ? "No visual checks awaiting review."
                        : "No human decisions recorded yet."}
                  </p>
                )}
                <p className="subtext">
                  Drafts stay available while you switch checks on this page.
                </p>
              </aside>
              <div className="review-workspace">
                {!finding || !draft ? (
                  <section className="panel review-complete">
                    <CheckCheck size={38} />
                    <h2>
                      {pending.length
                        ? "Choose another check"
                        : "Visual review is up to date"}
                    </h2>
                    <p>
                      {pending.length
                        ? "Clear your search or return to Pending to continue."
                        : "There are no pending visual decisions. Check the latest report for data failures and release readiness."}
                    </p>
                    <Link
                      className="primary"
                      href={report ? `/reports/${report.id}` : `/cases/${id}`}
                    >
                      View latest report <ArrowRight size={16} />
                    </Link>
                  </section>
                ) : (
                  <>
                    <section className="panel review-check-header">
                      <div className="section-head">
                        <span className="review-step-label">
                          <Eye size={17} /> VISUAL CHECK
                        </span>
                        <Badge value={finding.result} />
                      </div>
                      <h2>{finding.message}</h2>
                      <p className="subtext">
                        {finding.rule_id} · {finding.field} · Report v
                        {report.version}
                      </p>
                      <div className="review-observed">
                        <div>
                          <span>Extracted observation</span>
                          <p>{display(finding.actual)}</p>
                        </div>
                        <div>
                          <span>Reference observation</span>
                          <p>
                            {finding.expected == null
                              ? "Inspect the document against the check above."
                              : display(finding.expected)}
                          </p>
                        </div>
                      </div>
                    </section>
                    {stale && (
                      <div className="review-callout">
                        The report changed while this draft was open. Reload the
                        check and inspect its latest evidence before saving.
                        <button
                          className="secondary"
                          onClick={() => {
                            setDrafts((previous) => {
                              const next = { ...previous };
                              delete next[finding.rule_id];
                              return next;
                            });
                            setSaveError("");
                          }}
                        >
                          Reload check and discard draft
                        </button>
                      </div>
                    )}
                    <form onSubmit={submit}>
                      <fieldset
                        disabled={
                          saving ||
                          blocked ||
                          stale ||
                          !data.can_review ||
                          !!(
                            data.maker_checker && data.created_by === user?.id
                          ) ||
                          finding.result !== "REVIEW"
                        }
                        className="review-fieldset review-workbench-split"
                      >
                        <section className="panel" id="review-evidence">
                          <h2 className="illustrated-heading">
                            <span>
                              <FileText size={20} />
                            </span>
                            1. Inspect the original evidence
                          </h2>
                          <p>
                            Use the page controls to inspect each signing or
                            stamp region. Record the page and visible area you
                            actually checked. Open the original if your browser
                            cannot display it here.
                          </p>
                          {!draft.observations.length && (
                            <ErrorNotice message="No related source document is linked to this check. Correct the case documents and rerun SOP checks before reviewing." />
                          )}
                          <div className="review-documents">
                            {draft.observations.map((observation, index) => {
                              const source = data.documents.find(
                                (doc) => doc.id === observation.document_id,
                              );
                              const updateObservation = (
                                changes: Partial<Observation>,
                              ) =>
                                updateDraft({
                                  observations: draft.observations.map(
                                    (o, i) =>
                                      i === index ? { ...o, ...changes } : o,
                                  ),
                                });
                              return (
                                <article
                                  key={`${observation.document_id}-${index}`}
                                  className="review-document"
                                >
                                  <div className="review-document-title">
                                    <div>
                                      <strong>
                                        {source?.filename || "Source document"}
                                      </strong>
                                      <small>
                                        {source?.doc_type.replaceAll("_", " ")}
                                      </small>
                                    </div>
                                    <a
                                      className="text-link"
                                      href={`/api/documents/${observation.document_id}/file#page=${observation.page}`}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      Open original <ExternalLink size={14} />
                                    </a>
                                  </div>
                                  <div className="review-page-bar">
                                    <label className="review-page-control">
                                      Page inspected
                                      <input
                                        required
                                        type="number"
                                        min={1}
                                        step={1}
                                        value={observation.page}
                                        onChange={(e) =>
                                          updateObservation({
                                            page: Number(e.target.value),
                                          })
                                        }
                                      />
                                    </label>
                                    <div className="quick-chip-row" aria-label="Quick page selector">
                                      {[1, 2, 3, 4].map((pNum) => (
                                        <button
                                          key={pNum}
                                          type="button"
                                          className={
                                            "quick-chip " +
                                            (observation.page === pNum ? "active" : "")
                                          }
                                          onClick={() => updateObservation({ page: pNum })}
                                        >
                                          P{pNum}
                                        </button>
                                      ))}
                                    </div>
                                  </div>
                                  {source && (
                                    <FieldCrops
                                      document={source}
                                      paths={[
                                        finding.field,
                                        evidenceFor(finding).other_path || "",
                                        ...(evidenceFor(finding).supporting_paths || []),
                                      ]}
                                    />
                                  )}
                                  <EvidencePreview
                                    key={`${observation.document_id}-${observation.page}`}
                                    documentId={observation.document_id}
                                    page={observation.page}
                                    filename={
                                      source?.filename || "Source document"
                                    }
                                  />
                                  <label>
                                    Visible region inspected
                                    <input
                                      required
                                      minLength={3}
                                      maxLength={500}
                                      placeholder="e.g. Customer signature at the bottom right"
                                      value={observation.region}
                                      onChange={(e) =>
                                        updateObservation({
                                          region: e.target.value,
                                        })
                                      }
                                    />
                                    <div className="quick-chip-row">
                                      {[
                                        "Customer signature box",
                                        "Bottom-right footer paraf",
                                        "Officer signature & stamp",
                                        "Meterai / stamp duty box",
                                        "Checkbox & declaration row",
                                      ].map((preset) => (
                                        <button
                                          key={preset}
                                          type="button"
                                          className={
                                            "quick-chip " +
                                            (observation.region === preset ? "active" : "")
                                          }
                                          onClick={() =>
                                            updateObservation({ region: preset })
                                          }
                                        >
                                          {preset}
                                        </button>
                                      ))}
                                    </div>
                                  </label>
                                </article>
                              );
                            })}
                          </div>
                        </section>
                        {finding.result === "REVIEW" ? (
                          <section
                            className="panel review-decision review-decision-sticky"
                            id="review-decision"
                          >
                            <h2 className="illustrated-heading">
                              <span>
                                <ShieldCheck size={20} />
                              </span>
                              2. Record your decision
                            </h2>
                            <p>
                              Select the outcome only after inspecting the
                              evidence. Your decision, rationale and source
                              pages are recorded for audit.
                            </p>
                            <div
                              className="review-decision-options"
                              role="radiogroup"
                              aria-label="Review decision"
                            >
                              <label
                                className={`review-choice pass ${draft.result === "PASS" ? "selected" : ""}`}
                              >
                                <input
                                  type="radio"
                                  name="decision"
                                  value="PASS"
                                  required
                                  checked={draft.result === "PASS"}
                                  onChange={() =>
                                    updateDraft({ result: "PASS" })
                                  }
                                />
                                <CheckCheck size={24} />
                                <span>
                                  <strong>PASS</strong>
                                  <small>
                                    The visual evidence satisfies this check.
                                  </small>
                                  <b>1 point</b>
                                </span>
                              </label>
                              <label
                                className={`review-choice fail ${draft.result === "FAIL" ? "selected" : ""}`}
                              >
                                <input
                                  type="radio"
                                  name="decision"
                                  value="FAIL"
                                  required
                                  checked={draft.result === "FAIL"}
                                  onChange={() =>
                                    updateDraft({ result: "FAIL" })
                                  }
                                />
                                <CircleX size={24} />
                                <span>
                                  <strong>FAIL</strong>
                                  <small>
                                    The visual evidence does not satisfy this
                                    check.
                                  </small>
                                  <b>0 points</b>
                                </span>
                              </label>
                            </div>
                            <div className="quick-rationale-group">
                              <span className="small-label">QUICK RATIONALE TEMPLATES</span>
                              <div className="quick-chip-row">
                                {(draft.result === "FAIL"
                                  ? [
                                      "Required signature or paraf is blank on the inspected page.",
                                      "Visual mark or stamp is missing from the designated box.",
                                      "Signature across documents shows a visible discrepancy.",
                                    ]
                                  : [
                                      "Signature/mark is clearly present in the designated region.",
                                      "Required footer paraf verified present across applicable pages.",
                                      "Official bank verification stamp and officer signature verified.",
                                    ]
                                ).map((templateText) => (
                                  <button
                                    key={templateText}
                                    type="button"
                                    className={
                                      "quick-chip " +
                                      (draft.reason === templateText ? "active" : "")
                                    }
                                    onClick={() => updateDraft({ reason: templateText })}
                                  >
                                    {templateText}
                                  </button>
                                ))}
                              </div>
                            </div>
                            <label>
                              What did you observe?
                              <textarea
                                required
                                minLength={10}
                                maxLength={1000}
                                rows={4}
                                placeholder="Describe what is visible, why it passes or fails, and any relevant differences between the documents."
                                value={draft.reason}
                                onChange={(e) =>
                                  updateDraft({ reason: e.target.value })
                                }
                              />
                            </label>
                            <p className="subtext">
                              {draft.reason.length}/1,000 characters · At least
                              10 characters. This decision records a visual
                              observation; it does not authenticate identity or
                              a physical stamp.
                            </p>
                            <div className="review-save-bar">
                              <span>
                                Changes create a new SOP report using stored
                                values.
                              </span>
                              <button
                                className="primary"
                                disabled={
                                  !draft.result ||
                                  !draft.observations.length ||
                                  saving ||
                                  blocked ||
                                  stale ||
                                  !data.can_review ||
                                  !!(
                                    data.maker_checker &&
                                    data.created_by === user?.id
                                  )
                                }
                              >
                                <Check size={17} />
                                {saving
                                  ? "Saving decision…"
                                  : "Save decision and update points"}
                              </button>
                            </div>
                          </section>
                        ) : (
                          <section className="panel" id="review-decision">
                            <h2>Recorded decision</h2>
                            <Badge value={finding.result} />
                            <p>{evidenceFor(finding).review?.reason}</p>
                            <p className="subtext">
                              Reviewer: {evidenceFor(finding).review?.actor}.
                              The saved evidence is retained with the report.
                            </p>
                            {evidenceFor(finding).review?.observations.map(
                              (o, i) => (
                                <p key={i}>
                                  Page {o.page} · {o.region}
                                </p>
                              ),
                            )}
                          </section>
                        )}
                      </fieldset>
                    </form>
                  </>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </Shell>
  );
}
