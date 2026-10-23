"use client";
import {
  inFamily,
  ruleInFamily,
  type DocumentFamily,
} from "@/lib/document-family";
import { AccountCondition } from "./account-condition";
import { useState } from "react";
import { useData, usePlatform } from "@/components/platform-provider";
import { api } from "@/lib/api";
import { Busy, ErrorNotice, Badge, Modal } from "@/components/ui";
import type {
  Configuration,
  AutomationCatalog,
  SOPRule,
  FieldCatalog,
} from "@/lib/types";

type Props = {
  draft: Configuration;
  update: (v: Configuration) => void;
  editable: boolean;
};
export function AutomationEditor({ draft, update, editable }: Props) {
  const { notify } = usePlatform();
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [preview, setPreview] = useState("");
  const changes = (next: Configuration) =>
    Object.keys(next).filter(
      (k) =>
        JSON.stringify(next[k as keyof Configuration]) !==
        JSON.stringify(draft[k as keyof Configuration]),
    );
  return (
    <div className="settings-grid">
      <section className="panel settings-card">
        <h2>Workbook configuration</h2>
        <p>
          Export the current version, fill the template and import a draft.
          Validate and replay before publishing. Running cases keep their pinned
          version.
        </p>
        <a className="secondary" href="/api/config/export">
          Download editable XLSX template
        </a>
        <label>
          Import workbook
          <input
            disabled={!editable || busy}
            type="file"
            accept=".xlsx"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setBusy(true);
              setErrors([]);
              try {
                const form = new FormData();
                form.append("file", file);
                const r = await api<{
                  valid: boolean;
                  errors: { sheet: string; cell: string; message: string }[];
                  payload: Configuration;
                }>("/config/import", { method: "POST", body: form });
                if (r.valid) {
                  setPreview(
                    "Imported changes: " +
                      (changes(r.payload).join(", ") || "none"),
                  );
                  update(r.payload);
                  notify("Workbook loaded as draft. Replay before publishing.");
                } else
                  setErrors(
                    r.errors.map((x) => `${x.sheet} ${x.cell}: ${x.message}`),
                  );
              } catch (err) {
                notify(
                  err instanceof Error ? err.message : "Import failed",
                  "error",
                );
              } finally {
                setBusy(false);
                e.target.value = "";
              }
            }}
          />
        </label>
        {busy && <Busy />}
        {preview && <p className="info-note">{preview}</p>}
        {errors.map((x, i) => (
          <ErrorNotice key={i} message={x} />
        ))}
      </section>
      <section className="panel settings-card">
        <h2>Report context</h2>
        <p>
          Header metadata for this configuration. Transaction inputter, approver
          and carrier are supplied separately for each case.
        </p>
        {Object.entries(draft.report_context || {}).map(([key, v]) => (
          <label key={key}>
            {key.replaceAll("_", " ")}
            <input
              disabled={!editable}
              value={v}
              onChange={(e) =>
                update({
                  ...draft,
                  report_context: {
                    ...draft.report_context,
                    [key]: e.target.value,
                  },
                })
              }
            />
          </label>
        ))}
      </section>
      {/* Phase 1 §3.3.4 — Message Templates Editor */}
      <section className="panel settings-card" style={{ gridColumn: "1 / -1" }}>
        <h2>Message templates</h2>
        <p>
          Editable finding messages, grouping reasons, and status explanations.
          Changes apply to new cases after publishing. Missing keys fall back to
          hardcoded defaults.
        </p>
        <table className="config-table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(draft.sop_message_templates || {}).map(
              ([key, msg]) => (
                <tr key={key}>
                  <td>
                    <code>{key}</code>
                  </td>
                  <td>
                    <input
                      disabled={!editable}
                      value={msg}
                      onChange={(e) =>
                        update({
                          ...draft,
                          sop_message_templates: {
                            ...draft.sop_message_templates,
                            [key]: e.target.value,
                          },
                        })
                      }
                    />
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </section>
      {/* Phase 1 §3.3.5 — Grouping Configuration Editor */}
      <section className="panel settings-card" style={{ gridColumn: "1 / -1" }}>
        <h2>Filename grouping rules</h2>
        <p>
          Prefixes are stripped before customer name extraction. Suffix aliases
          map abbreviations to canonical document labels.
        </p>
        <label>Prefixes to strip (one per line)</label>
        <textarea
          disabled={!editable}
          rows={8}
          value={(draft.grouping_prefixes || []).join("\n")}
          onChange={(e) =>
            update({
              ...draft,
              grouping_prefixes: e.target.value
                .split("\n")
                .filter(Boolean),
            })
          }
        />
        <label>Suffix aliases (abbreviation = canonical suffix)</label>
        <table className="config-table">
          <thead>
            <tr>
              <th>Abbreviation</th>
              <th>Canonical suffix</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(draft.suffix_aliases || {}).map(
              ([abbr, canonical]) => (
                <tr key={abbr}>
                  <td>
                    <input
                      disabled={!editable}
                      value={abbr}
                      onChange={(e) => {
                        const next = { ...draft.suffix_aliases };
                        delete next[abbr];
                        next[e.target.value] = canonical;
                        update({ ...draft, suffix_aliases: next });
                      }}
                    />
                  </td>
                  <td>
                    <input
                      disabled={!editable}
                      value={canonical}
                      onChange={(e) =>
                        update({
                          ...draft,
                          suffix_aliases: {
                            ...draft.suffix_aliases,
                            [abbr]: e.target.value,
                          },
                        })
                      }
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      disabled={!editable}
                      onClick={() => {
                        const next = { ...draft.suffix_aliases };
                        delete next[abbr];
                        update({ ...draft, suffix_aliases: next });
                      }}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
        <button
          type="button"
          disabled={!editable}
          onClick={() =>
            update({
              ...draft,
              suffix_aliases: {
                ...draft.suffix_aliases,
                "new-alias": "canonical-suffix",
              },
            })
          }
        >
          Add alias
        </button>
      </section>
      <section className="panel settings-card" style={{ gridColumn: "1 / -1" }}>
        <h2>Workflow steps</h2>
        <p>
          The pipeline order follows dependency constraints. Configure supported
          parameters and provider polling; creation is submitted once. Fixed
          steps retain their registered action and error policy.
        </p>
        {draft.provider === "spider-ai" && (
          <p className="info-note">
            Spider-AI handles formatting during extraction. Parse and document
            normalization/validation are skipped; case SOP and report steps
            still run.
          </p>
        )}
        {(draft.workflow || []).map((s, i) => (
          <details key={s.step_id} className="rule-card">
            <summary>
              {s.order}. {s.action.replaceAll("_", " ")} ·{" "}
              {draft.provider === "spider-ai" &&
              ["parse", "normalize_validate"].includes(s.action)
                ? "Skipped for Spider-AI"
                : s.preset}
            </summary>
            <div className="form-grid">
              {Object.entries(s.parameters).map(([k, v]) => (
                <label key={k}>
                  {k.replaceAll("_", " ")}
                  {["tier"].includes(k) ? (
                    <select
                      disabled={!editable}
                      value={String(v)}
                      onChange={(e) => {
                        const steps = structuredClone(draft.workflow!);
                        steps[i].parameters[k] = e.target.value;
                        update({
                          ...draft,
                          workflow: steps,
                          [s.action === "parse"
                            ? "parse_tier"
                            : "extract_tier"]: e.target.value,
                        });
                      }}
                    >
                      {["agentic_plus", "agentic", "cost_effective"].map(
                        (x) => (
                          <option key={x}>{x}</option>
                        ),
                      )}
                    </select>
                  ) : typeof v === "number" || k === "version" ? (
                    <input
                      disabled={!editable}
                      type={typeof v === "number" ? "number" : "text"}
                      step={k === "minimum_confidence" ? "0.01" : "1"}
                      value={String(v)}
                      onChange={(e) => {
                        const steps = structuredClone(draft.workflow!);
                        steps[i].parameters[k] =
                          typeof v === "number"
                            ? Number(e.target.value)
                            : e.target.value;
                        update({
                          ...draft,
                          workflow: steps,
                          ...(k === "minimum_confidence"
                            ? {
                                classification_threshold: Number(
                                  e.target.value,
                                ),
                              }
                            : {}),
                          ...(k === "version"
                            ? { parse_version: e.target.value }
                            : {}),
                        });
                      }}
                    />
                  ) : (
                    <span className="subtext">
                      {JSON.stringify(v)} · preset invariant
                    </span>
                  )}
                </label>
              ))}
              <label>
                Provider poll deadline (seconds)
                <input
                  type="number"
                  disabled={
                    !editable ||
                    !["classify", "parse", "extract"].includes(s.action)
                  }
                  value={s.timeout_seconds}
                  onChange={(e) => {
                    const steps = structuredClone(draft.workflow!);
                    steps[i].timeout_seconds = Number(e.target.value);
                    update({ ...draft, workflow: steps });
                  }}
                />
              </label>
              <label>
                Read retries
                <input
                  type="number"
                  disabled={
                    !editable ||
                    !["classify", "parse", "extract"].includes(s.action)
                  }
                  value={s.read_poll_retries}
                  onChange={(e) => {
                    const steps = structuredClone(draft.workflow!);
                    steps[i].read_poll_retries = Number(e.target.value);
                    update({ ...draft, workflow: steps });
                  }}
                />
              </label>
            </div>
          </details>
        ))}
      </section>
    </div>
  );
}

const comparisons = [
  "match_exact",
  "match_address",
  "match_purpose",
  "match_money",
  "date_equal",
  "date_on_or_after",
  "signature_visual_consistency",
];
export function SOPBuilder({
  draft,
  update,
  editable,
  family,
}: Props & { family: DocumentFamily }) {
  const {
    data: fullCatalog,
    loading,
    error,
  } = useData<AutomationCatalog>("/config/catalog", 0);
  const [editing, setEditing] = useState<SOPRule | null>(null);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [original, setOriginal] = useState("");
  const [issue, setIssue] = useState("");
  const catalog = fullCatalog
    ? {
        ...fullCatalog,
        fields: fullCatalog.fields.filter((f) => inFamily(f.document, family, draft)),
        scope: fullCatalog.scope.filter((entry) => family!=="forex"&&family!=="account_opening" || ruleInFamily(entry, family, draft)),
      }
    : undefined;
  if (!catalog)
    return loading ? (
      <Busy />
    ) : (
      <ErrorNotice message={error || "Field catalog unavailable"} />
    );
  const allRules = draft.sop_rules || [];
  const rules = allRules.filter((rule) => ruleInFamily(rule, family, draft));
  const filtered = rules.filter((r) =>
    `${r.id} ${r.label} ${r.path} ${r.other_path} ${r.source_ref}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const currentPage = Math.min(
    page,
    Math.max(0, Math.ceil(filtered.length / 15) - 1),
  );
  const start = (r?: SOPRule) => {
    setIssue("");
    setOriginal(r?.id || "");
    setEditing(
      r
        ? structuredClone(r)
        : {
            id: "",
            label: "",
            enabled: true,
            source_ref: catalog.scope[0].source_ref,
            scope_basis: catalog.scope[0].scope_basis,
            report_category: catalog.categories[0],
            operator: "match_exact",
            path: "ektp.name",
            other_path:
              family === "account_opening"
                ? "account_opening_form.customer_name"
                : "application.remitter.name",
            severity: "FAIL",
            condition_operator: "always",
            comparison_policy: "exact_case_and_whitespace",
          },
    );
  };
  const patch = (v: Partial<SOPRule>) =>
    setEditing(editing ? { ...editing, ...v } : null);
  const allowedFields = (op: string) =>
    catalog.fields.filter(
      (f) => !catalog.operators[op] || catalog.operators[op]!.includes(f.type),
    );
  function fieldSelect(key: "path" | "other_path", currency = false) {
    if (!editing) return null;
    const path = currency
      ? editing[key === "path" ? "currency_path" : "other_currency_path"] || ""
      : editing[key];
    const doc = path.split(".")[0];
    const fs = currency
      ? catalog!.fields.filter((f) => f.type === "text")
      : allowedFields(editing.operator);
    const docs = Array.from(new Set(fs.map((f) => f.document)));
    const set = (v: string) =>
      patch(
        currency
          ? { [key === "path" ? "currency_path" : "other_currency_path"]: v }
          : { [key]: v },
      );
    return (
      <div className="form-grid">
        <label>
          {currency
            ? "Currency document"
            : key === "path"
              ? "Document"
              : "Reference document"}
          <select
            aria-label={
              currency
                ? "Currency document"
                : key === "path"
                  ? "Document"
                  : "Reference document"
            }
            value={doc}
            onChange={(e) =>
              set(fs.find((f) => f.document === e.target.value)?.path || "")
            }
          >
            <option value="">Select document</option>
            {docs.map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
        </label>
        <label>
          {currency ? "Currency field" : "Field"}
          <select
            aria-label={currency ? "Currency field" : "Field"}
            value={path}
            onChange={(e) => set(e.target.value)}
          >
            <option value="">Select field</option>
            {fs
              .filter((f) => f.document === doc)
              .map((f: FieldCatalog) => (
                <option key={f.path} value={f.path}>
                  {f.label} · {f.field} ({f.type})
                </option>
              ))}
          </select>
        </label>
      </div>
    );
  }
  return (
    <div className="settings-grid sop-workspace">
      <section className="panel settings-card">
        <div className="section-head">
          <h2>Document-only SOP rules</h2>
          <button
            className="secondary"
            disabled={!editable}
            onClick={() => start()}
          >
            Add rule
          </button>
        </div>
        <p>
          Approved YES controls plus all SOP3 system checks. External
          verification and CCTV are excluded. Unknown applicability fails data checks; only visual evidence can await review.
        </p>
        <label>
          Search SOP rules
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
            placeholder="Rule name, field, ID or source"
          />
        </label>
        <div className="button-row">
          <button
            disabled={currentPage === 0}
            onClick={() => setPage(currentPage - 1)}
          >
            Previous
          </button>
          <span>
            {filtered.length} results · Page {currentPage + 1} /{" "}
            {Math.max(1, Math.ceil(filtered.length / 15))}
          </span>
          <button
            disabled={(currentPage + 1) * 15 >= filtered.length}
            onClick={() => setPage(currentPage + 1)}
          >
            Next
          </button>
        </div>
        {filtered.slice(currentPage * 15, currentPage * 15 + 15).map((r) => (
          <div className="rule-card" key={r.id}>
            <strong>{r.label || r.id}</strong>
            <div>
              <Badge value={r.enabled ? "ACTIVE" : "DISABLED"} />
              <code>
                {r.source_ref} · {r.report_category}
              </code>
            </div>
            <p>
              {r.path} · {r.operator} · {r.other_path}
            </p>
            <button
              className="secondary"
              disabled={!editable}
              onClick={() => start(r)}
            >
              Edit rule
            </button>
          </div>
        ))}
      </section>
      {editing && (
        <Modal
          className="sop-rule-modal"
          title={original ? "Edit SOP rule" : "Add SOP rule"}
          onClose={() => setEditing(null)}
        >
          {editing ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (
                  allRules.some((r) => r.id === editing.id && r.id !== original)
                ) {
                  setIssue("Rule ID already exists");
                  return;
                }
                if (
                  !editing.path ||
                  (comparisons.includes(editing.operator) &&
                    !editing.other_path)
                ) {
                  setIssue("Choose compatible document fields");
                  return;
                }
                update({
                  ...draft,
                  sop_rules: original
                    ? allRules.map((r) => (r.id === original ? editing : r))
                    : [...allRules, editing],
                  ...(family!=="forex"&&family!=="account_opening" ? {document_families:{...draft.document_families,[family]:{...draft.document_families![family],sop_rule_ids:[...(draft.document_families![family].sop_rule_ids||[]).filter(id=>id!==original&&id!==editing.id),editing.id]}}} : {}),
                });
                setEditing(null);
              }}
            >
              <fieldset disabled={!editable}>
                {issue && <ErrorNotice message={issue} />}
                <h2>{original ? "Edit rule" : "New rule"}</h2>
                <label>
                  Rule ID
                  <input
                    required
                    pattern="[A-Za-z0-9_.-]+"
                    value={editing.id}
                    onChange={(e) => patch({ id: e.target.value })}
                  />
                </label>
                <label>
                  Finding message
                  <input
                    required
                    value={editing.label}
                    onChange={(e) => patch({ label: e.target.value })}
                  />
                </label>
                <label>
                  Approved source
                  <select
                    aria-label="Approved source"
                    value={editing.source_ref}
                    onChange={(e) =>
                      patch({
                        source_ref: e.target.value,
                        scope_basis: catalog.scope.find(
                          (x) => x.source_ref === e.target.value,
                        )!.scope_basis,
                      })
                    }
                  >
                    {catalog.scope.map((x) => (
                      <option key={x.source_ref}>{x.source_ref}</option>
                    ))}
                  </select>
                </label>
                <p className="info-note">
                  {
                    catalog.scope.find(
                      (x) => x.source_ref === editing.source_ref,
                    )?.included_and_excluded_components
                  }
                </p>
                <label>
                  Report category
                  <select
                    aria-label="Report category"
                    value={editing.report_category}
                    onChange={(e) => patch({ report_category: e.target.value })}
                  >
                    {catalog.categories.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Check preset
                  <select
                    aria-label="Check preset"
                    value={editing.operator}
                    onChange={(e) => {
                      const op = e.target.value;
                      patch({
                        operator: op,
                        path: allowedFields(op)[0]?.path || "",
                        other_path: allowedFields(op)[0]?.path || "",
                      });
                    }}
                  >
                    {Object.keys(catalog.operators).map((op) => (
                      <option key={op}>{op}</option>
                    ))}
                  </select>
                </label>
                {fieldSelect("path")}
                {comparisons.includes(editing.operator) &&
                  fieldSelect("other_path")}
                {editing.operator === "match_money" && (
                  <>
                    {fieldSelect("path", true)}
                    {fieldSelect("other_path", true)}
                  </>
                )}
                <label>
                  Condition
                  <select
                    aria-label="Condition"
                    value={editing.condition_operator || "always"}
                    onChange={(e) =>
                      patch({ condition_operator: e.target.value })
                    }
                  >
                    {["always", "equals", "in", "document_present"].map((x) => (
                      <option key={x}>{x}</option>
                    ))}
                  </select>
                </label>
                {["equals", "in"].includes(
                  editing.condition_operator || "",
                ) && (
                  <>
                    <label>
                      Case context
                      <select
                        aria-label="Case context"
                        value={editing.condition_key || ""}
                        onChange={(e) =>
                          patch({
                            condition_key: e.target.value,
                            condition_value: catalog.context[e.target.value][0],
                          })
                        }
                      >
                        <option value="">Choose context</option>
                        {Object.keys(catalog.context).map((x) => (
                          <option key={x}>{x}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Expected context
                      {editing.condition_operator === "in" ? (
                        <input
                          placeholder="Comma-separated allowed values"
                          aria-label="Expected context"
                          value={editing.condition_value || ""}
                          onChange={(e) =>
                            patch({ condition_value: e.target.value })
                          }
                        />
                      ) : (
                        <select
                          aria-label="Expected context"
                          value={editing.condition_value || ""}
                          onChange={(e) =>
                            patch({ condition_value: e.target.value })
                          }
                        >
                          {(
                            catalog.context[editing.condition_key || ""] || []
                          ).map((x) => (
                            <option key={x}>{x}</option>
                          ))}
                        </select>
                      )}
                    </label>
                  </>
                )}
                {editing.condition_operator === "document_present" && (
                  <label>
                    Conditional document
                    <select
                      aria-label="Expected context"
                      value={editing.condition_value || ""}
                      onChange={(e) =>
                        patch({ condition_value: e.target.value })
                      }
                    >
                      <option value="">Choose document</option>
                      {Object.keys(draft.profiles).map((x) => (
                        <option key={x}>{x}</option>
                      ))}
                    </select>
                  </label>
                )}
                {editing.operator==="account_check"&&<AccountCondition value={editing.comparison_policy||"{}"}
                  onChange={value=>patch({comparison_policy:value})} fields={catalog.fields}/>}
                <label>
                  Comparison policy / rationale
                  <input
                    value={editing.comparison_policy || ""}
                    onChange={(e) =>
                      patch({ comparison_policy: e.target.value })
                    }
                  />
                </label>
                <label>
                  Violation result
                  <select
                    aria-label="Violation result"
                    value={editing.severity}
                    onChange={(e) =>
                      patch({ severity: e.target.value as "FAIL" | "REVIEW" })
                    }
                  >
                    <option>FAIL</option>
                    <option>REVIEW</option>
                  </select>
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={editing.enabled}
                    onChange={(e) => patch({ enabled: e.target.checked })}
                  />{" "}
                  Rule enabled
                </label>
                <div className="button-row">
                  <button className="primary">Apply to draft</button>
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => setEditing(null)}
                  >
                    Cancel
                  </button>
                </div>
              </fieldset>
            </form>
          ) : (
            <>
              <h2>Rule editor</h2>
              <p>
                Choose a rule or add one. Select a document first; only its
                compatible extracted fields are offered.
              </p>
            </>
          )}
        </Modal>
      )}
    </div>
  );
}
