"use client";
import Link from "next/link";
import { useState } from "react";
import {
  Download,
  ArrowUpRight,
  Building2,
  History,
  Database,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { useData } from "@/components/platform-provider";
import { Badge, Busy, Empty, ErrorNotice, formatDate } from "@/components/ui";
import type { ReportListItem, ConfigResponse, Branch } from "@/lib/types";
export default function Reports() {
  const [branch, setBranch] = useState("");
  const [flow, setFlow] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [reportQuery, setReportQuery] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [sopStatusFilter, setSopStatusFilter] = useState("");
  const invalidRange = Boolean(dateFrom && dateTo && dateFrom > dateTo);
  const exportParams = new URLSearchParams({ branch_id: branch });
  if (flow) exportParams.set("transaction_flow", flow);
  if (dateFrom) exportParams.set("date_from", dateFrom);
  if (dateTo) exportParams.set("date_to", dateTo);
  const { data: branches } = useData<Branch[]>("/branches", 0);
  const { data, error, loading, refresh } =
      useData<ReportListItem[]>("/reports"),
    { data: cfg } = useData<ConfigResponse>("/config", 0);
  return (
    <Shell
      title="Kertas kerja"
      subtitle="Latest customer reports, ready to review in the application or download."
    >
      <section className="panel settings-card" style={{ marginBottom: 20 }}>
        <h2 className="illustrated-heading">
          <span>
            <Building2 size={21} aria-hidden />
          </span>
          Branch Kertas Kerja
        </h2>
        <p>
          One current customer row per branch and transaction flow. The Excel
          report uses grouped category headings and readable findings. Pending
          assessments are labelled explicitly; detailed rule scores remain on
          separate sheets.
        </p>
        <div className="button-row">
          <label>
            Branch
            <select
              aria-label="Branch"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
            >
              <option value="">Choose branch</option>
              {branches?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.code} · {b.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Transaction flow
            <select value={flow} onChange={(e) => setFlow(e.target.value)}>
              <option value="">All transaction flows</option>
              {Object.entries(cfg?.payload.templates || {}).map(
                ([key, value]) => (
                  <option key={key} value={key}>
                    {value.label}
                  </option>
                ),
              )}
            </select>
          </label>
          <label>
            Transaction date from
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </label>
          <label>
            Transaction date to
            <input
              type="date"
              value={dateTo}
              min={dateFrom || undefined}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </label>
          <a
            aria-disabled={!branch || invalidRange}
            tabIndex={branch && !invalidRange ? 0 : -1}
            onClick={(e) => {
              if (!branch || invalidRange) e.preventDefault();
            }}
            className={`primary branch-export-button ${!branch || invalidRange ? "unavailable" : ""}`}
            href={
              branch && !invalidRange
                ? "/api/reports/kertas-kerja?" + exportParams.toString()
                : undefined
            }
          >
            <Download size={16} aria-hidden />
            Download branch XLSX
          </a>
        </div>
        {invalidRange && (
          <p role="alert">The end date must be on or after the start date.</p>
        )}
        <p className="subtext">
          These filters apply to the branch export. Date filters use the
          recorded transaction date; reports without a readable transaction date
          are excluded when a date filter is set. Leave both dates empty to
          include all dates.
        </p>
      </section>
      <section className="panel">
        <div className="section-head">
          <div>
            <h2 className="illustrated-heading">
              <span>
                <History size={21} aria-hidden />
              </span>
              Latest customer reports
            </h2>
            <p>
              One latest report per customer, branch and transaction flow.
              Drafts may still contain unresolved findings.
            </p>
          </div>
        </div>
        {data && data.length > 0 && (
          <div className="filterbar" style={{ borderTop: "1px solid var(--line)" }}>
            <input
              aria-label="Search customer reports"
              placeholder="Search customer name or case reference..."
              value={reportQuery}
              onChange={(e) => setReportQuery(e.target.value)}
              style={{ maxWidth: 320 }}
            />
            <select
              aria-label="Filter report release state"
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
              style={{ maxWidth: 180 }}
            >
              <option value="">All release states</option>
              <option value="FINAL">Final / Released</option>
              <option value="DRAFT">Draft</option>
            </select>
            <select
              aria-label="Filter report SOP status"
              value={sopStatusFilter}
              onChange={(e) => setSopStatusFilter(e.target.value)}
              style={{ maxWidth: 200 }}
            >
              <option value="">All SOP statuses</option>
              <option value="PASS">Pass</option>
              <option value="NEEDS_REVIEW">Needs Review</option>
              <option value="FAIL">Fail</option>
            </select>
          </div>
        )}
        {error && <ErrorNotice message={error} retry={() => void refresh()} />}
        {loading && !data ? (
          <Busy />
        ) : data?.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Version</th>
                  <th>Release</th>
                  <th>SOP</th>
                  <th>Generated</th>
                  <th>Download</th>
                </tr>
              </thead>
              <tbody>
                {data
                  .filter((r) => {
                    if (
                      reportQuery &&
                      !`${r.customer} ${r.reference} ${r.transaction_flow}`
                        .toLowerCase()
                        .includes(reportQuery.toLowerCase())
                    )
                      return false;
                    if (stateFilter && r.state !== stateFilter) return false;
                    if (sopStatusFilter && r.validation_status !== sopStatusFilter)
                      return false;
                    return true;
                  })
                  .map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link className="customer-link" href={"/reports/" + r.id}>
                        {r.customer}
                        <ArrowUpRight size={13} />
                      </Link>
                      <div className="subtext">
                        {r.reference} ·{" "}
                        {cfg?.payload.templates[r.transaction_flow]?.label ||
                          r.transaction_flow}
                      </div>
                      {r.provider === "fixture" && (
                        <div className="fixture-tag">Synthetic fixture</div>
                      )}
                    </td>
                    <td>v{r.version}</td>
                    <td>
                      <Badge value={r.state} />
                    </td>
                    <td>
                      <Badge value={r.validation_status} />
                    </td>
                    <td className="muted">{formatDate(r.created_at)}</td>
                    <td>
                      <div className="button-row">
                        <Link className="text-link" href={`/reports/${r.id}`}>
                          View report <ArrowUpRight size={13} />
                        </Link>
                        {["xlsx", "pdf", "json"].map((fmt) => (
                          <a
                            className="text-link"
                            key={fmt}
                            href={
                              "/api/reports/" + r.id + "/download?format=" + fmt
                            }
                          >
                            {fmt.toUpperCase()}
                            <Download size={13} />
                          </a>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="Reports will appear here"
            detail="The worker prepares a draft after a case's active documents finish, including cases that need review."
          />
        )}
      </section>
      <section className="panel export-panel">
        <div>
          <h2 className="illustrated-heading">
            <span>
              <Database size={21} aria-hidden />
            </span>
            Extraction datasets
          </h2>
          <p>
            Separate CSV outputs for each document type. Values retain document
            and case references.
          </p>
        </div>
        <div className="export-grid">
          {cfg &&
            Object.entries(cfg.payload.profiles).map(([name, p]) => (
              <a className="secondary" key={name} href={"/api/exports/" + name}>
                {p.label}
                <Download size={15} />
              </a>
            ))}
        </div>
      </section>
    </Shell>
  );
}
