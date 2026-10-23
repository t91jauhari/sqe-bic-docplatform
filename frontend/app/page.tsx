"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Upload,
  ArrowUpRight,
  Layers,
  ScanLine,
  Clock3,
  CheckCircle2,
  ArrowRight,
  AlertTriangle,
  X,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { useData, usePlatform } from "@/components/platform-provider";
import { Busy, Empty, ErrorNotice, CaseTable } from "@/components/ui";
import type { Dashboard } from "@/lib/types";
type FailureGroup = {
  error_prefix: string;
  count: number;
  case_ids: string[];
  first_seen: number;
};
const DISMISSED_KEY = "failure-banner-dismissed";
export default function Overview() {
  const { data, error, loading, refresh } = useData<Dashboard>("/dashboard"),
    { user } = usePlatform();
  const since = Math.floor(Date.now() / 1000) - 24 * 60 * 60;
  const { data: failures } = useData<FailureGroup[]>(
    "/documents/failure-summary?since=" + since,
  );
  const [dismissed, setDismissed] = useState<string | null>(null);
  useEffect(() => {
    try {
      setDismissed(localStorage.getItem(DISMISSED_KEY));
    } catch {
      /* storage unavailable — banner simply reappears */
    }
  }, []);
  const cluster = failures?.find(
    (f) => f.count >= 3 && f.error_prefix !== dismissed,
  );
  const dismissCluster = () => {
    if (!cluster) return;
    setDismissed(cluster.error_prefix);
    try {
      localStorage.setItem(DISMISSED_KEY, cluster.error_prefix);
    } catch {
      /* ignore */
    }
  };
  const cards = data
    ? [
        {
          label: "Customer cases",
          value: data.cases,
          icon: Layers,
          caption: "Organized by customer label",
          href: "/cases",
        },
        {
          label: "In progress",
          value: data.processing,
          icon: ScanLine,
          caption: "Workers processing in parallel",
          href: "/cases?status=PROCESSING",
        },
        {
          label: "Needs attention",
          value: data.attention,
          icon: Clock3,
          caption: "Consolidated case exceptions",
          href: "/inbox",
        },
        {
          label: "Ready / released",
          value: data.ready,
          icon: CheckCircle2,
          caption: "SOP evaluation complete",
          href: "/reports",
        },
      ]
    : [];
  return (
    <Shell
      title="Operations overview"
      subtitle="A clear view of every customer case, from upload to kertas kerja."
      action={
        user?.role !== "auditor" && (
          <Link className="primary" href="/upload">
            <Upload size={17} />
            New upload
          </Link>
        )
      }
    >
      {error && <ErrorNotice message={error} retry={() => void refresh()} />}
      {cluster && (
        <div className="failure-banner" role="status">
          <AlertTriangle size={18} />
          <span>
            <strong>
              {cluster.count} documents failed with the same error
            </strong>{" "}
            since{" "}
            {new Intl.DateTimeFormat("en-GB", {
              hour: "2-digit",
              minute: "2-digit",
            }).format(new Date(cluster.first_seen * 1000))}{" "}
            — likely a temporary outage.{" "}
            <Link href="/cases">Review affected cases</Link>
          </span>
          <button
            className="icon-button"
            aria-label="Dismiss failure cluster banner"
            onClick={dismissCluster}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {loading && !data ? (
        <Busy />
      ) : (
        data && (
          <>
            <div className="stats-grid">
              {cards.map((c) => (
                <Link
                  className="stat-card stat-link"
                  key={c.label}
                  href={c.href}
                  aria-label={`${c.label}: ${c.value}. ${c.caption}`}
                >
                  <div className="stat-top">
                    <span>{c.label}</span>
                    <c.icon size={19} />
                  </div>
                  <strong>{c.value.toLocaleString()}</strong>
                  <p>
                    {c.caption}
                    <ArrowUpRight size={14} aria-hidden />
                  </p>
                </Link>
              ))}
            </div>
            <div className="overview-grid">
              <section className="panel cases-panel">
                <div className="section-head">
                  <div>
                    <h2>Recent customer cases</h2>
                    <p>Progress and findings, in one place.</p>
                  </div>
                  <Link href="/cases" className="text-link">
                    View all
                    <ArrowUpRight size={16} />
                  </Link>
                </div>
                {data.recent.length ? (
                  <CaseTable cases={data.recent} />
                ) : (
                  <Empty
                    title="Your workspace is ready"
                    detail="Upload a batch of customer documents to create your first cases."
                    action={
                      <Link className="primary" href="/upload">
                        <Upload size={16} />
                        Upload documents
                      </Link>
                    }
                  />
                )}
              </section>
              <aside className="overview-aside">
                <section className="dark-panel">
                  <span className="eyebrow">YOUR NEXT ACTION</span>
                  <h2>
                    {data.attention
                      ? "Keep cases moving."
                      : "Start with a batch."}
                  </h2>
                  <p>
                    {data.attention
                      ? "The inbox collects missing documents, classification conflicts and review findings into clear case actions."
                      : "Files are grouped by customer name first. Classification then confirms the right extraction schema."}
                  </p>
                  <Link href={data.attention ? "/inbox" : "/upload"}>
                    {data.attention ? "Open inbox" : "Upload documents"}
                    <ArrowRight size={17} />
                  </Link>
                </section>
                <section className="panel run-panel">
                  <h3>Processing configuration</h3>
                  <dl>
                    <div>
                      <dt>Provider</dt>
                      <dd>
                        {data.provider === "fixture"
                          ? "Synthetic fixtures"
                          : data.provider === "spider-ai" ? "Spider-AI" : "Historical provider"}
                      </dd>
                    </div>
                    <div>
                      <dt>Workflow</dt>
                      <dd>
                        {data.workflow_driver === "local"
                          ? "Local development"
                          : "Temporal"}
                      </dd>
                    </div>
                    <div>
                      <dt>Configuration</dt>
                      <dd>Version {data.config_version}</dd>
                    </div>
                    <div>
                      <dt>Documents complete</dt>
                      <dd>
                        {data.completed_documents} / {data.documents}
                      </dd>
                    </div>
                  </dl>
                  {data.provider === "fixture" && (
                    <p className="fixture-note">
                      Fixture mode uses synthetic values. It does not extract
                      uploaded content.
                    </p>
                  )}
                </section>
              </aside>
            </div>
          </>
        )
      )}
    </Shell>
  );
}
