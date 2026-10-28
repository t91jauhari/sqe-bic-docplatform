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
import { extractionCheck } from "@/lib/extraction-export";
import { downloadMultiSheetExcel } from "@/lib/excel-multi-sheet";
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

  const [activeMode, setActiveMode] = useState<"documents" | "sop" | "reports">("documents");
  const [selected, setSelected] = useState("");
  const [findingFilter, setFindingFilter] = useState<"all" | "attention" | "visual" | "pass">("all");
  const [action, setAction] = useState<Action | null>(null);
  const [pending, setPending] = useState(false);
  const [exporting, setExporting] = useState(false);

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
        d: Document,
        field: string,
        value: unknown,
      ): [string, string] => {
        const columns =
          cfg?.payload.profiles[
            d.doc_type as keyof typeof cfg.payload.profiles
          ]?.columns;
        const label = columns?.find(([key]) => key === field)?.[1] || field;
        const text =
          value == null &&
          d.validation?.fields?.[field]?.issues?.some((issue) =>
            ["UNRECOGNIZED_ENUM", "INVALID_OR_MISSING_ENUM"].includes(issue.code),
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
    } catch (err) {
      notify(
        err instanceof Error ? err.message : "Unable to export extraction to Excel.",
        "error",
      );
    } finally {
      setExporting(false);
    }
  };

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
        <Busy label="Membuka berkas kasus nasabah…" />
      ) : (
        data && (
          <div className="case-page-container">
            {/* Breadcrumb Navigation */}
            <nav className="case-breadcrumb-bar" aria-label="Breadcrumb">
              <Link href="/" className="bc-link">Beranda</Link>
              <span className="bc-sep">/</span>
              <Link href="/cases" className="bc-link">Daftar Kasus</Link>
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
                      <span className="pill-branch">Cabang: {data.branch_id}</span>
                      <StatusBadge value={data.status} />
                      <SopBadge value={data.validation_status} />
                    </div>
                  </div>
                </div>

                <div className="exec-actions">
                  {report && (
                    <a
                      className="btn-secondary-action"
                      href={`/api/reports/${report.id}/download?format=pdf`}
                      title="Unduh Lembar Kertas Kerja Resmi"
                    >
                      <Download size={15} />
                      <span>Kertas Kerja v{report.version}</span>
                    </a>
                  )}

                  {data.can_review && data.status === "READY" && report && report.state !== "FINAL" && (
                    <button
                      className="btn-primary-action"
                      disabled={pending}
                      onClick={() =>
                        void run(
                          () => api(`/reports/${report.id}/approve`, { method: "POST" }),
                          "Kertas kerja disetujui & laporan resmi dirilis.",
                        )
                      }
                    >
                      <ShieldCheck size={16} />
                      <span>Setujui & Rilis Kertas Kerja</span>
                    </button>
                  )}

                  {data.can_write && (
                    <Link
                      className="btn-secondary-action"
                      href={`/upload?case=${id}&branch=${data.branch_id}`}
                    >
                      <Upload size={15} />
                      <span>Upload Dokumen</span>
                    </Link>
                  )}
                </div>
              </div>

              {/* Integrated 4-Step Workflow Pipeline */}
              <div className="exec-stepper-wrap">
                <div className="pipeline-steps">
                  {/* Step 1: Document Intake */}
                  <div className={`pipeline-step ${data.documents_count > 0 ? "step-done" : "step-pending"}`}>
                    <div className="step-indicator">1</div>
                    <div className="step-content">
                      <div className="step-name">1. Dokumen Masuk</div>
                      <div className="step-desc">
                        {data.documents_count > 0 ? `${data.documents_count} berkas terunggah` : "Menunggu berkas"}
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
                      <div className="step-name">2. Ekstraksi AI</div>
                      <div className="step-desc">
                        {data.documents.some((d) => ["RUNNING", "PROCESSING", "QUEUED"].includes(d.status))
                          ? `Diproses (${data.completed_count}/${data.documents_count})`
                          : data.documents.some((d) => ["ERROR", "PROCESSING_ERROR"].includes(d.status))
                            ? `Perlu Perhatian (${data.documents.filter((d) => ["ERROR", "PROCESSING_ERROR"].includes(d.status)).length} gagal)`
                            : `${data.completed_count}/${data.documents_count} selesai`}
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
                      <div className="step-name">3. Kepatuhan SOP</div>
                      <div className="step-desc">
                        {data.status === "SOP_ERROR"
                          ? "Evaluasi terhenti"
                          : ["PASS", "COMPLIANT"].includes(data.validation_status)
                            ? "Semua aturan sesuai"
                            : ["REVIEW", "FAIL"].includes(data.validation_status)
                              ? "Ada temuan verifikasi"
                              : "Menunggu ekstraksi"}
                      </div>
                    </div>
                  </div>
                  <div className="pipeline-connector" />

                  {/* Step 4: Kertas Kerja */}
                  <div className={`pipeline-step ${
                    report?.state === "FINAL"
                      ? "step-done"
                      : report
                        ? "step-ready"
                        : "step-pending"
                  }`}>
                    <div className="step-indicator">4</div>
                    <div className="step-content">
                      <div className="step-name">4. Kertas Kerja</div>
                      <div className="step-desc">
                        {report?.state === "FINAL"
                          ? `Selesai v${report.version}`
                          : report
                            ? `Draft siap v${report.version}`
                            : "Menunggu SOP"}
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
                    Evaluasi SOP Terhenti Sementara
                  </strong>
                  <div style={{ fontSize: "13px", opacity: 0.85, marginTop: 2 }}>
                    Pemeriksaan SOP mengalami kendala jaringan. Seluruh hasil ekstraksi tetap utuh dan tersimpan aman. Klik untuk evaluasi ulang.
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
                        notify("Pemeriksaan SOP dijalankan ulang menggunakan hasil ekstraksi tersimpan.");
                        await refresh();
                      } catch (e) {
                        notify(e instanceof Error ? e.message : "Gagal menjalankan ulang.", "error");
                      } finally {
                        setPending(false);
                      }
                    }}
                  >
                    <RotateCcw size={15} />
                    Evaluasi Ulang SOP
                  </button>
                )}
              </div>
            )}

            {/* Missing documents callout */}
            {report?.snapshot.missing.length ? (
              <div className="missing-strip">
                <Clock3 size={18} />
                <strong>Menunggu Dokumen Prasyarat:</strong>
                {report.snapshot.missing
                  .map(
                    (x) =>
                      cfg?.payload.profiles[x as keyof typeof cfg.payload.profiles]?.label || x,
                  )
                  .join(", ")}
              </div>
            ) : null}

            {/* 3-Mode Primary Navigation Tabs */}
            <nav className="workspace-mode-tabs" aria-label="Mode kerja kasus">
              <button
                type="button"
                className={`mode-tab-btn ${activeMode === "documents" ? "active" : ""}`}
                onClick={() => setActiveMode("documents")}
              >
                <FileText size={17} />
                <span>1. Dokumen & Data Ekstraksi</span>
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
                <span>2. Evaluasi Kepatuhan SOP</span>
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
                <FileCheck2 size={17} />
                <span>3. Kertas Kerja & Riwayat Audit</span>
                {report && <span className="mode-tab-count">v{report.version}</span>}
              </button>
            </nav>

            {/* MODE 1: DOKUMEN & EKSTRAKSI DATA */}
            {activeMode === "documents" && (
              <div className="mode-view-documents">
                {/* Document Selector Chips Bar */}
                <div className="document-selector-bar">
                  <span className="selector-bar-label">PILIH DOKUMEN:</span>
                  {data.documents.map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      className={`doc-chip-btn ${doc?.id === d.id ? "selected" : ""}`}
                      onClick={() => setSelected(d.id)}
                    >
                      <FileText size={16} />
                      <div>
                        <strong>{d.filename}</strong>
                        <small>
                          {cfg?.payload.profiles[d.doc_type as keyof typeof cfg.payload.profiles]?.label || d.doc_type}
                        </small>
                      </div>
                      <Badge value={d.status} />
                    </button>
                  ))}

                  {exportableDocs.length > 0 && (
                    <button
                      className="btn-secondary-action"
                      style={{ marginLeft: "auto", fontSize: "12px", padding: "6px 12px" }}
                      disabled={exporting}
                      onClick={exportAllDocuments}
                      title="Ekspor seluruh hasil ekstraksi ke file Excel"
                    >
                      <Download size={14} />
                      <span>{exporting ? "Mengekspor…" : "Ekspor Excel"}</span>
                    </button>
                  )}

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
                              ? `Memproses ulang ${res.queued.length} dokumen yang sempat gagal.`
                              : "Tidak ada dokumen yang perlu diproses ulang.",
                          );
                          await refresh();
                        } catch (e) {
                          notify(e instanceof Error ? e.message : "Gagal memproses ulang.", "error");
                        } finally {
                          setPending(false);
                        }
                      }}
                    >
                      <RotateCcw size={14} />
                      Coba Ulang Gagal ({failedDocs.length})
                    </button>
                  )}
                </div>

                {/* Document Inspection Content */}
                {doc ? (
                  <section className="panel evidence-panel" style={{ padding: "20px 24px" }}>
                    <div className="section-head" style={{ marginBottom: 16 }}>
                      <div>
                        <h2 style={{ fontSize: "16px", margin: 0 }}>{doc.filename}</h2>
                        <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: "12px" }}>
                          Tipe Dokumen: <strong>{cfg?.payload.profiles[doc.doc_type as keyof typeof cfg.payload.profiles]?.label || doc.doc_type}</strong> · Status: <Badge value={doc.status} />
                        </p>
                      </div>
                      <div className="document-actions-right" style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <CopyExtraction
                          doc={doc}
                          columns={cfg?.payload.profiles[doc.doc_type as keyof typeof cfg.payload.profiles]?.columns}
                          provider={cfg?.payload.provider}
                        />
                        {data.can_review && ["COMPLETED", "ERROR", "NEEDS_CLASSIFICATION"].includes(doc.status) && (
                          <button
                            className="text-link"
                            style={{ fontSize: "12px" }}
                            onClick={() => setAction({ kind: "move", doc })}
                          >
                            <MoveRight size={14} />
                            Pindah Kasus
                          </button>
                        )}
                      </div>
                    </div>

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
                            ? "Perlu tindakan sebelum ekstraksi"
                            : doc.status === "COMPLETED"
                              ? "Tidak ada nilai atribut terbaca"
                              : "Sedang diproses AI di latar belakang"
                        }
                        detail={
                          doc.status === "COMPLETED"
                            ? "Model ekstraksi tidak mendeteksi nilai bidang pada dokumen ini."
                            : "Sistem sedang membaca dan memverifikasi isi dokumen secara otomatis."
                        }
                      />
                    )}
                  </section>
                ) : (
                  <Empty
                    title="Belum ada dokumen pada kasus ini"
                    detail="Unggah dokumen transaksi atau identitas nasabah untuk memulai ekstraksi otomatis."
                  />
                )}
              </div>
            )}

            {/* MODE 2: EVALUASI KEPATUHAN SOP */}
            {activeMode === "sop" && (
              <div className="mode-view-sop">
                <CaseSOP data={data} refresh={refresh} />

                {/* SOP Findings Section */}
                <section className="panel findings-section" style={{ marginTop: 20, padding: "20px 24px" }}>
                  <div className="field-evidence-toolbar" style={{ margin: "-20px -24px 16px", padding: "12px 24px" }}>
                    <div className="field-filter-pills">
                      {[
                        ["all", "Semua Temuan", report?.snapshot.findings.length || 0],
                        [
                          "attention",
                          "Perlu Perhatian",
                          report?.snapshot.findings.filter((f) => ["FAIL", "REVIEW", "ERROR"].includes(f.result)).length || 0,
                        ],
                        [
                          "visual",
                          "Pemeriksaan Visual",
                          report?.snapshot.findings.filter((f) => f.evaluation_type === "VISUAL").length || 0,
                        ],
                        [
                          "pass",
                          "Sesuai (Pass)",
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
                    <Link className="secondary compact-btn" href={`/cases/${id}/review`}>
                      <ShieldCheck size={14} />
                      Buka Review Visual
                    </Link>
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
                                      {leftDoc ? leftDoc.filename : "Nilai Sumber"} ({leftLabel})
                                    </span>
                                    <div style={{ fontSize: "13px", fontWeight: 600, color: "#1e293b", marginTop: 4 }}>
                                      {display(actualVal)}
                                    </div>
                                  </div>
                                  <div>
                                    <span style={{ fontSize: "11px", fontWeight: 600, color: "#64748b", textTransform: "uppercase" }}>
                                      {rightDoc ? rightDoc.filename : "Nilai Pembanding"} ({rightLabel})
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
                      title="Belum ada temuan SOP"
                      detail="Jalankan evaluasi SOP setelah dokumen selesai diekstraksi."
                    />
                  )}
                </section>
              </div>
            )}

            {/* MODE 3: KERTAS KERJA & RIWAYAT AUDIT */}
            {activeMode === "reports" && (
              <div className="mode-view-reports">
                {report ? (
                  <section className="panel report-summary-panel" style={{ padding: "20px 24px", marginBottom: 20 }}>
                    <div className="section-head">
                      <div>
                        <h2 style={{ fontSize: "17px", margin: 0 }}>Kertas Kerja Resmi (Work Paper v{report.version})</h2>
                        <p style={{ color: "#64748b", fontSize: "13px", margin: "4px 0 0" }}>
                          Status Laporan: <Badge value={report.state} /> · Diterbitkan: {formatDate(report.created_at)}
                        </p>
                      </div>
                      <div style={{ display: "flex", gap: "10px" }}>
                        <a
                          className="btn-primary-action"
                          href={`/api/reports/${report.id}/download?format=pdf`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <Download size={15} />
                          Unduh PDF Resmi
                        </a>
                      </div>
                    </div>
                  </section>
                ) : (
                  <Empty
                    title="Kertas kerja belum siap"
                    detail="Selesaikan ekstraksi dokumen dan evaluasi kepatuhan SOP terlebih dahulu."
                  />
                )}

                {/* Audit Timeline */}
                <section className="panel timeline-panel" style={{ padding: "20px 24px" }}>
                  <div className="section-head" style={{ marginBottom: 16 }}>
                    <h2 style={{ fontSize: "16px", margin: 0 }}>Jejak Audit & Riwayat Kasus (Audit Timeline)</h2>
                    <span className="count-pill">{data.timeline.length} aktivitas</span>
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
                              ? "Sistem Otomatis (Worker)"
                              : t.actor === user?.id
                                ? "Anda"
                                : t.actor}
                          </p>
                          <details style={{ marginTop: 4 }}>
                            <summary style={{ fontSize: "11px", color: "#64748b", cursor: "pointer" }}>Rincian Teknis</summary>
                            <pre style={{ fontSize: "11px", marginTop: 4 }}>{JSON.stringify(t.details, null, 2)}</pre>
                          </details>
                        </section>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {/* Bottom Maintenance Collapsible Drawer (For Admins & Developers Only) */}
            {data.can_review && (
              <details className="bottom-maintenance-drawer">
                <summary>
                  <Wrench size={15} />
                  <span>Pengaturan Pemeliharaan Kasus (Admin & Developer)</span>
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
  const { notify } = usePlatform(),
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

  const getInitialText = (val: unknown): string => {
    if (val === null || val === undefined) return "";
    if (typeof val === "object") {
      const o = val as Record<string, unknown>;
      if (o.raw !== undefined && o.raw !== null) return String(o.raw);
      if (o.amount_raw !== undefined && o.amount_raw !== null) return String(o.amount_raw);
      if (o.selected !== undefined && o.selected !== null) return Array.isArray(o.selected) ? o.selected.join(", ") : String(o.selected);
      if (o.text !== undefined && o.text !== null) return String(o.text);
      if (o.name !== undefined && o.name !== null) return String(o.name);
      return JSON.stringify(o);
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
    classification: "Konfirmasi Jenis Dokumen",
    correction: "Koreksi Nilai Atribut",
    move: "Pindah Berkas ke Kasus Lain",
    reconcile: "Rekonsiliasi Permintaan",
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
              } else {
                if (originalFieldVal && typeof originalFieldVal === "object" && !Array.isArray(originalFieldVal)) {
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
            notify("Aktivitas berhasil dicatat dalam jejak audit.");
            await onComplete();
          } catch (err) {
            setError(err instanceof Error ? err.message : "Tindakan gagal diproses.");
          } finally {
            setPending(false);
          }
        }}
      >
        <p className="muted">{action.doc.filename}</p>
        {error && <ErrorNotice message={error} />}
        {action.kind === "classification" && (
          <label>
            Jenis Dokumen Terverifikasi
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
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <span style={{ fontSize: "12px", fontWeight: 700, color: "#1e293b", textTransform: "uppercase" }}>
                {action.field ? `${action.field.replaceAll("_", " ")} (${action.field})` : "Bidang"}
              </span>
              <button
                type="button"
                className="text-link"
                style={{ fontSize: "11px" }}
                onClick={() => setIsJsonMode((m) => !m)}
              >
                {isJsonMode ? "Gunakan Formulir Teks" : "Gunakan Mode JSON"}
              </button>
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
            ) : (
              <>
                <div style={{ display: "grid", gridTemplateColumns: (originalFieldVal && typeof originalFieldVal === "object" && ("currency" in originalFieldVal || "currency_raw" in originalFieldVal || (action.field || "").toLowerCase().includes("amount") || (action.field || "").toLowerCase().includes("total"))) ? "1fr 140px" : "1fr", gap: "12px", marginBottom: "8px" }}>
                  <label>
                    Nilai Koreksi yang Benar
                    <input
                      type="text"
                      value={textValue}
                      onChange={(e) => setTextValue(e.target.value)}
                      placeholder="Masukkan nilai yang terbaca pada dokumen..."
                      required
                    />
                  </label>
                  {(originalFieldVal && typeof originalFieldVal === "object" && ("currency" in originalFieldVal || "currency_raw" in originalFieldVal || (action.field || "").toLowerCase().includes("amount") || (action.field || "").toLowerCase().includes("total"))) && (
                    <label>
                      Mata Uang
                      <input
                        type="text"
                        value={currencyValue}
                        onChange={(e) => setCurrencyValue(e.target.value.toUpperCase())}
                        placeholder="contoh: USD, CNY, IDR"
                      />
                    </label>
                  )}
                </div>
                <p className="subtext">
                  Koreksi dicatat ke audit trail. Nilai asli tersimpan; aturan SOP akan diperiksa ulang otomatis.
                </p>
              </>
            )}
          </div>
        )}
        {action.kind === "move" && (
          <label>
            Pilih Kasus Tujuan
            <select
              required
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            >
              <option value="">Pilih kasus...</option>
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
              Rekonsiliasi berkas penyedia eksternal.
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
          Alasan Tindakan (Wajib diisi untuk audit perbankan)
          <textarea
            required
            minLength={5}
            maxLength={1000}
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Jelaskan alasan koreksi atau bukti yang terlihat pada berkas..."
          />
        </label>
        <div className="modal-actions">
          <button className="secondary" type="button" onClick={onClose}>
            Batal
          </button>
          <button className="primary" disabled={pending}>
            {pending ? "Menyimpan…" : "Konfirmasi Tindakan"}
            <Check size={16} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
