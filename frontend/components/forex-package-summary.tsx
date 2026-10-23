import type { SOPPackages } from "@/lib/types";
import { Badge } from "@/components/ui";

export function ForexPackageSummary({ packages }: { packages?: SOPPackages }) {
  const forex = packages?.forex;
  if (!forex) return null;
  const score = forex.summary;
  return (
    <section
      className="panel settings-card"
      aria-label="Forex checkpoint package"
    >
      <div className="section-head">
        <h2>Forex · 15 SOP checkpoints</h2>
        <span className="count-pill">
          {score.earned}/{score.possible} points · {score.percentage ?? "—"}%
        </span>
      </div>
      <p>
        Each checkpoint earns one point when all its applicable field checks
        pass. {score.failed} failed · {score.pending} awaiting visual review
        {score.provisional ? " · Provisional" : ""}.
      </p>
      {!forex.coverage.complete && (
        <p className="error-text">
          Incomplete package: {forex.coverage.present}/15 checkpoints
          configured; {forex.coverage.missing_field_checks} required field
          checks missing. Missing checks fail package compliance.
        </p>
      )}
      <details>
        <summary>View checkpoint results</summary>
        <div className="form-grid">
          {forex.checkpoints.map((c) => (
            <div key={c.rule_id}>
              <strong>Checkpoint {c.rule_id.split(":")[1]}</strong>{" "}
              <Badge value={c.result} />
              <p>{c.label}</p>
              <p className="subtext">
                {c.child_rules.join(" · ") || "No configured check"}
              </p>
            </div>
          ))}
        </div>
      </details>
      <p className="subtext">
        The full rule score also includes other configured checks and counts the
        individual field checks separately.
      </p>
    </section>
  );
}
