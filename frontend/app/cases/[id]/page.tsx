"use client";
import { CaseConfiguration } from "@/components/case-configuration";
import { FieldEvidenceWorkspace } from "@/components/field-evidence-workspace";
import { FieldReprocess } from "@/components/field-reprocess";
import { FieldRequestRecovery } from "@/components/field-request-recovery";
import { BatchGroupingRepair } from "@/components/batch-grouping-repair";
import { EnumRevalidation } from "@/components/enum-revalidation";
import { CaseTask } from "@/components/case-task";
import { SpiderResubmit } from "@/components/spider-resubmit";
import { CopyExtraction } from "@/components/copy-extraction";
import { VisualRegionEditor } from "@/components/visual-region-editor";
import { use, useState, useCallback, useEffect } from "react";
import Link from "next/link";
import {
  GitBranch,
  Upload,
  FileText,
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
  Scale,
  FileCheck2,
  FolderOpen,
  ChevronRight,
  AlertCircle,
  CheckCircle2,
  Layers,
  WandSparkles,
  FileSpreadsheet,
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
  Branch,
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
    { notify, user, devMode } = usePlatform();
  const { data: cfg } = useData<ConfigResponse>("/config", 0);
  const { data: branches } = useData<Branch[]>("/branches", 0);

  const [activeMode, setActiveMode] = useState<"documents" | "sop" | "reports">("documents");
  const [selected, setSelected] = useState("");
  const [showReprocess, setShowReprocess] = useState(false);
  const [findingFilter, setFindingFilter] = useState<"all" | "attention" | "visual" | "pass">("all");
  const [action, setAction] = useState<Action | null>(null);
  const [pending, setPending] = useState(false);
  const branchName = data?.branch_name || branches?.find((b) => b.id === data?.branch_id)?.name || data?.branch_id || "-";

  const close = useCallback(() => setAction(null), []);

  useEffect(() => {
    if (!selected && data && window.location.hash === "#recovery") {
      const failed = data.documents.find((d) => d.error);
      if (failed) setSelected(failed.id);
    }
  }, [data, selected]);

  const doc =
    data?.documents.find((d) => d.id === selected) || data?.documents[0];
  const report = data?.reports[0];

  const failedDocs =
    data?.documents.filter(
      (d) =>
        d.status === "ERROR" ||
        d.status === "FAILED" ||
        d.status === "NEEDS_CLASSIFICATION",
    ) || [];

  const retryableDocs =
    data?.documents.filter((d) => !d.provider_state?.pending_create) || [];

  const run = async (fn: () => Promise<unknown>, success: string) => {
    setPending(true);
    try {
      await fn();
      notify(success);
      await refresh();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Action failed.", "error");
    } finally {
      setPending(false);
    }
  };

  return (
    <Shell
      title={data?.customer ? `${data.customer}` : "Kasus Nasabah"}
      subtitle={data?.reference ? `Referensi: ${data.reference}` : "Memuat detail kasus..."}
    >
      {error && <ErrorNotice message={error} retry={() => void refresh()} />}
      {loading && !data ? (
        <Busy label="Loading customer case file…" />
      ) : (
        data && (
          <div className="case-page-container">
            {/* Breadcrumb Navigation */}
            <nav className="case-breadcrumb-bar" aria-label="Breadcrumb">
              <Link href="/" className="bc-link">Dashboard</Link>
              <span className="bc-sep">/</span>
              <Link href="/cases" className="bc-link">Customer Cases</Link>
              <span className="bc-sep">/</span>
              <span className="bc-current">{data.customer} ({data.reference})</span>
            </nav>

            {/* Executive Case Summary Card */}
            <header className="case-executive-header">
              <div className="exec-header-top">
                <div className="exec-customer-info">
                  <div className="exec-avatar">{data.customer.charAt(0).toUpperCase()}</div>
                  <div className="exec-customer-text">
                    <h1>{data.customer}</h1>
                    <div className="exec-badges-row">
                      <span className="pill-ref">REF: {data.reference}</span>
                      <span className="pill-branch">Branch: {branchName}</span>
                      <StatusBadge value={data.status} />
                      <SopBadge value={data.validation_status} />
                    </div>
                  </div>
                </div>

                <div className="exec-actions">
                  {report ? (
                    <a
                      className="btn-download-kertas-kerja"
                      href={`/api/reports/${report.id}/download?format=xlsx`}
                      title="Download Official Kertas Kerja in Excel format (.xlsx)"
                    >
                      <FileSpreadsheet size={16} />
                      <span>Download Excel Kertas Kerja</span>
                      <span className="btn-version-pill">v{report.version}</span>
                    </a>
                  ) : null}
                </div>
              </div>

              {/* Integrated 4-Step Workflow Pipeline */}
              <div className="exec-stepper-wrap">
                <div className="pipeline-steps">
                  {/* Step 1: Document Intake */}
                  <div className={`pipeline-step ${data.documents_count > 0 ? "step-done" : "step-pending"}`}>
                    <div className="step-indicator">1</div>
                    <div className="step-content">
                      <div className="step-name">1. Document Intake</div>
                      <div className="step-desc">
                        {data.documents_count > 0 ? `${data.documents_count} files uploaded` : "Waiting for files"}
                      </div>
                    </div>
                  </div>
                  <div className="pipeline-connector" />

                  {/* Step 2: AI Extraction */}
                  <div className={`pipeline-step ${
                    data.completed_count === data.documents_count && data.documents_count > 0
                      ? "step-done"
                      : data.documents.some((d) => ["RUNNING", "PROCESSING", "QUEUED"].includes(d.status))
                        ? "step-active"
                        : data.documents.some((d) => ["ERROR", "PROCESSING_ERROR"].includes(d.status))
                          ? "step-attention"
                          : "step-pending"
                  }`}>
                    <div className="step-indicator">2</div>
                    <div className="step-content">
                      <div className="step-name">2. AI Extraction</div>
                      <div className="step-desc">
                        {data.documents.some((d) => ["RUNNING", "PROCESSING", "QUEUED"].includes(d.status))
                          ? `Processing (${data.completed_count}/${data.documents_count})`
                          : data.documents.some((d) => ["ERROR", "PROCESSING_ERROR"].includes(d.status))
                            ? `Needs Attention (${data.documents.filter((d) => ["ERROR", "PROCESSING_ERROR"].includes(d.status)).length} failed)`
                            : `${data.completed_count}/${data.documents_count} completed`}
                      </div>
                    </div>
                  </div>
                  <div className="pipeline-connector" />

                  {/* Step 3: SOP Compliance */}
                  <div className={`pipeline-step ${
                    data.status === "SOP_ERROR"
                      ? "step-attention"
                      : ["PASS", "COMPLIANT"].includes(data.validation_status)
                        ? "step-done"
                        : ["REVIEW", "FAIL"].includes(data.validation_status)
                          ? "step-review"
                          : "step-pending"
                  }`}>
                    <div className="step-indicator">3</div>
                    <div className="step-content">
                      <div className="step-name">3. SOP Compliance</div>
                      <div className="step-desc">
                        {data.status === "SOP_ERROR"
                          ? "Evaluation interrupted"
                          : ["PASS", "COMPLIANT"].includes(data.validation_status)
                            ? "All rules compliant"
                            : ["REVIEW", "FAIL"].includes(data.validation_status)
                              ? "Findings need review"
                              : "Waiting for extraction"}
                      </div>
                    </div>
                  </div>
                  <div className="pipeline-connector" />

                  {/* Step 4: Work Paper */}
                  <div className={`pipeline-step ${
                    report?.state === "FINAL"
                      ? "step-done"
                      : report
                        ? "step-ready"
                        : "step-pending"
                  }`}>
                    <div className="step-indicator">4</div>
                    <div className="step-content">
                      <div className="step-name">4. Work Paper</div>
                      <div className="step-desc">
                        {report?.state === "FINAL"
                          ? `Finalized v${report.version}`
                          : report
                            ? `Draft ready v${report.version}`
                            : "Waiting for SOP"}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </header>

            {/* SOP Interrupted Alert Banner */}
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
                  marginTop: -6,
                  marginBottom: 16,
                }}
              >
                <div>
                  <strong style={{ color: "var(--color-danger, #dc2626)" }}>
                    SOP Compliance Evaluation Interrupted
                  </strong>
                  <div style={{ fontSize: "13px", opacity: 0.85, marginTop: 2 }}>
                    SOP evaluation encountered a network interruption. All extracted document data remains intact and safely preserved. Click to rerun.
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
                        notify("SOP evaluation rerun using stored document extractions.");
                        await refresh();
                      } catch (e) {
                        notify(e instanceof Error ? e.message : "Rerun failed.", "error");
                      } finally {
                        setPending(false);
                      }
                    }}
                  >
                    <RotateCcw size={15} />
                    Rerun SOP Compliance
                  </button>
                )}
              </div>
            )}

            {/* Missing documents callout */}
            {report?.snapshot.missing.length ? (
              <div className="missing-strip" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Clock3 size={18} />
                  <strong>Waiting for Prerequisite Documents:</strong>
                  <span>
                    {report.snapshot.missing
                      .map(
                        (x) =>
                          cfg?.payload.profiles[x as keyof typeof cfg.payload.profiles]?.label || x,
                      )
                      .join(", ")}
                  </span>
                </div>
                {data.can_write && (
                  <Link
                    href={`/upload?case=${id}&branch=${data.branch_id}`}
                    className="btn-secondary-action compact-btn"
                    title="Upload additional documents to attach to this ongoing case"
                  >
                    <Upload size={13} />
                    <span>Upload Missing Documents</span>
                  </Link>
                )}
              </div>
            ) : null}

            {/* 3-Mode Primary Navigation Tabs */}
            <nav className="workspace-mode-tabs" aria-label="Case workspace modes">
              <button
                type="button"
                className={`mode-tab-btn ${activeMode === "documents" ? "active" : ""}`}
                onClick={() => setActiveMode("documents")}
              >
                <FileText size={17} />
                <span>1. Documents & Extracted Data</span>
                <span className="mode-tab-count">
                  {data.completed_count}/{data.documents_count}
                </span>
              </button>

              <button
                type="button"
                className={`mode-tab-btn ${activeMode === "sop" ? "active" : ""}`}
                onClick={() => setActiveMode("sop")}
              >
                <Scale size={17} />
                <span>2. SOP Compliance Checks</span>
                <span
                  className={`mini-status-dot ${
                    data.status === "SOP_ERROR"
                      ? "error"
                      : ["REVIEW", "FAIL"].includes(data.validation_status)
                        ? "warn"
                        : "good"
                  }`}
                  title={data.validation_status}
                />
              </button>

              <button
                type="button"
                className={`mode-tab-btn ${activeMode === "reports" ? "active" : ""}`}
                onClick={() => setActiveMode("reports")}
              >
                <Clock3 size={17} />
                <span>3. Audit Trail & History</span>
                <span className="mode-tab-count">{data.timeline.length}</span>
              </button>
            </nav>

            {/* MODE 1: DOCUMENTS & EXTRACTED DATA */}
            {activeMode === "documents" && (
              <div className="mode-view-documents">
                {/* Document Package Selector Panel - No Horizontal Scrolling! */}
                <div className="doc-package-panel">
                  <div className="doc-package-header">
                    <div className="doc-package-title">
                      <Layers size={16} style={{ color: "#0d9488" }} />
                      <strong>Customer Document Package ({data.documents_count})</strong>
                      <span className="doc-package-subtext">
                        Select a document to inspect fields, review visual crops, or reprocess.
                      </span>
                    </div>

                    <div className="doc-package-actions">
                      {data.can_write && failedDocs.length > 0 && (
                        <button
                          className="primary compact-btn"
                          disabled={pending}
                          onClick={async () => {
                            setPending(true);
                            try {
                              const res = await api<{
                                queued: unknown[];
                                skipped: { reason: string }[];
                              }>("/cases/" + id + "/retry-documents", { method: "POST" });
                              notify(
                                res.queued.length
                                  ? `Reprocessing ${res.queued.length} failed document(s).`
                                  : "No documents required retry.",
                              );
                              await refresh();
                            } catch (e) {
                              notify(e instanceof Error ? e.message : "Retry failed.", "error");
                            } finally {
                              setPending(false);
                            }
                          }}
                        >
                          <RotateCcw size={14} />
                          Retry Failed ({failedDocs.length})
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Responsive Document Cards Grid - Clean, Spacious, No Scrollbar! */}
                  <div className="doc-package-grid">
                    {data.documents.map((d) => {
                      const profileLabel =
                        cfg?.payload.profiles[d.doc_type as keyof typeof cfg.payload.profiles]?.label || d.doc_type;
                      const isSelected = doc?.id === d.id;
                      return (
                        <button
                          key={d.id}
                          type="button"
                          className={`doc-card-btn ${isSelected ? "selected" : ""}`}
                          onClick={() => {
                            setSelected(d.id);
                            setShowReprocess(false);
                          }}
                        >
                          <div className="doc-card-icon-wrap">
                            <FileText size={18} />
                          </div>
                          <div className="doc-card-body">
                            <strong className="doc-card-filename" title={d.filename}>
                              {d.filename}
                            </strong>
                            <span className="doc-card-profile" title={profileLabel}>
                              {profileLabel}
                            </span>
                          </div>
                          <div className="doc-card-badge-wrap">
                            <Badge value={d.status} />
                          </div>
                        </button>
                      );
                    })}

                    {/* Missing prerequisite document placeholders */}
                    {report?.snapshot.missing.map((missingType) => {
                      const profileLabel =
                        cfg?.payload.profiles[missingType as keyof typeof cfg.payload.profiles]?.label || missingType;
                      return (
                        <Link
                          key={missingType}
                          href={`/upload?case=${id}&branch=${data.branch_id}`}
                          className="doc-card-missing"
                          title="Click to upload this missing prerequisite document"
                        >
                          <div className="doc-card-icon-wrap missing">
                            <Clock3 size={18} />
                          </div>
                          <div className="doc-card-body">
                            <strong className="doc-card-filename" style={{ color: "#b45309" }}>
                              Missing Document
                            </strong>
                            <span className="doc-card-profile" style={{ color: "#92400e" }}>
                              {profileLabel}
                            </span>
                          </div>
                          <div className="doc-card-badge-wrap">
                            <span className="pill-missing">+ Upload</span>
                          </div>
                        </Link>
                      );
                    })}
                  </div>
                </div>

                {/* Document Inspection Content */}
                {doc ? (
                  <section
                    className="panel evidence-panel"
                    style={{
                      padding: 0,
                      overflow: "hidden",
                      background: "#ffffff",
                      border: "1px solid #f1f5f9",
                      borderRadius: "10px",
                      boxShadow: "0 1px 2px 0 rgba(15, 23, 42, 0.02)",
                    }}
                  >
                    <div
                      className="section-head"
                      style={{
                        padding: "16px 20px",
                        borderBottom: "1px solid #f1f5f9",
                        margin: 0,
                        background: "#ffffff",
                      }}
                    >
                      <div>
                        <h2 style={{ fontSize: "16px", margin: 0 }}>{doc.filename}</h2>
                        <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: "12px" }}>
                          Document Type: <strong>{cfg?.payload.profiles[doc.doc_type as keyof typeof cfg.payload.profiles]?.label || doc.doc_type}</strong> · Status: <Badge value={doc.status} />
                        </p>
                      </div>
                      <div className="document-actions-right" style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <CopyExtraction
                          doc={doc}
                          columns={cfg?.payload.profiles[doc.doc_type as keyof typeof cfg.payload.profiles]?.columns}
                          provider={cfg?.payload.provider}
                        />

                        {/* Per-Field Reprocessing Button */}
                        {data.can_review && doc.status === "COMPLETED" && (
                          <button
                            className="btn-secondary-action compact-btn"
                            onClick={() => setShowReprocess((prev) => !prev)}
                            title="Reprocess specific fields with AI without re-extracting the entire document"
                          >
                            <WandSparkles size={14} />
                            <span>{showReprocess ? "Hide Reprocess" : "Reprocess Specific Fields"}</span>
                          </button>
                        )}

                        {data.can_review && ["COMPLETED", "ERROR", "NEEDS_CLASSIFICATION"].includes(doc.status) && (
                          <button
                            className="text-link"
                            style={{ fontSize: "12px" }}
                            onClick={() => setAction({ kind: "move", doc })}
                          >
                            <MoveRight size={14} />
                            Move Case
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Per-Field AI Reprocessing Panel */}
                    {showReprocess && (
                      <div className="per-field-reprocess-container">
                        <div className="per-field-reprocess-header">
                          <div>
                            <strong>Per-Field AI Reprocessing</strong>
                            <p>
                              Select one or more individual fields to re-extract with targeted prompt guidance without re-processing the entire document.
                            </p>
                          </div>
                          <button className="text-button" onClick={() => setShowReprocess(false)}>
                            Close
                          </button>
                        </div>
                        <FieldReprocess
                          documentId={doc.id}
                          columns={cfg?.payload.profiles[doc.doc_type as keyof typeof cfg.payload.profiles]?.columns || []}
                          onQueued={() => {
                            setShowReprocess(false);
                            notify("Field reprocessing request queued.");
                            void refresh();
                          }}
                          canReplaceOverrides={data.can_write}
                        />
                      </div>
                    )}

                    {Object.keys(doc.normalized || {}).length ||
                    doc.validation?.visual_evidence?.length ||
                    doc.validation?.field_evidence?.length ? (
                      <FieldEvidenceWorkspace
                        doc={doc}
                        columns={cfg?.payload.profiles[doc.doc_type as keyof typeof cfg.payload.profiles]?.columns}
                        provider={cfg?.payload.provider}
                        canWrite={data.can_write}
                        canReview={data.can_review}
                        pending={pending}
                        onRefreshCrops={() =>
                          void run(
                            () => api(`/documents/${doc.id}/field-evidence`, { method: "POST" }),
                            "Bukti visual diperbarui dari hasil tersimpan.",
                          )
                        }
                        onCorrectField={(field) => setAction({ kind: "correction", doc, field })}
                        onRegionSaved={() => void refresh()}
                      />
                    ) : (
                      <Empty
                        title={
                          ["ERROR", "NEEDS_CLASSIFICATION"].includes(doc.status)
                            ? "Action required before extraction"
                            : doc.status === "COMPLETED"
                              ? "No field values detected"
                              : "Processing with AI in background"
                        }
                        detail={
                          doc.status === "COMPLETED"
                            ? "The extraction model did not detect structured field values on this document."
                            : "The platform is reading and verifying document contents automatically."
                        }
                      />
                    )}
                  </section>
                ) : (
                  <Empty
                    title="No documents in this customer case yet"
                    detail="Upload customer identity or transaction documents to begin automated extraction."
                  />
                )}
              </div>
            )}

            {/* MODE 2: SOP COMPLIANCE CHECKS */}
            {activeMode === "sop" && (
              <div className="mode-view-sop">
                <CaseSOP data={data} refresh={refresh} />

                {/* SOP Findings Section */}
                <section className="panel findings-section" style={{ marginTop: 20, padding: "20px 24px" }}>
                  <div className="field-evidence-toolbar" style={{ margin: "-20px -24px 16px", padding: "12px 24px" }}>
                    <div className="field-filter-pills">
                      {[
                        ["all", "All Findings", report?.snapshot.findings.length || 0],
                        [
                          "attention",
                          "Needs Attention",
                          report?.snapshot.findings.filter((f) => ["FAIL", "REVIEW", "ERROR"].includes(f.result)).length || 0,
                        ],
                        [
                          "visual",
                          "Visual Checks",
                          report?.snapshot.findings.filter((f) => f.evaluation_type === "VISUAL").length || 0,
                        ],
                        [
                          "pass",
                          "Compliant (Pass)",
                          report?.snapshot.findings.filter((f) => f.result === "PASS").length || 0,
                        ],
                      ].map(([key, label, count]) => (
                        <button
                          key={String(key)}
                          type="button"
                          className={findingFilter === key ? "active" : ""}
                          onClick={() => setFindingFilter(key as "all" | "attention" | "visual" | "pass")}
                        >
                          {label} <span>{count}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {report?.snapshot.findings.length ? (
                    <div className="findings-list">
                      {report.snapshot.findings
                        .filter((f) => {
                          if (findingFilter === "attention") return ["FAIL", "REVIEW", "ERROR"].includes(f.result);
                          if (findingFilter === "visual") return f.evaluation_type === "VISUAL";
                          if (findingFilter === "pass") return f.result === "PASS";
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
                            : typeof f.evidence?.reference_document_id === "string"
                              ? [f.evidence.reference_document_id]
                              : [];
                          const rightDoc =
                            data.documents.find((d) => rightDocIds.includes(d.id)) ||
                            data.documents.find((d) => rightPath.startsWith(d.doc_type + "."));

                          const leftLabel = leftDoc
                            ? cfg?.payload.profiles[leftDoc.doc_type as keyof typeof cfg.payload.profiles]?.columns?.find(([k]) => k === leftPath.replace(leftDoc.doc_type + ".", ""))?.[1] || leftPath
                            : leftPath;

                          const rightLabel = rightDoc
                            ? cfg?.payload.profiles[rightDoc.doc_type as keyof typeof cfg.payload.profiles]?.columns?.find(([k]) => k === rightPath.replace(rightDoc.doc_type + ".", ""))?.[1] || rightPath
                            : rightPath;

                          const actualVal = f.actual ?? f.evidence?.value ?? f.evidence?.actual_value;
                          const expectedVal = f.expected ?? f.evidence?.other_value ?? f.evidence?.expected_value;
                          const hasComparison = actualVal !== undefined || expectedVal !== undefined;

                          return (
                            <div key={f.rule_id || index} className="finding-item" style={{ padding: "16px", borderRadius: "10px", border: "1px solid #e2e8f0", marginBottom: "12px", background: "#ffffff" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                                <div>
                                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                                    <strong style={{ fontSize: "14px", color: "#0f172a" }}>{f.rule_id}</strong>
                                    <Badge value={f.result} />
                                    {f.evaluation_type === "VISUAL" && <span className="mini-tag visual">Visual Check</span>}
                                  </div>
                                  <p style={{ margin: "4px 0 8px", fontSize: "13px", color: "#475569" }}>{f.message}</p>
                                </div>
                              </div>

                              {hasComparison && (
                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", background: "#f8fafc", padding: "12px 14px", borderRadius: "8px", marginTop: "8px", border: "1px solid #e2e8f0" }}>
                                  <div>
                                    <span style={{ fontSize: "11px", fontWeight: 600, color: "#64748b", textTransform: "uppercase" }}>
                                      {leftDoc ? leftDoc.filename : "Source Document"} ({leftLabel})
                                    </span>
                                    <div style={{ fontSize: "13px", fontWeight: 600, color: "#1e293b", marginTop: 4 }}>
                                      {display(actualVal)}
                                    </div>
                                  </div>
                                  <div>
                                    <span style={{ fontSize: "11px", fontWeight: 600, color: "#64748b", textTransform: "uppercase" }}>
                                      {rightDoc ? rightDoc.filename : "Comparison Document"} ({rightLabel})
                                    </span>
                                    <div style={{ fontSize: "13px", fontWeight: 600, color: "#1e293b", marginTop: 4 }}>
                                      {display(expectedVal)}
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                    </div>
                  ) : (
                    <Empty
                      title="No SOP findings recorded"
                      detail="Run SOP compliance checks once documents are extracted."
                    />
                  )}
                </section>
              </div>
            )}

            {/* MODE 3: AUDIT TRAIL & HISTORY */}
            {activeMode === "reports" && (
              <div className="mode-view-reports">
                {/* Audit Timeline */}
                <section className="panel timeline-panel" style={{ padding: "20px 24px" }}>
                  <div className="section-head" style={{ marginBottom: 16 }}>
                    <h2 style={{ fontSize: "16px", margin: 0 }}>Audit Trail & History Timeline</h2>
                    <span className="count-pill">{data.timeline.length} events</span>
                  </div>

                  <div className="timeline">
                    {data.timeline.map((t) => (
                      <div key={t.id}>
                        <span className="timeline-dot" />
                        <section>
                          <strong>{t.event.replaceAll(".", " / ").replaceAll("_", " ")}</strong>
                          <p>
                            {formatDate(t.created_at)} ·{" "}
                            {t.actor === "worker"
                              ? "Automated Worker"
                              : t.actor === user?.id
                                ? "You"
                                : t.actor}
                          </p>
                          {devMode && (
                            <details style={{ marginTop: 4 }}>
                              <summary style={{ fontSize: "11px", color: "#64748b", cursor: "pointer" }}>Technical Details</summary>
                              <pre style={{ fontSize: "11px", marginTop: 4 }}>{JSON.stringify(t.details, null, 2)}</pre>
                            </details>
                          )}
                        </section>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {/* Bottom Maintenance Collapsible Drawer (For Admins & Developers Only) */}
            {data.can_review && devMode && (
              <details className="bottom-maintenance-drawer">
                <summary>
                  <Wrench size={15} />
                  <span>Case Maintenance & Developer Utilities</span>
                </summary>
                <div style={{ marginTop: 14 }}>
                  <BatchGroupingRepair
                    key={id}
                    batchIds={Array.from(
                      new Set(
                        data.documents
                          .map((d) => d.batch_id)
                          .filter((batchId): batchId is string => !!batchId),
                      ),
                    )}
                  />
                  {data.documents.some((d) => d.doc_type === "ektp" && d.status === "COMPLETED") && (
                    <EnumRevalidation caseId={id} refresh={refresh} />
                  )}
                  {data.can_adopt_configuration && (
                    <CaseConfiguration caseId={id} currentVersion={data.config_version} refresh={refresh} />
                  )}
                  <div style={{ marginTop: 12 }}>
                    <CaseTask caseId={data.id} />
                  </div>
                </div>
              </details>
            )}
          </div>
        )
      )}

      {/* Action Modal (Corrections, Classification, Move, Reconcile) */}
      {action && (
        <ActionModal
          action={action}
          onClose={close}
          onComplete={async () => {
            close();
            await refresh();
          }}
        />
      )}
    </Shell>
  );
}

function ActionModal({
  action,
  onClose,
  onComplete,
}: {
  action: Action;
  onClose: () => void;
  onComplete: () => Promise<void>;
}) {
  const { notify, devMode } = usePlatform(),
    { data: cases } = useData<{ items: CaseSummary[] }>("/cases?limit=100", 0);
  const { data: cfg } = useData<ConfigResponse>("/config", 0);
  const [reason, setReason] = useState(""),
    [type, setType] = useState(
      action.doc.doc_type === "unknown" ? "application" : action.doc.doc_type,
    ),
    [target, setTarget] = useState("");

  const originalFieldVal =
    action.doc.overrides?.[action.field || ""] ??
    action.doc.raw?.[action.field || ""] ??
    null;

  type PageInitialItem = {
    page_number: number;
    footer_present: boolean;
    evidence: string;
  };

  const isPageInitialsField =
    (action.field || "").toLowerCase().includes("page_initials") ||
    Boolean(
      originalFieldVal &&
        typeof originalFieldVal === "object" &&
        "pages" in (originalFieldVal as Record<string, unknown>),
    );

  const isSignatureOrStampField =
    !isPageInitialsField &&
    Boolean(
      (originalFieldVal &&
        typeof originalFieldVal === "object" &&
        ("present" in (originalFieldVal as Record<string, unknown>) ||
          "stamp_present" in (originalFieldVal as Record<string, unknown>))) ||
        (action.field || "").toLowerCase().includes("signature") ||
        (action.field || "").toLowerCase().includes("stamp"),
    );

  const getInitialPages = (): PageInitialItem[] => {
    if (
      originalFieldVal &&
      typeof originalFieldVal === "object" &&
      "pages" in (originalFieldVal as Record<string, unknown>)
    ) {
      const pages = (originalFieldVal as { pages: unknown[] }).pages;
      if (Array.isArray(pages) && pages.length) {
        return pages.map((p, idx) => {
          const item = (typeof p === "object" && p !== null ? p : {}) as Record<string, unknown>;
          return {
            page_number: typeof item.page_number === "number" ? item.page_number : idx + 1,
            footer_present: item.footer_present === true,
            evidence: typeof item.evidence === "string" ? item.evidence : "",
          };
        });
      }
    }
    return [
      { page_number: 1, footer_present: true, evidence: "" },
      { page_number: 2, footer_present: true, evidence: "" },
      { page_number: 3, footer_present: true, evidence: "" },
      { page_number: 4, footer_present: false, evidence: "Main signing block page" },
    ];
  };

  const getInitialSig = () => {
    const o = (originalFieldVal && typeof originalFieldVal === "object" ? originalFieldVal : {}) as Record<string, unknown>;
    return {
      present: o.present === true || o.stamp_present === true,
      complete: o.complete !== false,
      page_number: typeof o.page_number === "number" ? o.page_number : 1,
      signer_name: typeof o.name === "string" ? o.name : typeof o.text === "string" ? o.text : "",
      evidence: typeof o.evidence === "string" ? o.evidence : "",
    };
  };

  const [pageList, setPageList] = useState<PageInitialItem[]>(() => getInitialPages());
  const [sigData, setSigData] = useState(() => getInitialSig());

  const getInitialText = (val: unknown): string => {
    if (val === null || val === undefined) return "";
    if (typeof val === "object") {
      const o = val as Record<string, unknown>;
      if (o.raw !== undefined && o.raw !== null) return String(o.raw);
      if (o.amount_raw !== undefined && o.amount_raw !== null) return String(o.amount_raw);
      if (o.selected !== undefined && o.selected !== null)
        return Array.isArray(o.selected) ? o.selected.join(", ") : String(o.selected);
      if (o.text !== undefined && o.text !== null) return String(o.text);
      if (o.name !== undefined && o.name !== null) return String(o.name);
      return "";
    }
    return String(val);
  };

  const getInitialCurrency = (val: unknown): string => {
    if (val && typeof val === "object") {
      const o = val as Record<string, unknown>;
      return String(o.currency ?? o.currency_raw ?? "");
    }
    return "";
  };

  const [textValue, setTextValue] = useState(() => getInitialText(originalFieldVal));
  const [currencyValue, setCurrencyValue] = useState(() => getInitialCurrency(originalFieldVal));
  const [isJsonMode, setIsJsonMode] = useState(false);
  const [rawJsonValue, setRawJsonValue] = useState(() => JSON.stringify(originalFieldVal, null, 2));

  const [providerId, setProviderId] = useState("");
  const [pending, setPending] = useState(false),
    [error, setError] = useState("");

  const title = {
    classification: "Confirm Document Type",
    correction: "Correct Field Value",
    move: "Move Document to Another Case",
    reconcile: "Reconcile External Submission",
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
            if (action.kind === "correction") {
              let correctionPayload: unknown;
              if (isJsonMode) {
                correctionPayload = JSON.parse(rawJsonValue);
              } else if (isPageInitialsField) {
                correctionPayload = {
                  page_count: pageList.length,
                  pages: pageList.map((p) => ({
                    page_number: p.page_number,
                    footer_present: p.footer_present,
                    non_text: true,
                    complete: true,
                    evidence:
                      p.evidence ||
                      (p.footer_present ? "Initials verified by reviewer" : "No initials observed"),
                  })),
                };
              } else if (isSignatureOrStampField) {
                correctionPayload = {
                  present: sigData.present,
                  complete: sigData.complete,
                  page_number: Number(sigData.page_number) || 1,
                  non_text: true,
                  ...(sigData.signer_name ? { name: sigData.signer_name, text: sigData.signer_name } : {}),
                  evidence:
                    sigData.evidence ||
                    (sigData.present ? "Signature/stamp verified by reviewer" : "Absence verified"),
                };
              } else {
                if (
                  originalFieldVal &&
                  typeof originalFieldVal === "object" &&
                  !Array.isArray(originalFieldVal)
                ) {
                  const orig = { ...(originalFieldVal as Record<string, unknown>) };
                  if ("raw" in orig || "currency" in orig) {
                    orig.raw = textValue;
                    if (currencyValue.trim()) orig.currency = currencyValue.trim();
                    correctionPayload = orig;
                  } else if ("amount_raw" in orig || "currency_raw" in orig) {
                    orig.amount_raw = textValue;
                    if (currencyValue.trim()) orig.currency_raw = currencyValue.trim();
                    correctionPayload = orig;
                  } else if ("selected" in orig) {
                    orig.selected = textValue;
                    correctionPayload = orig;
                  } else {
                    orig.raw = textValue;
                    if (currencyValue.trim()) orig.currency = currencyValue.trim();
                    correctionPayload = orig;
                  }
                } else {
                  correctionPayload = textValue;
                }
              }
              await api(base + "/corrections", {
                method: "POST",
                body: JSON.stringify({
                  field: action.field || "",
                  value: correctionPayload,
                  reason,
                }),
              });
            }
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
            notify("Action recorded in audit trail.");
            await onComplete();
          } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to process action.");
          } finally {
            setPending(false);
          }
        }}
      >
        <p className="muted">{action.doc.filename}</p>
        {error && <ErrorNotice message={error} />}
        {action.kind === "classification" && (
          <label>
            Verified Document Type
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {cfg &&
                Object.entries(cfg.payload.profiles).map(([profileId, p]) => (
                  <option value={profileId} key={profileId}>
                    {p.label}
                  </option>
                ))}
            </select>
          </label>
        )}
        {action.kind === "correction" && (
          <div className="correction-fields-group" style={{ marginBottom: 14 }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 8,
              }}
            >
              <span
                style={{
                  fontSize: "12px",
                  fontWeight: 700,
                  color: "#1e293b",
                  textTransform: "uppercase",
                }}
              >
                {action.field ? `${action.field.replaceAll("_", " ")} (${action.field})` : "Field"}
              </span>
              {devMode && (
                <button
                  type="button"
                  className="text-link"
                  style={{ fontSize: "11px" }}
                  onClick={() => setIsJsonMode((m) => !m)}
                >
                  {isJsonMode ? "Switch to Form Mode" : "Switch to Raw JSON"}
                </button>
              )}
            </div>

            {isJsonMode ? (
              <label>
                Payload JSON
                <textarea
                  className="code-input"
                  rows={6}
                  value={rawJsonValue}
                  onChange={(e) => setRawJsonValue(e.target.value)}
                  required
                />
              </label>
            ) : isPageInitialsField ? (
              <div style={{ marginBottom: 12 }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 8,
                  }}
                >
                  <label style={{ margin: 0, fontWeight: 600, fontSize: "12px" }}>
                    RIPLAY Physical Page Verification ({pageList.length} Pages)
                  </label>
                  <button
                    type="button"
                    className="text-link"
                    style={{ fontSize: "11px" }}
                    onClick={() =>
                      setPageList((prev) => [
                        ...prev,
                        { page_number: prev.length + 1, footer_present: true, evidence: "" },
                      ])
                    }
                  >
                    + Add Page
                  </button>
                </div>
                <div className="grouped-pages-grid">
                  {pageList.map((p, idx) => (
                    <div key={p.page_number} className="page-group-card">
                      <span className="page-num-tag">Page {p.page_number}</span>
                      <select
                        value={p.footer_present ? "true" : "false"}
                        onChange={(e) => {
                          const nextPresent = e.target.value === "true";
                          setPageList((prev) =>
                            prev.map((item, i) =>
                              i === idx ? { ...item, footer_present: nextPresent } : item,
                            ),
                          );
                        }}
                      >
                        <option value="true">Present (Initials)</option>
                        <option value="false">Absent / Blank</option>
                      </select>
                      <input
                        type="text"
                        value={p.evidence}
                        onChange={(e) => {
                          const val = e.target.value;
                          setPageList((prev) =>
                            prev.map((item, i) =>
                              i === idx ? { ...item, evidence: val } : item,
                            ),
                          );
                        }}
                        placeholder="Evidence / notes (e.g. initials visible at bottom right)"
                      />
                    </div>
                  ))}
                </div>
                <p className="subtext" style={{ marginTop: 6 }}>
                  Review initials for each page. Verified values update the RIPLAY compliance audit trail automatically.
                </p>
              </div>
            ) : isSignatureOrStampField ? (
              <div style={{ marginBottom: 12 }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "10px" }}>
                  <label>
                    Mark / Stamp Status
                    <select
                      value={sigData.present ? "true" : "false"}
                      onChange={(e) => setSigData({ ...sigData, present: e.target.value === "true" })}
                    >
                      <option value="true">Present (Mark Observed)</option>
                      <option value="false">Absent (Blank Area)</option>
                    </select>
                  </label>
                  <label>
                    Completeness
                    <select
                      value={sigData.complete ? "true" : "false"}
                      onChange={(e) => setSigData({ ...sigData, complete: e.target.value === "true" })}
                    >
                      <option value="true">Complete / Legible</option>
                      <option value="false">Incomplete / Cropped</option>
                    </select>
                  </label>
                  <label>
                    Physical Page #
                    <input
                      type="number"
                      min={1}
                      value={sigData.page_number}
                      onChange={(e) => setSigData({ ...sigData, page_number: Number(e.target.value) || 1 })}
                      required
                    />
                  </label>
                  <label>
                    Signer Name / Visible Text
                    <input
                      type="text"
                      value={sigData.signer_name}
                      onChange={(e) => setSigData({ ...sigData, signer_name: e.target.value })}
                      placeholder="e.g. Customer Name, Branch Stamp"
                    />
                  </label>
                </div>
                <label>
                  Evidence / Location Notes
                  <input
                    type="text"
                    value={sigData.evidence}
                    onChange={(e) => setSigData({ ...sigData, evidence: e.target.value })}
                    placeholder="e.g. Signature clearly visible in signing block"
                  />
                </label>
              </div>
            ) : (
              <>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns:
                      originalFieldVal &&
                      typeof originalFieldVal === "object" &&
                      ("currency" in originalFieldVal ||
                        "currency_raw" in originalFieldVal ||
                        (action.field || "").toLowerCase().includes("amount") ||
                        (action.field || "").toLowerCase().includes("total"))
                        ? "1fr 140px"
                        : "1fr",
                    gap: "12px",
                    marginBottom: "8px",
                  }}
                >
                  <label>
                    Target Value
                    <input
                      type="text"
                      value={textValue}
                      onChange={(e) => setTextValue(e.target.value)}
                      placeholder="Enter the correct value as visible on the document…"
                      required
                    />
                  </label>
                  {originalFieldVal &&
                    typeof originalFieldVal === "object" &&
                    ("currency" in originalFieldVal ||
                      "currency_raw" in originalFieldVal ||
                      (action.field || "").toLowerCase().includes("amount") ||
                      (action.field || "").toLowerCase().includes("total")) && (
                      <label>
                        Currency
                        <input
                          type="text"
                          value={currencyValue}
                          onChange={(e) => setCurrencyValue(e.target.value.toUpperCase())}
                          placeholder="e.g. USD, CNY, IDR"
                        />
                      </label>
                    )}
                </div>
                <p className="subtext">
                  Correction is recorded in the audit trail. Original values remain preserved; SOP rules will be evaluated automatically.
                </p>
              </>
            )}
          </div>
        )}
        {action.kind === "move" && (
          <label>
            Select Target Case
            <select
              required
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            >
              <option value="">Select case…</option>
              {cases?.items
                .filter((c) => c.id !== action.doc.case_id)
                .map((c) => (
                  <option value={c.id} key={c.id}>
                    {c.reference} — {c.customer}
                  </option>
                ))}
            </select>
          </label>
        )}
        {action.kind === "reconcile" && (
          <>
            <p className="muted">
              Reconcile external provider submission.
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
          Reason for this Action (Required for banking audit trail)
          <textarea
            required
            minLength={5}
            maxLength={1000}
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Explain the reason for this correction or cite visible document evidence…"
          />
        </label>
        <div className="modal-actions">
          <button className="secondary" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="primary" disabled={pending}>
            {pending ? "Saving…" : "Confirm Action"}
            <Check size={16} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
