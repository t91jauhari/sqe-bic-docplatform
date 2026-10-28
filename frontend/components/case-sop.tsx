"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ScanEye, RotateCcw, CheckCircle2, AlertTriangle, ShieldCheck } from "lucide-react";
import { useData, usePlatform } from "@/components/platform-provider";
import { api } from "@/lib/api";
import { ContextInputs } from "@/components/context-inputs";
import { Badge, ErrorNotice } from "@/components/ui";
import { SopBadge } from "@/components/status";
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
    const rawContext = (data.case_context || {}) as Record<string, any>;
    const contextMap = Object.fromEntries(
      Object.entries(rawContext).filter(
        ([, v]) => typeof v === "string",
      ) as [string, string][],
    );
    if (data.context_suggestions) {
      for (const s of data.context_suggestions) {
        if (!contextMap[s.field] && !s.conflict && s.value && s.value !== "UNKNOWN") {
          contextMap[s.field] = s.value;
        }
      }
    }
    setValues(contextMap);
    if (rawContext.annotation?.reason && !reason) {
      setReason(rawContext.annotation.reason);
    }
    if (rawContext.annotation?.evidence && !evidence) {
      setEvidence(rawContext.annotation.evidence);
    }
  }, [contextKey, data.context_suggestions]);
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
  const allFindings = report?.snapshot.findings || [];
  const totalRules = allFindings.length;
  const passedCount = allFindings.filter((f) => f.result === "PASS").length;
  const failedCount = allFindings.filter((f) => f.result === "FAIL" || f.result === "ERROR").length;
  const reviewCount = allFindings.filter((f) => f.result === "REVIEW").length;

  return (
    <section className="panel settings-card" style={{ marginBottom: 20 }}>
      <div className="section-head" style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <h2 style={{ fontSize: "16px", margin: 0 }}>SOP Compliance Overview</h2>
          <SopBadge value={data.validation_status} />
        </div>
        <button
          className="btn-secondary-action compact-btn"
          disabled={
            !data.can_write ||
            pending ||
            data.completed_count !== data.documents_count
          }
          onClick={() => void run(`/cases/${data.id}/sop-rerun`, {})}
          title="Rerun all SOP compliance rules against verified document extractions"
        >
          <RotateCcw size={14} />
          <span>Rerun SOP Checks</span>
        </button>
      </div>

      <p style={{ margin: "0 0 16px", fontSize: "13px", color: "var(--color-muted, #64748b)" }}>
        {current
          ? `All transaction rules evaluated against banking regulations and verified case documents · Last run: ${new Intl.DateTimeFormat("en-GB", {
              day: "2-digit",
              month: "short",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
              timeZone: "Asia/Jakarta",
            }).format(new Date(current.created_at * 1000))}`
          : "Waiting for document extraction to finish before running SOP compliance."}
      </p>

      {/* Clear Executive KPI Strip - No Confusing Point Game! */}
      {allFindings.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
            gap: "12px",
            marginBottom: "18px",
          }}
        >
          <div
            style={{
              padding: "12px 14px",
              background: "#f8fafc",
              borderRadius: "8px",
              border: "1px solid #e2e8f0",
            }}
          >
            <span style={{ fontSize: "11px", fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>
              Overall Compliance
            </span>
            <div
              style={{
                fontSize: "16px",
                fontWeight: 700,
                marginTop: 4,
                color:
                  data.validation_status === "PASS"
                    ? "#16a34a"
                    : data.validation_status === "FAIL"
                      ? "#dc2626"
                      : "#d97706",
              }}
            >
              {data.validation_status === "PASS"
                ? "Fully Compliant"
                : data.validation_status === "FAIL"
                  ? "Non-Compliant"
                  : "Needs Review"}
            </div>
          </div>

          <div
            style={{
              padding: "12px 14px",
              background: "#f8fafc",
              borderRadius: "8px",
              border: "1px solid #e2e8f0",
            }}
          >
            <span style={{ fontSize: "11px", fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>
              Rules Evaluated
            </span>
            <div style={{ fontSize: "16px", fontWeight: 700, marginTop: 4, color: "#1e293b" }}>
              {totalRules} Checkpoints
            </div>
          </div>

          <div
            style={{
              padding: "12px 14px",
              background: "#f0fdf4",
              borderRadius: "8px",
              border: "1px solid #bbf7d0",
            }}
          >
            <span style={{ fontSize: "11px", fontWeight: 700, color: "#166534", textTransform: "uppercase" }}>
              Compliant (Pass)
            </span>
            <div style={{ fontSize: "16px", fontWeight: 700, marginTop: 4, color: "#15803d" }}>
              {passedCount} Passed
            </div>
          </div>

          <div
            style={{
              padding: "12px 14px",
              background: failedCount > 0 ? "#fef2f2" : "#f8fafc",
              borderRadius: "8px",
              border: `1px solid ${failedCount > 0 ? "#fecaca" : "#e2e8f0"}`,
            }}
          >
            <span
              style={{
                fontSize: "11px",
                fontWeight: 700,
                color: failedCount > 0 ? "#991b1b" : "#64748b",
                textTransform: "uppercase",
              }}
            >
              Discrepancies
            </span>
            <div
              style={{
                fontSize: "16px",
                fontWeight: 700,
                marginTop: 4,
                color: failedCount > 0 ? "#dc2626" : "#475569",
              }}
            >
              {failedCount} Findings
            </div>
          </div>
        </div>
      )}

      {current?.error && <ErrorNotice message={current.error} />}
      <details>
        <summary style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}>
          <span>Case context and transaction metadata</span>
          {Boolean((data.case_context as any)?.annotation?.actor === "system.auto_inference") && (
            <span style={{ fontSize: "0.75rem", background: "#dcfce7", color: "#15803d", padding: "0.15rem 0.5rem", borderRadius: "12px", fontWeight: "normal" }}>
              ✓ Auto-filled by System
            </span>
          )}
        </summary>
        {(data.case_context as any)?.annotation?.actor === "system.auto_inference" && (
          <div
            style={{
              padding: "0.65rem 0.9rem",
              background: "var(--bg-accent, #f0fdf4)",
              border: "1px solid #bbf7d0",
              borderRadius: "6px",
              marginTop: "0.75rem",
              marginBottom: "0.75rem",
              fontSize: "0.85rem",
              color: "#166534",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "0.5rem",
            }}
          >
            <span>
              <strong>✓ Auto-resolved by Platform Engine:</strong> Metadata fields are pre-populated from verified case documents (Straight-Through Processing).
            </span>
            <button
              type="button"
              className="secondary"
              style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}
              onClick={() => {
                const autoValues: Record<string, string> = {};
                for (const s of data.context_suggestions || []) {
                  if (!s.conflict && s.value && s.value !== "UNKNOWN") {
                    autoValues[s.field] = s.value;
                  }
                }
                setValues({ ...values, ...autoValues });
                setReason("Re-aligned with automated case document inference");
                setEvidence("Verified from Application slip, EKTP, and Valas Declaration");
              }}
            >
              Reset to Auto Values
            </button>
          </div>
        )}
        {Boolean(data.context_suggestions && data.context_suggestions.length > 0) && (
          <div style={{ margin: "0.5rem 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
              {data.context_suggestions?.filter(s => !s.conflict).length} automated evidence suggestions
            </span>
            {data.can_write && (
              <button
                type="button"
                className="secondary"
                style={{ padding: "0.2rem 0.5rem", fontSize: "0.75rem" }}
                onClick={() => {
                  const draftValues = { ...values };
                  const evParts: string[] = [];
                  for (const s of data.context_suggestions || []) {
                    if (!s.conflict && s.value && s.value !== "UNKNOWN") {
                      draftValues[s.field] = s.value;
                      evParts.push(`${s.field}: ${s.value}`);
                    }
                  }
                  setValues(draftValues);
                  setReason("Accepted all automated document context suggestions");
                  setEvidence(evParts.slice(0, 3).join("; "));
                }}
              >
                Apply All Suggestions
              </button>
            )}
          </div>
        )}
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
    </section>
  );
}
