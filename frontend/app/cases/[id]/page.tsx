"use client";
import {CaseConfiguration} from "@/components/case-configuration";
import { FieldEvidenceWorkspace } from "@/components/field-evidence-workspace";
import { FieldReprocess } from "@/components/field-reprocess";
import { FieldRequestRecovery } from "@/components/field-request-recovery";
import { BatchGroupingRepair } from "@/components/batch-grouping-repair";
import { EnumRevalidation } from "@/components/enum-revalidation";
import { CaseTask } from "@/components/case-task";
import { SpiderResubmit } from "@/components/spider-resubmit";
import { CopyExtraction } from "@/components/copy-extraction";
import { extractionCheck } from "@/lib/extraction-export";
import { downloadMultiSheetExcel } from "@/lib/excel-multi-sheet";
import { VisualRegionEditor } from "@/components/visual-region-editor";
import { use, useState, useCallback, useEffect } from "react";
import Link from "next/link";
import {
  Upload,
  FileText,
  ArrowUpRight,
  RotateCcw,
  Check,
  Download,
  ExternalLink,
  Pencil,
  MoveRight,
  ChevronDown,
  Clock3,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { useData, usePlatform } from "@/components/platform-provider";
import {
  Badge,
  Busy,
  ErrorNotice,
  Empty,
  Modal,
  display,
  formatDate,
} from "@/components/ui";
import { StatusBadge, SopBadge } from "@/components/status";
import { CaseSOP } from "@/components/case-sop";
import { api } from "@/lib/api";
import type {
  CaseDetail,
  Document,
  ConfigResponse,
  CaseSummary,
} from "@/lib/types";
type Action = {
  kind: "classification" | "correction" | "move" | "reconcile";
  doc: Document;
  field?: string;
};
export default function CasePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params),
    { data, error, loading, refresh } = useData<CaseDetail>("/cases/" + id),
    { notify, user } = usePlatform();
  const { data: cfg } = useData<ConfigResponse>("/config", 0);
  const [selected, setSelected] = useState(""),
    [tab, setTab] = useState<"fields" | "findings" | "timeline">("fields"),
    [findingFilter, setFindingFilter] = useState<"all" | "attention" | "visual" | "pass">("all"),
    [sidebarCollapsed, setSidebarCollapsed] = useState(false),
    [action, setAction] = useState<Action | null>(null),
    [pending, setPending] = useState(false),
    [exporting, setExporting] = useState(false);
  const close = useCallback(() => setAction(null), []);
  useEffect(() => {
    if (!selected && data && window.location.hash === "#recovery") {
      const failed = data.documents.find((d) => d.error);
      if (failed) setSelected(failed.id);
    }
  }, [data, selected]);
  // Step 8 — in-view highlight for the sticky section navigation.
  const [activeSection, setActiveSection] = useState("case-overview");
  useEffect(() => {
    if (!data) return;
    const ids = [
      "case-overview",
      "case-documents",
      "case-fields",
      "case-sop",
      "case-reports",
    ];
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) setActiveSection(visible.target.id);
      },
      { rootMargin: "-96px 0px -55% 0px", threshold: [0, 0.1, 0.3] },
    );
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [data, selected, tab]);
  const doc =
      data?.documents.find((d) => d.id === selected) || data?.documents[0],
    report = data?.reports[0];
  const exportableDocs =
    data?.documents.filter(
      (d) =>
        d.status === "COMPLETED" &&
        Object.entries(d.normalized || {}).some(([f]) => f !== "page_results"),
    ) || [];
  const failedDocs =
    data?.documents.filter(
      (d) =>
        d.status === "ERROR" ||
        d.status === "FAILED" ||
        d.status === "NEEDS_CLASSIFICATION",
    ) || [];
  const retryableDocs =
    data?.documents.filter((d) => !d.provider_state?.pending_create) || [];
  const exportAllDocuments = async () => {
    if (!exportableDocs.length) return;
    setExporting(true);
    try {
      const resolveRow = (
        doc: Document,
        field: string,
        value: unknown,
      ): [string, string] => {
        const columns =
          cfg?.payload.profiles[
            doc.doc_type as keyof typeof cfg.payload.profiles
          ]?.columns;
        const label = columns?.find(([key]) => key === field)?.[1] || field;
        const text =
          value == null &&
          doc.validation?.fields?.[field]?.issues?.some((issue) =>
            ["UNRECOGNIZED_ENUM", "INVALID_OR_MISSING_ENUM"].includes(
              issue.code,
            ),
          )
            ? "Unrecognized value · needs review"
            : display(value);
        return [label, text];
      };
      downloadMultiSheetExcel(
        exportableDocs,
        resolveRow,
        `${data?.reference || "case"}-extraction.xls`,
      );
      notify(
        `Exported ${exportableDocs.length} document${
          exportableDocs.length === 1 ? "" : "s"
        } to Excel.`,
      );
    } catch (error) {
      notify(
        error instanceof Error ? error.message : "Unable to export extraction",
        "error",
      );
    } finally {
      setExporting(false);
    }
  };
  const run = async (operation: () => Promise<unknown>, message: string) => {
    setPending(true);
    try {
      await operation();
      notify(message);
      await refresh();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Action failed.", "error");
    } finally {
      setPending(false);
    }
  };
  return (
    <Shell
      title={data?.customer || "Customer case"}
      subtitle={
        data
          ? data.reference +
            " · " +
            (data.transaction_flow_label || data.template) +
            " · Configuration v" +
            data.config_version
          : "Opening case workspace…"
      }
      action={
        data && (
          <div className="button-row">
            <Link className="secondary" href={`/cases/${id}/comparison`}>
              Dataset comparison
            </Link>
            <Link className="secondary" href={`/cases/${id}/review`}>
              <ShieldCheck size={17} />
              Visual review
            </Link>
            {data.can_write && (
              <Link
                className="primary"
                href={"/upload?case=" + id + "&branch=" + data.branch_id}
              >
                <Upload size={17} />
                Add documents
              </Link>
            )}
          </div>
        )
      }
    >
      {error && <ErrorNotice message={error} retry={() => void refresh()} />}
      {loading && !data ? (
        <Busy />
      ) : (
        data && (
          <>
            {data.can_review && (
              <details className="case-utilities">
                <summary>
                  <Wrench size={16} aria-hidden />
                  Case maintenance tools<span>Grouping & identity checks</span>
                </summary>
                <BatchGroupingRepair
                  key={id}
                  batchIds={Array.from(
                    new Set(
                      data.documents
                        .map((d) => d.batch_id)
                        .filter((id): id is string => !!id),
                    ),
                  )}
                />
                {data.documents.some(
                  (d) => d.doc_type === "ektp" && d.status === "COMPLETED",
                ) && <EnumRevalidation caseId={id} refresh={refresh} />}
                {data.can_adopt_configuration && <CaseConfiguration caseId={id} currentVersion={data.config_version} refresh={refresh} />}
              </details>
            )}
            <div className="case-banner">
              <div className="case-banner-title">
                <span className="case-symbol">
                  <LayersIcon />
                </span>
                <div>
                  <strong>Case status</strong>
                  <div className="badge-row">
                    <StatusBadge value={data.status} />
                    <SopBadge value={data.validation_status} />
                  </div>
                </div>
              </div>
              <div>
                <span className="muted">Documents completed</span>
                <strong>
                  {data.completed_count} / {data.documents_count}
                </strong>
              </div>
              <div>
                <span className="muted">Latest report</span>
                <strong>{report ? `v${report.version}` : "Not ready"}</strong>
              </div>
              <div className="case-release">
                {report && (
                  <>
                    <a
                      className="secondary"
                      href={
                        "/api/reports/" + report.id + "/download?format=pdf"
                      }
                    >
                      <Download size={16} />
                      <span title="Work paper report — the standardized output pack for this case">
                        Kertas kerja
                      </span>{" "}
                      v{report.version}
                    </a>
                    {data.can_review &&
                      data.status === "READY" &&
                      report.state !== "FINAL" && (
                        <button
                          className="primary"
                          disabled={pending}
                          onClick={() =>
                            void run(
                              () =>
                                api("/reports/" + report.id + "/approve", {
                                  method: "POST",
                                }),
                              "Report released.",
                            )
                          }
                        >
                          <ShieldCheck size={16} />
                          Release report
                        </button>
                      )}
                  </>
                )}
              </div>
            </div>
            {data.status === "SOP_ERROR" && (
              <div
                className="fixture-banner"
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 16,
                  background: "rgba(220, 38, 38, 0.08)",
                  borderColor: "rgba(220, 38, 38, 0.3)",
                  color: "inherit",
                  marginTop: 12,
                }}
              >
                <div>
                  <strong style={{ color: "var(--color-danger, #dc2626)" }}>
                    SOP Evaluation Interrupted
                  </strong>
                  <div style={{ fontSize: "13px", opacity: 0.85, marginTop: 2 }}>
                    Case SOP checks encountered an issue. Saved extraction results are intact and preserved. Click to rerun SOP evaluation.
                  </div>
                </div>
                {data.can_write && (
                  <button
                    className="primary"
                    disabled={pending}
                    style={{ whiteSpace: "nowrap" }}
                    onClick={async () => {
                      setPending(true);
                      try {
                        await api("/cases/" + id + "/sop-rerun", { method: "POST" });
                        notify("SOP evaluation queued. Using saved extractions.");
                        await refresh();
                      } catch (e) {
                        notify(e instanceof Error ? e.message : "Rerun failed.", "error");
                      } finally {
                        setPending(false);
                      }
                    }}
                  >
                    <RotateCcw size={15} />
                    Rerun SOP checks
                  </button>
                )}
              </div>
            )}
            {report?.snapshot.provider === "fixture" && (
              <div className="fixture-banner">
                DEVELOPMENT FIXTURE · These are synthetic values, not extraction
                of the uploaded PDF.
              </div>
            )}
            {report?.snapshot.missing.length ? (
              <div className="missing-strip">
                <Clock3 size={18} />
                <strong>Waiting for documents:</strong>
                {report.snapshot.missing
                  .map(
                    (x) =>
                      cfg?.payload.profiles[
                        x as keyof typeof cfg.payload.profiles
                      ]?.label || x,
                  )
                  .join(", ")}
              </div>
            ) : null}
            <nav className="section-tabs" aria-label="Case sections">
              {[
                ["case-overview", "Overview"],
                ["case-documents", "Documents"],
                ["case-fields", "Fields"],
                ["case-sop", "SOP"],
                ["case-reports", "Reports"],
              ].map(([anchor, label]) => (
                <a
                  key={anchor}
                  href={"#" + anchor}
                  className={activeSection === anchor ? "active" : ""}
                >
                  {label}
                </a>
              ))}
            </nav>
            <div id="case-overview">
              <details className="case-utilities" style={{ marginBottom: 14 }}>
                <summary>
                  <Clock3 size={16} aria-hidden />
                  SLA & case assignment<span>Set reviewer owner and due date</span>
                </summary>
                <CaseTask caseId={data.id} />
              </details>
              <CaseSOP data={data} refresh={refresh} />
            </div>
            {sidebarCollapsed && (
              <div className="collapsed-doc-strip panel">
                <div className="collapsed-doc-pills">
                  <span className="small-label">DOCUMENTS ({data.documents.length})</span>
                  {data.documents.map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      className={"doc-pill-btn " + (doc?.id === d.id ? "active" : "")}
                      onClick={() => setSelected(d.id)}
                    >
                      <FileText size={14} />
                      <span>{d.filename}</span>
                      <Badge value={d.status} />
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  className="secondary compact-btn"
                  onClick={() => setSidebarCollapsed(false)}
                >
                  Show document sidebar
                </button>
              </div>
            )}
            <div
              className={"case-workspace " + (sidebarCollapsed ? "sidebar-collapsed" : "")}
              id="case-documents"
            >
              <aside className="document-list panel">
                <div className="section-head">
                  <h2>Documents</h2>
                  <span className="count-pill">{data.documents.length}</span>
                  <button
                    type="button"
                    className="text-link"
                    onClick={() => setSidebarCollapsed(true)}
                    title="Collapse document sidebar for full-width field & crop inspection"
                  >
                    Full width
                  </button>
                  {exportableDocs.length > 0 && (
                    <button
                      className="secondary"
                      disabled={exporting}
                      onClick={exportAllDocuments}
                      title="Export every document's extracted fields to a multi-tab Excel file"
                    >
                      <Download size={15} />
                      {exporting ? "Exporting…" : "Export all to Excel"}
                    </button>
                  )}
                  {data.can_write && (data.status === "SOP_ERROR" || data.status === "PROCESSING_ERROR") && (
                    <button
                      className="primary"
                      disabled={pending}
                      title="Rerun SOP rules using saved extractions. No cloud API calls required."
                      onClick={async () => {
                        setPending(true);
                        try {
                          await api("/cases/" + id + "/sop-rerun", { method: "POST" });
                          notify("SOP evaluation queued. Using saved extractions.");
                          await refresh();
                        } catch (e) {
                          notify(e instanceof Error ? e.message : "SOP rerun failed.", "error");
                        } finally {
                          setPending(false);
                        }
                      }}
                    >
                      <RotateCcw size={15} />
                      Rerun SOP
                    </button>
                  )}
                  {data.can_write && failedDocs.length > 0 && (
                    <button
                      className="secondary"
                      disabled={pending}
                      title="Re-extract only the failed documents. Successfully extracted documents are preserved."
                      onClick={async () => {
                        setPending(true);
                        try {
                          const res = await api<{
                            queued: unknown[];
                            skipped: { reason: string }[];
                          }>("/cases/" + id + "/retry-documents", {
                            method: "POST",
                          });
                          notify(
                            res.queued.length
                              ? `Re-queued ${res.queued.length} failed document${
                                  res.queued.length === 1 ? "" : "s"
                                } for retry.` +
                                  (res.skipped.length
                                    ? ` (${res.skipped.length} completed documents preserved).`
                                    : "")
                              : "No documents were eligible for retry.",
                          );
                          await refresh();
                        } catch (e) {
                          notify(
                            e instanceof Error ? e.message : "Retry failed.",
                            "error",
                          );
                        } finally {
                          setPending(false);
                        }
                      }}
                    >
                      <RotateCcw size={15} />
                      Retry failed documents ({failedDocs.length})
                    </button>
                  )}
                  {data.can_write && failedDocs.length === 0 && retryableDocs.length > 0 && (
                    <button
                      className="secondary"
                      disabled={pending}
                      title="Re-trigger extraction with a fresh provider request for every document in this case"
                      onClick={async () => {
                        setPending(true);
                        try {
                          const res = await api<{
                            queued: unknown[];
                            skipped: { reason: string }[];
                          }>("/cases/" + id + "/retry-documents?all=true", {
                            method: "POST",
                          });
                          notify(
                            res.queued.length
                              ? `Re-queued ${res.queued.length} document${
                                  res.queued.length === 1 ? "" : "s"
                                } for retry.` +
                                  (res.skipped.length
                                    ? ` ${res.skipped.length} skipped.`
                                    : "")
                              : "No documents were eligible for retry.",
                          );
                          await refresh();
                        } catch (e) {
                          notify(
                            e instanceof Error ? e.message : "Retry failed.",
                            "error",
                          );
                        } finally {
                          setPending(false);
                        }
                      }}
                    >
                      <RotateCcw size={15} />
                      Re-extract all ({retryableDocs.length})
                    </button>
                  )}
                </div>
                {data.documents.map((d) => (
                  <button
                    key={d.id}
                    className={
                      "document-item " + (doc?.id === d.id ? "selected" : "")
                    }
                    onClick={() => setSelected(d.id)}
                  >
                    <FileText size={19} />
                    <div>
                      <strong>{d.filename}</strong>
                      <span>
                        {cfg?.payload.profiles[
                          d.doc_type as keyof typeof cfg.payload.profiles
                        ]?.label || "Awaiting classification"}
                      </span>
                      <Badge value={d.status} />
                    </div>
                  </button>
                ))}
                <div className="version-note">
                  <ShieldCheck size={16} />
                  <span>
                    Schema and SOP settings pinned to configuration v
                    {data.config_version}.
                  </span>
                </div>
              </aside>
              <section className="panel evidence-panel" id="case-fields">
                {doc ? (
                  <>
                    <div className="section-head">
                      <div>
                        <h2>{doc.filename}</h2>
                        <p>
                          {doc.classification.method === "llama"
                            ? "LlamaCloud classification verified"
                            : doc.classification.method === "fixture"
                              ? "Synthetic development fixture"
                              : doc.classification.manual
                                ? "Type confirmed by reviewer"
                                : "Grouped by filename · verification pending"}
                        </p>
                      </div>
                      <a
                        className="text-link"
                        target="_blank"
                        rel="noreferrer"
                        href={"/api/documents/" + doc.id + "/file"}
                      >
                        Open PDF
                        <ExternalLink size={15} />
                      </a>
                    </div>
                    <div className="tabs">
                      <button
                        className={tab === "fields" ? "active" : ""}
                        onClick={() => setTab("fields")}
                      >
                        Extracted fields
                      </button>
                      <button
                        className={tab === "findings" ? "active" : ""}
                        onClick={() => setTab("findings")}
                      >
                        SOP findings
                        <span>{report?.snapshot.findings.length || 0}</span>
                      </button>
                      <button
                        className={tab === "timeline" ? "active" : ""}
                        onClick={() => setTab("timeline")}
                      >
                        Audit timeline
                      </button>
                    </div>
                    {Array.isArray(doc?.provider_state?.location_guidance) &&
                      (doc.provider_state?.location_guidance?.length || 0) > 0 && (
                        <details className="info-note">
                          <summary>
                            Reviewed location guidance for this job ·{" "}
                            {doc.provider_state?.location_guidance?.length || 0} fields
                          </summary>
                          <p>
                            Matching reviewed forms supplied location hints to
                            Parse and Extract. Evidence below comes from this
                            document and still requires independent
                            verification.
                          </p>
                          {doc.provider_state?.location_guidance?.map(
                            (hint, index) => (
                              <div key={index}>
                                {String(hint.field)} · page{" "}
                                {String(hint.page_number)}
                              </div>
                            ),
                          )}
                        </details>
                      )}
                    {doc?.error && (
                      <div className="document-error">
                        <ErrorNotice message={doc.error} />
                        {data.can_write &&
                          !!doc.provider_state?.pending_create && (
                            <p className="subtext">
                              <strong>Provider request needs recovery</strong> —
                              the request may have reached the provider before
                              the connection dropped.{" "}
                              <a
                                href="#recovery"
                                className="text-link"
                                title={
                                  "Request " +
                                  String(doc.provider_state?.pending_create) +
                                  (doc.provider_state?.provider_stage
                                    ? " · stage " +
                                      doc.provider_state.provider_stage
                                    : "")
                                }
                              >
                                Details
                              </a>
                            </p>
                          )}
                        <div className="recovery-block" id="recovery">
                          <span className="small-label">NEXT STEP</span>
                          {data.can_review &&
                            ["ERROR", "NEEDS_CLASSIFICATION"].includes(
                              doc.status,
                            ) &&
                            !Object.keys(doc.raw || {}).length && (
                              <button
                                className="primary"
                                onClick={() =>
                                  setAction({ kind: "classification", doc })
                                }
                              >
                                Confirm document type
                              </button>
                            )}
                          <span className="small-label">ADVANCED RECOVERY</span>
                          {data.can_write &&
                            doc.status === "COMPLETED" &&
                            String(
                              doc.provider_state?.provider_stage || "",
                            ).startsWith("SPIDER_FIELDS_") && (
                              <FieldRequestRecovery
                                documentId={doc.id}
                                onQueued={() => void refresh()}
                              />
                            )}
                          <div className="button-row">
                            {data.can_write &&
                              doc.status === "ERROR" &&
                              !doc.provider_state?.pending_create && (
                                <button
                                  className="secondary"
                                  disabled={pending}
                                  onClick={() =>
                                    void run(
                                      () =>
                                        api("/documents/" + doc.id + "/retry", {
                                          method: "POST",
                                        }),
                                      "Document queued for retry.",
                                    )
                                  }
                                >
                                  <RotateCcw size={15} />
                                  Resume processing
                                </button>
                              )}
                            {data.can_write &&
                              doc.status === "ERROR" &&
                              !String(
                                doc.provider_state?.pending_create ||
                                  doc.provider_state?.provider_stage ||
                                  "",
                              )
                                .toLowerCase()
                                .startsWith("spider_fields_") &&
                              (String(
                                doc.provider_state?.pending_create || "",
                              ).startsWith("spider_") ||
                                (String(
                                  doc.provider_state?.provider_stage || "",
                                ).startsWith("SPIDER_") &&
                                  !!doc.provider_state?.[
                                    `spider_${String(doc.provider_state?.provider_stage).slice(7).toLowerCase()}_response_key`
                                  ])) && (
                                <SpiderResubmit
                                  documentId={doc.id}
                                  onSaved={() => void refresh()}
                                />
                              )}
                            {user?.role === "bank_admin" &&
                              doc.status === "ERROR" &&
                              !String(
                                doc.provider_state?.pending_create || "",
                              ).startsWith("spider_") &&
                              !!doc.provider_state?.pending_create && (
                                <button
                                  className="secondary"
                                  onClick={() =>
                                    setAction({ kind: "reconcile", doc })
                                  }
                                >
                                  Reconcile provider job
                                </button>
                              )}
                          </div>
                        </div>
                      </div>
                    )}
                    {tab === "fields" && doc && (
                      <>
                        {data.can_write && doc.status === "COMPLETED" && (
                          <FieldReprocess
                            key={doc.id}
                            documentId={doc.id}
                            canReplaceOverrides={data.can_review}
                            columns={
                              cfg?.payload.profiles[
                                doc.doc_type as keyof typeof cfg.payload.profiles
                              ]?.columns ||
                              Object.keys(doc.raw || {}).map(
                                (key) => [key, key] as [string, string],
                              )
                            }
                            onQueued={() => void refresh()}
                          />
                        )}
                        <div className="document-meta">
                          <Badge value={doc.validation_status} />
                          <CopyExtraction
                            doc={doc}
                            columns={
                              cfg?.payload.profiles[
                                doc.doc_type as keyof typeof cfg.payload.profiles
                              ]?.columns
                            }
                            provider={cfg?.payload.provider}
                          />
                          {data.can_review &&
                            [
                              "COMPLETED",
                              "ERROR",
                              "NEEDS_CLASSIFICATION",
                            ].includes(doc.status) && (
                              <button
                                className="text-link"
                                onClick={() => setAction({ kind: "move", doc })}
                              >
                                <MoveRight size={14} />
                                Move to another case
                              </button>
                            )}
                        </div>
                        {doc.validation_status === "SKIPPED" && (
                          <p className="info-note">
                            Values were formatted by Spider-AI during
                            extraction. Document normalization and validation
                            were skipped; case SOP results are shown separately.
                          </p>
                        )}
                        {Object.keys(doc.normalized || {}).length ||
                        doc.validation?.visual_evidence?.length ||
                        doc.validation?.field_evidence?.length ? (
                          <FieldEvidenceWorkspace
                            doc={doc}
                            columns={
                              cfg?.payload.profiles[
                                doc.doc_type as keyof typeof cfg.payload.profiles
                              ]?.columns
                            }
                            provider={cfg?.payload.provider}
                            canWrite={data.can_write}
                            canReview={data.can_review}
                            pending={pending}
                            onRefreshCrops={() =>
                              void run(
                                () =>
                                  api(`/documents/${doc.id}/field-evidence`, {
                                    method: "POST",
                                  }),
                                "Field evidence refreshed from saved results.",
                              )
                            }
                            onCorrectField={(field) =>
                              setAction({
                                kind: "correction",
                                doc,
                                field,
                              })
                            }
                            onRegionSaved={() => void refresh()}
                          />
                        ) : (
                          <Empty
                            title={
                              ["ERROR", "NEEDS_CLASSIFICATION"].includes(
                                doc.status,
                              )
                                ? "Action needed before extraction"
                                : doc.status === "COMPLETED"
                                  ? "No fields returned"
                                  : "Processing in the background"
                            }
                            detail={
                              doc.status === "COMPLETED"
                                ? "The model returned no displayable field values. Inspect its saved response before requesting a new extraction."
                                : "The worker will publish extracted values here when processing finishes. Progress updates automatically."
                            }
                          />
                        )}
                        {Array.isArray(doc.raw?.page_results) && (
                          <details className="provider-details">
                            <summary>
                              Page extraction details (
                              {doc.raw?.page_results?.length || 0} pages)
                            </summary>
                            <pre>
                              {JSON.stringify(doc.raw?.page_results, null, 2)}
                            </pre>
                          </details>
                        )}
                        <details className="provider-details">
                          <summary>
                            Classification and provider checkpoints
                            <ChevronDown size={15} />
                          </summary>
                          <pre>
                            {JSON.stringify(
                              {
                                classification: doc.classification,
                                provider_state: doc.provider_state,
                              },
                              null,
                              2,
                            )}
                          </pre>
                        </details>
                      </>
                    )}
                    {tab === "findings" && (
                      <div className="findings-list">
                        {report?.snapshot.findings.length ? (
                          <>
                            <div className="field-evidence-toolbar" style={{ margin: "-20px -24px 16px", padding: "12px 24px" }}>
                              <div className="field-filter-pills">
                                {[
                                  ["all", "All findings", report.snapshot.findings.length],
                                  [
                                    "attention",
                                    "Needs attention",
                                    report.snapshot.findings.filter((f) =>
                                      ["FAIL", "REVIEW", "ERROR"].includes(f.result),
                                    ).length,
                                  ],
                                  [
                                    "visual",
                                    "Visual checks",
                                    report.snapshot.findings.filter(
                                      (f) => f.evaluation_type === "VISUAL",
                                    ).length,
                                  ],
                                  [
                                    "pass",
                                    "Passed",
                                    report.snapshot.findings.filter(
                                      (f) => f.result === "PASS",
                                    ).length,
                                  ],
                                ].map(([key, label, count]) => (
                                  <button
                                    key={String(key)}
                                    type="button"
                                    className={findingFilter === key ? "active" : ""}
                                    onClick={() =>
                                      setFindingFilter(
                                        key as "all" | "attention" | "visual" | "pass",
                                      )
                                    }
                                  >
                                    {label} <span>{count}</span>
                                  </button>
                                ))}
                              </div>
                              <Link className="secondary compact-btn" href={`/cases/${id}/review`}>
                                <ShieldCheck size={14} />
                                Open visual review
                              </Link>
                            </div>
                            {report.snapshot.findings
                              .filter((f) => {
                                if (findingFilter === "attention")
                                  return ["FAIL", "REVIEW", "ERROR"].includes(f.result);
                                if (findingFilter === "visual")
                                  return f.evaluation_type === "VISUAL";
                                if (findingFilter === "pass")
                                  return f.result === "PASS";
                                return true;
                              })
                              .map((f, index) => {
                                const leftPath = String(f.evidence?.path || f.field || "");
                                const rightPath = String(f.evidence?.other_path || "");

                                const leftDocIds = Array.isArray(f.evidence?.document_ids)
                                  ? (f.evidence.document_ids as string[])
                                  : typeof f.evidence?.document_id === "string"
                                    ? [f.evidence.document_id]
                                    : [];
                                const leftDoc =
                                  data.documents.find((d) => leftDocIds.includes(d.id)) ||
                                  data.documents.find((d) => leftPath.startsWith(d.doc_type + "."));

                                const rightDocIds = Array.isArray(f.evidence?.reference_document_ids)
                                  ? (f.evidence.reference_document_ids as string[])
                                  : [];
                                const rightDoc =
                                  data.documents.find((d) => rightDocIds.includes(d.id)) ||
                                  (rightPath ? data.documents.find((d) => rightPath.startsWith(d.doc_type + ".")) : null);

                                const leftParts = leftPath.split(".");
                                const leftType = leftParts[0];
                                const leftField = leftParts.slice(1).join(".") || leftPath;

                                const rightParts = rightPath.split(".");
                                const rightType = rightParts[0];
                                const rightField = rightParts.slice(1).join(".") || rightPath;

                                const getFieldLabel = (docType: string, fieldKey: string) => {
                                  const profileCols = cfg?.payload.profiles[docType as keyof typeof cfg.payload.profiles]?.columns;
                                  const col = profileCols?.find(([k]) => k === fieldKey || k === fieldKey.split(".").pop());
                                  return col ? col[1] : fieldKey;
                                };

                                const leftLabel = leftDoc ? getFieldLabel(leftDoc.doc_type, leftField) : leftField;
                                const rightLabel = rightDoc ? getFieldLabel(rightDoc.doc_type, rightField) : rightField;

                                const isComparison = Boolean(
                                  rightPath &&
                                  (rightPath !== leftPath || (rightDoc && leftDoc && rightDoc.id !== leftDoc.id))
                                );

                                return (
                                  <div className="finding-card" key={`${f.rule_id}-${index}`}>
                                    <div>
                                      <Badge value={f.result} />
                                      {f.evaluation_type && (
                                        <span className="mini-tag visual">
                                          {f.evaluation_type}
                                        </span>
                                      )}
                                      <strong>{f.field}</strong>
                                      {f.source_ref && (
                                        <span className="count-pill" style={{ fontSize: "0.75rem", padding: "1px 6px" }}>
                                          {f.source_ref}
                                        </span>
                                      )}
                                      <span className="rule-id">{f.rule_id}</span>
                                    </div>

                                    {/* Dedicated document and field comparison pathway */}
                                    <div className="sop-pathway-banner">
                                      {isComparison ? (
                                        <div className="sop-comparison-flow">
                                          <div className="sop-pathway-node source">
                                            <span className="sop-node-tag">SOURCE DOCUMENT</span>
                                            <div className="sop-node-title">
                                              <FileText size={14} className="node-icon" />
                                              <strong title={leftDoc?.filename || leftType}>
                                                {leftDoc ? leftDoc.filename : leftType}
                                              </strong>
                                            </div>
                                            <div className="sop-node-field">
                                              <span className="field-name-badge">{leftLabel}</span>
                                              <code className="field-path-code">{leftField}</code>
                                            </div>
                                          </div>

                                          <div className="sop-comparison-badge">
                                            <div className="sop-vs-pill">⇄ VS</div>
                                            <span className="sop-comparison-method">
                                              {f.evidence?.policy ? String(f.evidence.policy).replace(/_/g, " ") : "compared with"}
                                            </span>
                                          </div>

                                          <div className="sop-pathway-node reference">
                                            <span className="sop-node-tag">REFERENCE DOCUMENT</span>
                                            <div className="sop-node-title">
                                              <FileText size={14} className="node-icon" />
                                              <strong title={rightDoc?.filename || rightType}>
                                                {rightDoc ? rightDoc.filename : rightType}
                                              </strong>
                                            </div>
                                            <div className="sop-node-field">
                                              <span className="field-name-badge">{rightLabel}</span>
                                              <code className="field-path-code">{rightField}</code>
                                            </div>
                                          </div>
                                        </div>
                                      ) : (
                                        <div className="sop-single-doc-flow">
                                          <div className="sop-pathway-node single">
                                            <span className="sop-node-tag">EVALUATED DOCUMENT & FIELD</span>
                                            <div className="sop-node-title">
                                              <FileText size={14} className="node-icon" />
                                              <strong title={leftDoc?.filename || leftType}>
                                                {leftDoc ? leftDoc.filename : (leftType || "Case Document")}
                                              </strong>
                                            </div>
                                            <div className="sop-node-field">
                                              <span className="field-name-badge">{leftLabel}</span>
                                              <code className="field-path-code">{leftField || leftPath}</code>
                                            </div>
                                          </div>
                                          <div className="sop-rule-objective">
                                            <span className="sop-node-tag">EVALUATION RULE</span>
                                            <div className="rule-policy-desc">
                                              {f.evidence?.policy ? String(f.evidence.policy).replace(/_/g, " ") : f.evaluation_type === "VISUAL" ? "Visual verification check" : "Field validation requirement"}
                                            </div>
                                          </div>
                                        </div>
                                      )}
                                    </div>

                                    <p>{f.message}</p>
                                    <div className="finding-side-by-side">
                                      <div>
                                        <span className="small-label">
                                          ACTUAL OBSERVATION · {leftDoc?.filename ? `${leftDoc.filename} (${leftField})` : leftPath}
                                        </span>
                                        <div>{display(f.actual)}</div>
                                      </div>
                                      <div>
                                        <span className="small-label">
                                          {isComparison
                                            ? `EXPECTED / REFERENCE · ${rightDoc?.filename ? `${rightDoc.filename} (${rightField})` : rightPath}`
                                            : "EXPECTED / RULE REQUIREMENT"}
                                        </span>
                                        <div>{display(f.expected)}</div>
                                      </div>
                                    </div>

                                    {Array.isArray(f.evidence?.comparisons) && f.evidence.comparisons.length > 0 && (
                                      <div className="finding-comparison-pills">
                                        {f.evidence.comparisons.map((c: any, i: number) => (
                                          <span key={i} className={`comparison-result-pill ${c.match ? "match" : "mismatch"}`}>
                                            <strong>Method:</strong> {c.method || "match"} · <strong>Match:</strong> {c.match ? "✓ YES" : "✗ NO"}
                                          </span>
                                        ))}
                                      </div>
                                    )}

                                    <div className="finding-actions-row">
                                      {f.evaluation_type === "VISUAL" && (
                                        <Link
                                          className="text-link"
                                          href={`/cases/${id}/review`}
                                        >
                                          Resolve in visual review
                                          <ArrowUpRight size={13} />
                                        </Link>
                                      )}
                                      {leftDoc && (
                                        <button
                                          type="button"
                                          className="text-link"
                                          onClick={() => {
                                            setSelected(leftDoc.id);
                                            setTab("fields");
                                          }}
                                        >
                                          Inspect {leftDoc.filename} ({leftField})
                                        </button>
                                      )}
                                      {rightDoc && rightDoc.id !== leftDoc?.id && (
                                        <button
                                          type="button"
                                          className="text-link"
                                          onClick={() => {
                                            setSelected(rightDoc.id);
                                            setTab("fields");
                                          }}
                                        >
                                          Inspect {rightDoc.filename} ({rightField})
                                        </button>
                                      )}
                                      <details>
                                        <summary>Source evidence</summary>
                                        <pre>{JSON.stringify(f.evidence, null, 2)}</pre>
                                      </details>
                                    </div>
                                  </div>
                                );
                              })}
                          </>
                        ) : (
                          <Empty
                            title={
                              report
                                ? "No findings recorded"
                                : "Checks are still running"
                            }
                            detail={
                              report
                                ? "Review the report before release."
                                : "A draft is generated after the active documents finish."
                            }
                          />
                        )}
                      </div>
                    )}
                    {tab === "timeline" && (
                      <div className="timeline">
                        {data.timeline.map((t) => (
                          <div key={t.id}>
                            <span className="timeline-dot" />
                            <section>
                              <strong>
                                {t.event
                                  .replaceAll(".", " / ")
                                  .replaceAll("_", " ")}
                              </strong>
                              <p>
                                {formatDate(t.created_at)} ·{" "}
                                {t.actor === "worker"
                                  ? "Background worker"
                                  : t.actor === user?.id
                                    ? "You"
                                    : t.actor}
                              </p>
                              <details>
                                <summary>Details</summary>
                                <pre>{JSON.stringify(t.details, null, 2)}</pre>
                              </details>
                            </section>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <Empty
                    title="No documents in this case"
                    detail="Add the required customer documents to continue."
                  />
                )}
              </section>
            </div>
            {!!data.reports.length && (
              <section className="panel report-history" id="case-reports">
                <div className="section-head">
                  <h2>
                    Latest <span title="Work paper report">Kertas kerja</span>
                  </h2>
                  <span className="muted">Current report for this case.</span>
                </div>
                <div className="report-versions">
                  {data.reports.slice(0, 1).map((r) => (
                    <div key={r.id}>
                      <div>
                        <strong>Version {r.version}</strong>
                        <span>{formatDate(r.created_at)}</span>
                      </div>
                      <Badge value={r.state} />
                      <Badge value={r.snapshot.validation_status} />
                      <div className="button-row">
                        <Link className="primary" href={`/reports/${r.id}`}>
                          View report <ArrowUpRight size={14} />
                        </Link>
                        {["pdf", "xlsx", "json"].map((fmt) => (
                          <a
                            key={fmt}
                            className="text-link"
                            href={
                              "/api/reports/" + r.id + "/download?format=" + fmt
                            }
                          >
                            {fmt.toUpperCase()}
                            <Download size={13} />
                          </a>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        )
      )}
      {action && (
        <ActionModal
          action={action}
          cfg={cfg}
          onClose={close}
          onComplete={async () => {
            setAction(null);
            await refresh();
          }}
        />
      )}
    </Shell>
  );
}
function LayersIcon() {
  return <FileText size={22} />;
}
function ActionModal({
  action,
  cfg,
  onClose,
  onComplete,
}: {
  action: Action;
  cfg: ConfigResponse | null;
  onClose: () => void;
  onComplete: () => Promise<void>;
}) {
  const { notify } = usePlatform(),
    { data: cases } = useData<{ items: CaseSummary[] }>("/cases?limit=100", 0);
  const [reason, setReason] = useState(""),
    [type, setType] = useState(
      action.doc.doc_type === "unknown" ? "application" : action.doc.doc_type,
    ),
    [target, setTarget] = useState("");
  const [value, setValue] = useState(
      JSON.stringify(
        action.doc.overrides?.[action.field || ""] ??
          action.doc.raw?.[action.field || ""] ??
          null,
        null,
        2,
      ),
    ),
    [providerId, setProviderId] = useState("");
  const [pending, setPending] = useState(false),
    [error, setError] = useState("");
  const title = {
    classification: "Confirm document type",
    correction: "Correct extracted field",
    move: "Move document",
    reconcile: "Reconcile provider submission",
  }[action.kind];
  return (
    <Modal title={title} onClose={onClose}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setPending(true);
          setError("");
          try {
            const base = "/documents/" + action.doc.id;
            if (action.kind === "classification")
              await api(base + "/classification", {
                method: "POST",
                body: JSON.stringify({ doc_type: type, reason }),
              });
            if (action.kind === "correction")
              await api(base + "/corrections", {
                method: "POST",
                body: JSON.stringify({
                  field: action.field,
                  value: JSON.parse(value),
                  reason,
                }),
              });
            if (action.kind === "move")
              await api(base + "/move", {
                method: "POST",
                body: JSON.stringify({ case_id: target, reason }),
              });
            if (action.kind === "reconcile")
              await api(base + "/reconcile", {
                method: "POST",
                body: JSON.stringify({
                  stage: action.doc.provider_state?.pending_create,
                  provider_id: providerId,
                  reason,
                }),
              });
            notify("Action recorded in the audit trail.");
            await onComplete();
          } catch (err) {
            setError(err instanceof Error ? err.message : "Action failed.");
          } finally {
            setPending(false);
          }
        }}
      >
        <p className="muted">{action.doc.filename}</p>
        {error && <ErrorNotice message={error} />}
        {action.kind === "classification" && (
          <label>
            Verified document type
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {cfg &&
                Object.entries(cfg.payload.profiles).map(([id, p]) => (
                  <option value={id} key={id}>
                    {p.label}
                  </option>
                ))}
            </select>
          </label>
        )}
        {action.kind === "correction" && (
          <>
            <label>
              {action.field} · effective raw value
              <textarea
                className="code-input"
                rows={8}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                required
              />
            </label>
            <p className="subtext">
              Use JSON matching the original field structure. The raw extraction
              is preserved; SOP checks will rerun.
            </p>
          </>
        )}
        {action.kind === "move" && (
          <label>
            Target case
            <select
              required
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            >
              <option value="">Select a case</option>
              {cases?.items
                .filter((c) => c.id !== action.doc.case_id)
                .map((c) => (
                  <option value={c.id} key={c.id}>
                    {c.reference}
                  </option>
                ))}
            </select>
          </label>
        )}
        {action.kind === "reconcile" && (
          <>
            <p className="muted">
              Reconcile only a saved job for a supported provider. Historical Llama submissions cannot resume; upgrade the case to Spider-AI before retrying.
            </p>
            <label>
              {String(action.doc.provider_state?.pending_create)}
              <input
                required
                value={providerId}
                onChange={(e) => setProviderId(e.target.value)}
              />
            </label>
          </>
        )}
        <label>
          Reason for this action
          <textarea
            required
            minLength={5}
            maxLength={1000}
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Describe the source evidence or correction."
          />
        </label>
        <div className="modal-actions">
          <button className="secondary" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="primary" disabled={pending}>
            {pending ? "Saving…" : "Confirm action"}
            <Check size={16} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
