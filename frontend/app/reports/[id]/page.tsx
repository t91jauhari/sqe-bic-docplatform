"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Download,
  FileCheck2,
  Files,
  ListChecks,
  ShieldCheck,
  FileSpreadsheet,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { useData, usePlatform } from "@/components/platform-provider";
import { api } from "@/lib/api";
import { Badge, Busy, ErrorNotice, display, formatDate } from "@/components/ui";
import { ForexPackageSummary } from "@/components/forex-package-summary";
import type { Finding } from "@/lib/types";

type Report = {
  id: string;
  case_id: string;
  customer: string;
  version: number;
  state: string;
  created_at: number;
  validation_status: string;
  provider: string;
  reference: string;
  case_status?: string;
  approved_by?: string | null;
  snapshot: {
    report_title?: string;
    config_version?: number;
    scores?: Record<string, number | null>;
    sop_packages?: import("@/lib/types").SOPPackages;
    sop_summary?: import("@/lib/types").SOPSummary;
    missing?: string[];
    findings: Finding[];
    documents: {
      id: string;
      filename: string;
      doc_type: string;
      status: string;
      normalized: Record<string, unknown>;
    }[];
  };
};
const CATEGORY_LABELS: Record<string, { label: string; desc: string }> = {
  DATA_COMPLETION: {
    label: "Kelengkapan Data Transaksi",
    desc: "Kesesuaian identitas, formulir aplikasi, dan data nominal",
  },
  CUSTOMER_SIGNATURE: {
    label: "Keabsahan Tanda Tangan & Meterai",
    desc: "Verifikasi spesimen tanda tangan dan meterai Rp 10.000",
  },
  DOCUMENT_COMPLETION: {
    label: "Kelengkapan Dokumen Underlying",
    desc: "Faktur/invoice komersial, e-KTP, dan surat pernyataan",
  },
  OFFICER_REVIEW_APPROVAL: {
    label: "Verifikasi Pejabat Bank",
    desc: "Pemeriksaan pejabat cabang dan kontrol maker-checker",
  },
  total_a: {
    label: "Subtotal A: Data & Tanda Tangan",
    desc: "Kepatuhan data administratif dan keabsahan tanda tangan",
  },
  total_b: {
    label: "Subtotal B: Dokumen & Persetujuan",
    desc: "Kepatuhan underlying transaksi dan otorisasi bank",
  },
  total: {
    label: "Hasil Kepatuhan Akhir (Final KKP)",
    desc: "Hasil evaluasi kepatuhan menyeluruh untuk laporan audit",
  },
};

export default function ReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params),
    router = useRouter();
  const { data, error, loading, refresh } = useData<Report>(`/reports/${id}`);
  const { notify } = usePlatform();
  const [filter, setFilter] = useState("attention"),
    [query, setQuery] = useState("");
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState("");

  const handleApprove = async () => {
    if (!data) return;
    setApproving(true);
    setApproveError("");
    try {
      await api(`/reports/${data.id}/approve`, { method: "POST" });
      notify(
        "Kertas kerja berhasil disetujui & difinalisasi (Report released).",
        "success",
      );
      await refresh();
    } catch (e) {
      const msg =
        e instanceof Error ? e.message : "Gagal memfinalisasi laporan.";
      setApproveError(msg);
      notify(msg, "error");
    } finally {
      setApproving(false);
    }
  };

  useEffect(() => {
    if (data && data.id !== id) router.replace(`/reports/${data.id}`);
  }, [data, id, router]);
  const findings = (data?.snapshot.findings || []).filter(
    (f) =>
      (filter === "all" || ["FAIL", "REVIEW", "ERROR"].includes(f.result)) &&
      `${f.rule_id} ${f.field} ${f.message}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <Shell
      title={data ? `Kertas kerja · ${data.customer}` : "Kertas kerja"}
      subtitle={
        data
          ? `${data.reference} · Latest version ${data.version} · Generated ${formatDate(data.created_at)}`
          : "Opening the latest report…"
      }
      action={
        <Link className="secondary" href="/reports">
          <ArrowLeft size={16} />
          All customer reports
        </Link>
      }
    >
      {error && <ErrorNotice message={error} retry={() => void refresh()} />}
      {loading && !data && <Busy />}
      {data && (
        <div className="report-detail">
          <section className="panel settings-card">
            <div className="section-head">
              <div>
                <h2 className="illustrated-heading">
                  <span>
                    <FileCheck2 size={21} />
                  </span>
                  {data.snapshot.report_title || "Customer kertas kerja"}
                </h2>
                <p>
                  Latest saved report for this case. Read the findings below or
                  download a copy.
                </p>
              </div>
              <div className="button-row">
                <a
                  className="btn-primary-action"
                  style={{ background: "#16a34a", borderColor: "#15803d", color: "#ffffff", display: "inline-flex", alignItems: "center", gap: 6 }}
                  href={`/api/reports/${data.id}/download?format=xlsx`}
                  title="Download Kertas Kerja in Excel format (.xlsx)"
                >
                  <FileSpreadsheet size={15} />
                  <span>Unduh Excel (XLSX)</span>
                </a>
                <a
                  className="secondary"
                  href={`/api/reports/${data.id}/download?format=pdf`}
                  title="Download PDF format"
                >
                  <Download size={15} />
                  PDF
                </a>
                <a
                  className="secondary"
                  href={`/api/reports/${data.id}/download?format=json`}
                  title="Download JSON format"
                >
                  <Download size={15} />
                  JSON
                </a>
              </div>
            </div>
            <div className="report-summary-grid">
              <div>
                <small>Customer</small>
                <strong>{data.customer}</strong>
              </div>
              <div>
                <small>Report version</small>
                <strong>v{data.version}</strong>
              </div>
              <div>
                <small>Release Status</small>
                <Badge value="FINAL / RELEASED" />
              </div>
              <div>
                <small>SOP result</small>
                <Badge value={data.validation_status} />
              </div>
            </div>

            <Link className="text-link" href={`/cases/${data.case_id}`}>
              Open source case →
            </Link>
          </section>
          {data.provider === "fixture" && (
            <div className="fixture-banner">
              Synthetic fixture report — these are test values.
            </div>
          )}
          {!!data.snapshot.missing?.length && (
            <div className="missing-strip">
              <strong>Missing documents:</strong>
              {data.snapshot.missing.join(", ")}
            </div>
          )}
          <ForexPackageSummary packages={data.snapshot.sop_packages} />
          {data.snapshot.sop_summary && (
            <section
              className="panel settings-card report-points"
              aria-labelledby="report-points-title"
            >
              <div className="section-head">
                <h2 className="illustrated-heading" id="report-points-title">
                  <span>
                    <FileCheck2 size={21} aria-hidden />
                  </span>
                  SOP rule points
                </h2>
                <span className="count-pill">
                  {data.snapshot.sop_summary.provisional
                    ? "Provisional score"
                    : data.snapshot.sop_summary.possible
                      ? "Checks resolved"
                      : "No applicable rules"}
                </span>
              </div>
              <div className="report-points-grid">
                <div>
                  <small>Rule points earned</small>
                  <strong>
                    {data.snapshot.sop_summary.earned}
                    <span> / {data.snapshot.sop_summary.possible}</span>
                  </strong>
                </div>
                <div>
                  <small>Compliance</small>
                  <strong>
                    {data.snapshot.sop_summary.percentage === null
                      ? "—"
                      : `${data.snapshot.sop_summary.percentage}%`}
                  </strong>
                </div>
                <div className="report-metric-failed">
                  <small>Not Compliant checks</small>
                  <strong>{data.snapshot.sop_summary.failed}</strong>
                </div>
                <div className="report-metric-pending">
                  <small>Pending checks</small>
                  <strong>{data.snapshot.sop_summary.pending}</strong>
                </div>
              </div>
              {data.snapshot.sop_summary.possible > 0 && (
                <progress
                  aria-label="SOP rule points earned"
                  value={data.snapshot.sop_summary.earned}
                  max={data.snapshot.sop_summary.possible}
                />
              )}
              <p className="subtext">
                Each applicable PASS earns one point. Rule compliance is verified against banking regulations and required criteria.
              </p>
            </section>
          )}
          {!!Object.keys(data.snapshot.scores || {}).length && (
            <section className="panel settings-card">
              <div className="section-head">
                <div>
                  <h2 className="illustrated-heading">
                    <span>
                      <FileCheck2 size={21} />
                    </span>
                    Kertas Kerja Pemeriksaan (KKP) · Indikator Kepatuhan
                  </h2>
                </div>
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                  gap: "14px",
                  marginTop: "16px",
                }}
              >
                {Object.entries(data.snapshot.scores!).map(([key, value]) => {
                  const isRollup = ["total_a", "total_b", "total"].includes(key);
                  const catFindings = (data.snapshot.findings || []).filter((f) => {
                    if (isRollup) {
                      if (key === "total_a")
                        return ["DATA_COMPLETION", "CUSTOMER_SIGNATURE"].includes(
                          f.category || "",
                        );
                      if (key === "total_b")
                        return [
                          "DOCUMENT_COMPLETION",
                          "OFFICER_REVIEW_APPROVAL",
                        ].includes(f.category || "");
                      return true;
                    }
                    return f.category === key;
                  });

                  const eligible = catFindings.filter(
                    (f) =>
                      f.eligible !== false && f.result !== "NOT_APPLICABLE",
                  );
                  const passedCount = eligible.filter(
                    (f) => f.result === "PASS",
                  ).length;
                  const failedCount = eligible.filter(
                    (f) => f.result === "FAIL",
                  ).length;
                  const reviewCount = eligible.filter((f) =>
                    ["REVIEW", "ERROR"].includes(f.result),
                  ).length;
                  const totalCount = eligible.length;
                  const pct =
                    totalCount > 0
                      ? Math.round((passedCount / totalCount) * 100)
                      : null;

                  return (
                    <div
                      key={key}
                      style={{
                        padding: "16px",
                        borderRadius: "10px",
                        border:
                          value === 1
                            ? "1px solid rgba(22, 163, 74, 0.3)"
                            : value === 0
                              ? "1px solid rgba(239, 68, 68, 0.3)"
                              : "1px solid rgba(234, 179, 8, 0.3)",
                        background:
                          value === 1
                            ? "rgba(22, 163, 74, 0.03)"
                            : value === 0
                              ? "rgba(239, 68, 68, 0.03)"
                              : "rgba(234, 179, 8, 0.03)",
                        display: "flex",
                        flexDirection: "column",
                        justifyContent: "space-between",
                        gap: "10px",
                      }}
                    >
                      <div>
                        <div
                          style={{
                            fontSize: "0.8rem",
                            color: "var(--text-muted, #64748b)",
                            fontWeight: 700,
                            textTransform: "uppercase",
                            letterSpacing: "0.025em",
                          }}
                        >
                          {CATEGORY_LABELS[key]?.label ||
                            key.replaceAll("_", " ")}
                        </div>
                        <div
                          style={{
                            fontSize: "0.75rem",
                            color: "var(--text-muted, #94a3b8)",
                            marginTop: "3px",
                          }}
                        >
                          {CATEGORY_LABELS[key]?.desc}
                        </div>
                      </div>

                      <div style={{ marginTop: "6px" }}>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: "8px",
                          }}
                        >
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "4px",
                              padding: "3px 10px",
                              borderRadius: "9999px",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              background:
                                value === 1
                                  ? "rgba(22, 163, 74, 0.15)"
                                  : value === 0
                                    ? "rgba(239, 68, 68, 0.15)"
                                    : "rgba(234, 179, 8, 0.15)",
                              color:
                                value === 1
                                  ? "#16a34a"
                                  : value === 0
                                    ? "#dc2626"
                                    : "#d97706",
                            }}
                          >
                            {value === 1
                              ? "SESUAI"
                              : value === 0
                                ? `TEMUAN (${failedCount} temuan)`
                                : `PERLU REVIEW (${reviewCount} pending)`}
                          </span>
                          {pct !== null && (
                            <span
                              style={{
                                fontSize: "1.15rem",
                                fontWeight: 700,
                                color:
                                  pct >= 90
                                    ? "#16a34a"
                                    : pct >= 70
                                      ? "#d97706"
                                      : "#dc2626",
                              }}
                            >
                              {pct}%
                            </span>
                          )}
                        </div>
                        {totalCount > 0 && (
                          <div
                            style={{
                              fontSize: "0.75rem",
                              color: "var(--text-muted, #64748b)",
                              marginTop: "6px",
                            }}
                          >
                            Kesesuaian: <strong>{passedCount}</strong> dari{" "}
                            {totalCount} kriteria ({failedCount} temuan)
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
          <section className="panel settings-card">
            <div className="section-head">
              <div>
                <h2 className="illustrated-heading">
                  <span>
                    <ListChecks size={21} />
                  </span>
                  SOP findings
                </h2>
                <p>
                  {data.snapshot.findings.length} recorded checks. Unresolved
                  findings remain visible in draft reports.
                </p>
              </div>
            </div>
            <div className="filterbar">
              <div className="pill-tabs">
                <button
                  aria-pressed={filter === "attention"}
                  className={filter === "attention" ? "active" : ""}
                  onClick={() => setFilter("attention")}
                >
                  Needs attention
                </button>
                <button
                  aria-pressed={filter === "all"}
                  className={filter === "all" ? "active" : ""}
                  onClick={() => setFilter("all")}
                >
                  All findings
                </button>
              </div>
              <input
                aria-label="Search report findings"
                placeholder="Find a rule, field or message"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            {findings.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Rule / field</th>
                      <th>Finding message</th>
                      <th>Observed vs expected</th>
                      <th>Result & audit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {findings.map((f, i) => {
                      const rev = (
                        f.evidence as
                          | {
                              review?: {
                                actor?: string;
                                reason?: string;
                                result?: string;
                              };
                            }
                          | undefined
                      )?.review;
                      return (
                        <tr key={`${f.rule_id}-${i}`}>
                          <td>
                            <strong>{f.rule_id}</strong>
                            <div className="subtext">{f.field}</div>
                            {f.evaluation_type && (
                              <span className="mini-tag visual">
                                {f.evaluation_type}
                              </span>
                            )}
                          </td>
                          <td>{f.message}</td>
                          <td>
                            <div className="finding-side-by-side compact">
                              <div>
                                <span className="small-label">OBSERVED</span>
                                <div>{display(f.actual)}</div>
                              </div>
                              <div>
                                <span className="small-label">EXPECTED</span>
                                <div>{display(f.expected)}</div>
                              </div>
                            </div>
                          </td>
                          <td>
                            <Badge value={f.result} />
                            {rev && (
                              <div className="subtext" style={{ marginTop: 6 }}>
                                <strong>Reviewed ({rev.actor}):</strong>{" "}
                                {rev.reason}
                              </div>
                            )}
                            <details>
                              <summary>Evidence details</summary>
                              <dd>{display(f.evidence)}</dd>
                            </details>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="info-note">
                No findings match this view. Select All findings or clear the
                search to see more.
              </p>
            )}
          </section>
          <section className="panel settings-card">
            <h2 className="illustrated-heading">
              <span>
                <Files size={21} />
              </span>
              Source documents & extracted values
            </h2>
            {data.snapshot.documents.map((doc, i) => (
              <details className="report-source-document" key={doc.id || i}>
                <summary>
                  {doc.filename}
                  <Badge value={doc.status} />
                </summary>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Field</th>
                        <th>Extracted value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(doc.normalized || {}).map(
                        ([key, value]) => (
                          <tr key={key}>
                            <td>{key.replaceAll("_", " ")}</td>
                            <td>{display(value)}</td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              </details>
            ))}
          </section>
        </div>
      )}
    </Shell>
  );
}
