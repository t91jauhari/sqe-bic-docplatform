"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ScanEye } from "lucide-react";
import { useData, usePlatform } from "@/components/platform-provider";
import { api } from "@/lib/api";
import { ContextInputs } from "@/components/context-inputs";
import { ForexPackageSummary } from "@/components/forex-package-summary";
import { Badge, ErrorNotice } from "@/components/ui";
import type { AutomationCatalog, CaseDetail } from "@/lib/types";
export function CaseSOP({
  data,
  refresh,
}: {
  data: CaseDetail;
  refresh: () => Promise<void>;
}) {
  const { data: catalog } = useData<AutomationCatalog>(`/config/catalog?case_id=${encodeURIComponent(data.id)}`, 0);
  const { notify } = usePlatform();
  const [values, setValues] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState("");
  const [pending, setPending] = useState(false);
  const contextKey = JSON.stringify(data.case_context || {});
  useEffect(() => {
    setValues(
      Object.fromEntries(
        Object.entries(data.case_context || {}).filter(
          ([, v]) => typeof v === "string",
        ) as [string, string][],
      ),
    );
  }, [contextKey]);
  const run = async (path: string, body: unknown, method = "POST") => {
    setPending(true);
    try {
      await api(path, { method, body: JSON.stringify(body) });
      notify("SOP processing queued. Uses stored extraction.");
      await refresh();
    } catch (err) {
      notify(
        err instanceof Error ? err.message : "SOP operation failed",
        "error",
      );
    } finally {
      setPending(false);
    }
  };
  const current = data.sop_runs?.[0];
  const report = data.reports[0];
  const forex =
    Boolean(report?.snapshot.sop_packages?.forex) ||
    data.documents.some((d) =>
      [
        "application",
        "lld",
        "invoice",
        "valas_declaration_1",
        "valas_declaration_2",
      ].includes(d.doc_type),
    );
  const findings =
    report?.snapshot.findings.filter(
      (f) => f.result === "REVIEW" && f.evaluation_type === "VISUAL",
    ) || [];
  return (
    <section className="panel settings-card" style={{ marginBottom: 20 }}>
      <div className="section-head">
        <h2>Case SOP workflow</h2>
        {current && <Badge value={current.status} />}
        <button
          className="secondary"
          disabled={
            !data.can_write ||
            pending ||
            data.completed_count !== data.documents_count
          }
          onClick={() => void run(`/cases/${data.id}/sop-rerun`, {})}
        >
          Rerun SOP checks
        </button>
      </div>
      <p>
        {current
          ? `Complete · ${new Intl.DateTimeFormat("en-GB", {
              day: "2-digit",
              month: "short",
              hour: "2-digit",
              minute: "2-digit",
              timeZone: "Asia/Jakarta",
            }).format(new Date(current.created_at * 1000))}`
          : "Waiting for document extraction to finish."}
      </p>
      {current && (
        <p className="subtext" title={current.snapshot_hash}>
          Workflow stage: {current.stage.replaceAll("_", " ").toLowerCase()}
        </p>
      )}
      {current?.error && <ErrorNotice message={current.error} />}
      <p className="subtext">
        SOP runs and report versions keep frozen document values and rules.
        Document quality checks remain available separately.
      </p>
      {report?.snapshot.sop_summary && (
        <div className="button-row">
          <span className="count-pill">
            {report.snapshot.sop_summary.earned}/
            {report.snapshot.sop_summary.possible} points
            {" · "}
            {report.snapshot.sop_summary.percentage ?? "—"}%{" · "}
            {report.snapshot.sop_summary.failed} failed
            {" · "}
            {report.snapshot.sop_summary.pending} awaiting visual review
            {report.snapshot.sop_summary.provisional ? " · Provisional" : ""}
          </span>
        </div>
      )}
      <ForexPackageSummary packages={report?.snapshot.sop_packages} />
      <details>
        <summary>Case context and transaction metadata</summary>
        {data.context_suggestions?.map((s, i) => (
          <div key={i} style={{ padding: 8 }}>
            <strong>
              {s.field}: {s.value}
            </strong>{" "}
            — {s.source}
            {s.conflict ? " · Conflicting evidence; review required" : ""}
            {!s.conflict && data.can_write && (
              <button
                className="text-link"
                onClick={() => {
                  setValues({ ...values, [s.field]: s.value });
                  setEvidence(`Document ${s.document_id}: ${s.source}`);
                }}
              >
                Use suggestion in draft
              </button>
            )}
          </div>
        ))}
        <p>
          Enter values from supplied documents. Unknown values fail data checks;
          carrier and transaction staff are never inferred from platform users.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(
              `/cases/${data.id}/context`,
              { values, reason, evidence },
              "PUT",
            );
          }}
        >
          <fieldset disabled={!data.can_write || pending}>
            <div className="form-grid">
              <ContextInputs definitions={catalog?.context_definitions || {}} values={values}
                onChange={setValues} documents={data.documents} />
            </div>
            {forex && (
              <p className="subtext">
                Select documents when several copies could apply. Partial
                payment requires an explicit amount, three-letter currency and
                supporting document/page evidence below. No extraction is
                repeated.
              </p>
            )}
            <label>
              Reason for annotation
              <input
                required
                minLength={5}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            <label>
              Document / page evidence
              <input
                required
                minLength={5}
                value={evidence}
                onChange={(e) => setEvidence(e.target.value)}
              />
            </label>
            <button className="primary">Save context and rerun</button>
          </fieldset>
        </form>
      </details>
      <div className="review-entry">
        <span className="review-entry-icon">
          <ScanEye size={24} aria-hidden />
        </span>
        <div>
          <h3>Visual review workspace</h3>
          <p>
            {findings.length} visual checks awaiting a decision. Inspect
            documents, record evidence, and resolve each check on a dedicated
            page.
          </p>
        </div>
        <Link className="primary" href={`/cases/${data.id}/review`}>
          Open review workspace <ArrowRight size={16} />
        </Link>
      </div>
    </section>
  );
}
