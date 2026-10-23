"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import {
  Search,
  Upload,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  X,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { useData } from "@/components/platform-provider";
import { Busy, CaseTable, Empty, ErrorNotice } from "@/components/ui";
import type { CaseSummary, ConfigResponse } from "@/lib/types";
export default function Cases() {
  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get("status");
    if (
      initial &&
      [
        "QUEUED",
        "PROCESSING",
        "WAITING_DOCUMENTS",
        "NEEDS_REVIEW",
        "ERROR",
        "READY",
        "FINALIZED",
      ].includes(initial)
    )
      setStatus(initial);
  }, []);
  const [search, setSearch] = useState(""),
    [q, setQ] = useState(""),
    [status, setStatus] = useState(""),
    [sopFilter, setSopFilter] = useState(""),
    [flow, setFlow] = useState(""),
    [pageSize, setPageSize] = useState(25),
    [page, setPage] = useState(0);
  const { data: config } = useData<ConfigResponse>("/config", 0);
  const { data, error, loading, lastUpdated, refresh } = useData<{
    items: CaseSummary[];
    total: number;
  }>(
    "/cases?q=" +
      encodeURIComponent(q) +
      "&status=" +
      status +
      "&transaction_flow=" +
      encodeURIComponent(flow) +
      "&offset=" +
      page * pageSize +
      "&limit=" +
      pageSize,
  );
  const visibleCases = (data?.items || []).filter((c) => {
    if (!sopFilter) return true;
    const v = (c.validation_status || "").toUpperCase();
    if (sopFilter === "REVIEW")
      return ["REVIEW", "NEEDS_REVIEW", "FAIL"].includes(v);
    if (sopFilter === "NONE") return ["", "PENDING", "NONE"].includes(v);
    return v === sopFilter;
  });
  const filtered = !!(q || status || flow || sopFilter);
  const reset = () => {
    setSearch("");
    setQ("");
    setStatus("");
    setFlow("");
    setSopFilter("");
    setPage(0);
  };
  return (
    <Shell
      title="Customer cases"
      subtitle="Every document set, organized by customer and scoped to your branches."
    >
      <section className="panel">
        <div className="case-list-heading">
          <div>
            <h2>Case workspace</h2>
            <p>
              {data
                ? `${data.total} cases in this view`
                : "Loading your cases…"}{" "}
              · Select a customer to review documents.
            </p>
          </div>
          <button
            className="secondary"
            onClick={() => void refresh()}
            disabled={loading}
          >
            <RefreshCw size={15} />
            Refresh
          </button>
        </div>
        <div className="case-quick-views" aria-label="Case views">
          {[
            ["", "All cases"],
            ["NEEDS_REVIEW", "Needs review"],
            ["PROCESSING", "Processing"],
            ["READY", "Ready"],
          ].map(([value, label]) => (
            <button
              key={value}
              className={status === value ? "active" : ""}
              aria-pressed={status === value}
              onClick={() => {
                setStatus(value);
                setPage(0);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="filterbar case-filterbar">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setQ(search);
              setPage(0);
            }}
            className="search"
          >
            <Search size={17} />
            <input
              aria-label="Search customer"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search customer name…"
            />
            <button type="submit">Search</button>
          </form>
          <select
            aria-label="Filter transaction flow"
            value={flow}
            onChange={(e) => {
              setFlow(e.target.value);
              setPage(0);
            }}
          >
            <option value="">All transaction flows</option>
            {Object.entries(config?.payload.templates || {}).map(([id, f]) => (
              <option key={id} value={id}>
                {f.label}
                {f.enabled === false ? " (archived)" : ""}
              </option>
            ))}
          </select>
          <select
            aria-label="Filter status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(0);
            }}
          >
            <option value="">All statuses</option>
            {[
              ["QUEUED", "Queued"],
              ["PROCESSING", "Processing"],
              ["WAITING_DOCUMENTS", "Waiting Documents"],
              ["NEEDS_REVIEW", "Needs Review"],
              ["PROCESSING_ERROR", "Processing Error"],
              ["READY", "Ready"],
              ["FINALIZED", "Finalized"],
            ].map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <select
            aria-label="Filter SOP result"
            value={sopFilter}
            onChange={(e) => {
              setSopFilter(e.target.value);
              setPage(0);
            }}
          >
            <option value="">SOP: this page · All</option>
            <option value="REVIEW">Needs Review</option>
            <option value="FAIL">Fail</option>
            <option value="PASS">Pass</option>
            <option value="NONE">Not run</option>
          </select>
          <Link className="primary" href="/upload">
            <Upload size={16} />
            Upload documents
          </Link>
        </div>
        {filtered && (
          <div className="active-filter-bar">
            <span>
              Filtered view
              {sopFilter ? " · SOP filtering applies to the current page" : ""}
            </span>
            {q && <span className="filter-chip">Search: {q}</span>}
            <button className="text-button" onClick={reset}>
              <X size={14} />
              Clear all filters
            </button>
          </div>
        )}
        {error && <ErrorNotice message={error} retry={() => void refresh()} />}
        {loading && !data ? (
          <Busy />
        ) : visibleCases.length ? (
          <CaseTable cases={visibleCases} />
        ) : (
          <Empty
            title={filtered ? "No cases match this view" : "No cases here yet"}
            detail={
              sopFilter && data?.items.length
                ? "No matching SOP results on this page. Try the next page or clear filters."
                : "Try another filter, or upload your first customer documents."
            }
            action={
              filtered ? (
                <button className="secondary" onClick={reset}>
                  Clear filters
                </button>
              ) : (
                <Link className="secondary" href="/upload">
                  <Upload size={16} />
                  Upload documents
                </Link>
              )
            }
          />
        )}
        {data && (
          <div className="pagination">
            <span>
              {data.total ? page * pageSize + 1 : 0}–
              {Math.min((page + 1) * pageSize, data.total)} of {data.total}{" "}
              cases{sopFilter ? ` · ${visibleCases.length} shown` : ""}
            </span>
            <div>
              <select
                aria-label="Cases per page"
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(0);
                }}
              >
                {[10, 25, 50].map((n) => (
                  <option value={n} key={n}>
                    {n} per page
                  </option>
                ))}
              </select>
              <button
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
                aria-label="Previous page"
              >
                <ChevronLeft size={16} />
              </button>
              <span>Page {page + 1}</span>
              <button
                disabled={(page + 1) * pageSize >= data.total}
                onClick={() => setPage(page + 1)}
                aria-label="Next page"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
        {lastUpdated && (
          <p className="data-freshness">
            Last refreshed{" "}
            {new Date(lastUpdated).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}{" "}
            · Updates automatically while this page is visible.
          </p>
        )}
      </section>
    </Shell>
  );
}
