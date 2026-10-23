"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Download,
  FileCheck2,
  Files,
  ListChecks,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { useData } from "@/components/platform-provider";
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
export default function ReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params),
    router = useRouter();
  const { data, error, loading, refresh } = useData<Report>(`/reports/${id}`);
  const [filter, setFilter] = useState("attention"),
    [query, setQuery] = useState("");
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
                <Link
                  className="secondary"
                  href={`/cases/${data.case_id}/review`}
                >
                  Open visual review
                </Link>
                {["pdf", "xlsx", "json"].map((fmt) => (
                  <a
                    key={fmt}
                    className="secondary"
                    href={`/api/reports/${data.id}/download?format=${fmt}`}
                  >
                    <Download size={15} />
                    {fmt.toUpperCase()}
                  </a>
                ))}
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
                <small>Release</small>
                <Badge value={data.state} />
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
                  <small>Failed checks</small>
                  <strong>{data.snapshot.sop_summary.failed}</strong>
                </div>
                <div className="report-metric-pending">
                  <small>Awaiting visual review</small>
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
                Each applicable PASS earns one point. Pending visual reviews
                remain in possible points. Release readiness is assessed
                separately.
              </p>
            </section>
          )}
          {!!Object.keys(data.snapshot.scores || {}).length && (
            <section className="panel settings-card">
              <h2>Legacy category compliance indicators</h2>
              <div className="report-summary-grid">
                {Object.entries(data.snapshot.scores!).map(([key, value]) => (
                  <div key={key}>
                    <small>{key.replaceAll("_", " ")}</small>
                    <strong>{value === null ? "Needs review" : value}</strong>
                  </div>
                ))}
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
                      <th>Result</th>
                      <th>Finding & evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {findings.map((f, i) => (
                      <tr key={`${f.rule_id}-${i}`}>
                        <td>
                          <strong>{f.rule_id}</strong>
                          <div className="subtext">{f.field}</div>
                        </td>
                        <td>
                          <Badge value={f.result} />
                        </td>
                        <td>
                          {f.message}
                          <details>
                            <summary>Values & evidence</summary>
                            <dl>
                              <dt>Actual</dt>
                              <dd>{display(f.actual)}</dd>
                              <dt>Expected</dt>
                              <dd>{display(f.expected)}</dd>
                              <dt>Evidence</dt>
                              <dd>{display(f.evidence)}</dd>
                            </dl>
                          </details>
                        </td>
                      </tr>
                    ))}
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
