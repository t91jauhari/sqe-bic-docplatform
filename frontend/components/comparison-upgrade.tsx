"use client";

import { useEffect, useState } from "react";
import { ArrowRightLeft, Eye, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import type { Configuration } from "@/lib/types";
import { ComparisonFields, type FieldOptions } from "@/components/comparison-fields";

type Candidate = { id: string; label: string; left: string; right: string; families: string[] };
type Preview = { source_version: number; basis_sha256: string; converted_rule_ids: string[]; payload: Configuration };

export function ComparisonUpgrade({ configuration, version, editable, onApply, family }: {
  configuration: Configuration; version: number; editable: boolean;
  family: string;
  onApply: (configuration: Configuration) => void;
}) {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewSource, setPreviewSource] = useState<Configuration | null>(null);
  const [previewFamily, setPreviewFamily] = useState("");
  const [loadingCandidates, setLoadingCandidates] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldOptions, setFieldOptions] = useState<FieldOptions | null>(null);
  const [newId, setNewId] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newLeft, setNewLeft] = useState("");
  const [newRight, setNewRight] = useState("");
  useEffect(() => {
    let cancelled = false;
    setFieldOptions(null);
    const timer = setTimeout(() => { if (editable) api<FieldOptions>("/config/upgrades/comparisons/fields", {
      method: "POST", body: JSON.stringify({ expected_version: version, family, payload: configuration }),
    }).then(result => { if (!cancelled) setFieldOptions(result); })
      .catch(error => { if (!cancelled) setError(error instanceof Error ? error.message : "Could not load fields."); }); }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [configuration.profiles, configuration.document_families, configuration.context_definitions, version, family, editable]);
  useEffect(() => { setNewLeft(""); setNewRight(""); }, [family]);
  useEffect(() => {
    let cancelled = false;
    setLoadingCandidates(true);
    if (editable) api<{ candidates: Candidate[] }>("/config/upgrades/comparisons")
      .then(result => { if (!cancelled) setCandidates(result.candidates); })
      .catch(error => { if (!cancelled) setError(error instanceof Error ? error.message : "Could not load upgrade options."); })
      .finally(() => { if (!cancelled) setLoadingCandidates(false); });
    return () => { cancelled = true; };
  }, [version, editable]);
  useEffect(() => { setPreview(null); setPreviewSource(null); setSelected([]); }, [configuration, version, family]);
  if (!editable) return null;
  const available = candidates.filter(candidate => candidate.families.includes(family) && configuration.sop_rules?.some(rule => rule.id === candidate.id));
  const configured = (configuration.generic_sop_rules || []).filter(rule => rule.families.includes(family));
  const previewCurrent = preview && previewSource === configuration && preview.source_version === version && previewFamily === family;
  async function inspect() {
    setBusy(true); setError(""); setPreview(null);
    try {
      const result = await api<Preview>("/config/upgrades/comparisons/preview", {
        method: "POST", body: JSON.stringify({ expected_version: version, rule_ids: selected, payload: configuration }),
      });
      setPreview(result); setPreviewSource(configuration); setPreviewFamily(family);
    } catch (error) { setError(error instanceof Error ? error.message : "Preview failed."); }
    finally { setBusy(false); }
  }
  return <><section className="panel settings-card" aria-labelledby="new-comparison-title">
    <h2 id="new-comparison-title">Add a text comparison</h2>
    <p>Compare two configured fields in this family. Matching values pass for one point; missing, unclear or different values fail. This check does not perform visual verification.</p>
    <div className="form-grid">
      <label>New comparison ID<input value={newId} placeholder="customer_name_consistency" onChange={event => setNewId(event.target.value)} /></label>
      <label>Check description<input value={newLabel} placeholder="Customer names must match" onChange={event => setNewLabel(event.target.value)} /></label>
      <label>First text field<select value={newLeft} onChange={event => { setNewLeft(event.target.value); if (newRight === event.target.value) setNewRight(""); }}>
        <option value="">Choose a field</option>
        {fieldOptions?.fields.map(field => <option key={field.path} value={field.path}>{field.profile_label} · {field.label} ({field.path})</option>)}
      </select></label>
      <label>Compared text field<select value={newRight} onChange={event => setNewRight(event.target.value)}>
        <option value="">Choose a different field</option>
        {fieldOptions?.fields.filter(field => field.path !== newLeft).map(field => <option key={field.path} value={field.path}>{field.profile_label} · {field.label} ({field.path})</option>)}
      </select></label>
    </div>
    <button type="button" className="secondary" disabled={!fieldOptions || fieldOptions.fields.length < 2} onClick={() => {
      if (!fieldOptions) return;
      if (!/^[A-Za-z0-9_.-]{1,100}$/.test(newId) || [...(configuration.sop_rules || []), ...(configuration.generic_sop_rules || [])].some(rule => rule.id === newId)) {
        setError("Enter a unique comparison ID using letters, digits, dots, underscores or hyphens."); return;
      }
      const left = fieldOptions.fields.find(field => field.path === newLeft);
      const right = fieldOptions.fields.find(field => field.path === newRight);
      if (!newLabel.trim() || !left || !right || left.path === right.path) { setError("Enter a description and choose two different text fields."); return; }
      const rule = { id: newId, label: newLabel.trim(), enabled: true, families: [family], report_category: "DATA_COMPLETION",
        source_ref: "Configured SOP rule", policy: { left: left.path, right: right.path, normalization: "casefold_whitespace" as const },
        schema_paths: { [left.path]: left.schema_path, [right.path]: right.schema_path } };
      onApply({ ...configuration, generic_sop_rules: [...(configuration.generic_sop_rules || []), rule],
        ...(configuration.rule_order ? { rule_order: [...configuration.rule_order, newId] } : {}),
        ...(configuration.rule_scope ? { rule_scope: { family_rule_ids: { ...configuration.rule_scope.family_rule_ids,
          [family]: [...(configuration.rule_scope.family_rule_ids[family] || []), newId] } } } : {}) });
      setNewId(""); setNewLabel(""); setNewLeft(""); setNewRight(""); setError("");
    }}>Add comparison to draft</button>
    <p className="subtext">New comparisons start with case and whitespace matching. Edit their fields, matching behavior and applicability below. Select the check in the relevant transaction flow before publishing.</p>
    {error && <p role="alert">{error}</p>}
  </section><section className="panel settings-card" aria-labelledby="comparison-upgrade-title">
    <h2 id="comparison-upgrade-title"><ArrowRightLeft size={20} aria-hidden="true" /> Upgrade comparison rules</h2>
    <p>Move supported checks into editable comparison policies. Rule IDs, scoring and order are preserved. Review first, then add the changes to your draft.</p>
    {error && <p role="alert">{error}</p>}
    {loadingCandidates ? <p role="status">Loading supported rules…</p> : available.length ? <fieldset disabled={busy}>
      <legend>Choose rules to review</legend>
      {available.map(candidate => <label key={candidate.id} style={{ display: "flex", flexDirection: "row", alignItems: "start", gap: 12 }}>
        <input type="checkbox" style={{ width: "auto", flex: "0 0 auto" }} checked={selected.includes(candidate.id)} onChange={event => {
          setPreview(null);
          setSelected(event.target.checked ? [...selected, candidate.id] : selected.filter(id => id !== candidate.id));
        }} />
        <span>{candidate.label}<small style={{ display: "block" }}>{candidate.left} ↔ {candidate.right}</small></span>
      </label>)}
      <button type="button" className="button secondary" disabled={!selected.length || busy} onClick={inspect}>
        <Eye size={16} aria-hidden="true" /> {busy ? "Preparing preview…" : `Preview ${selected.length || "selected"} rules`}
      </button>
    </fieldset> : <p>No supported rules remain in this draft.</p>}
    {previewCurrent && <div role="region" aria-label="Comparison upgrade preview">
      <h3><CheckCircle2 size={18} aria-hidden="true" /> Ready for draft review</h3>
      <p>{preview.converted_rule_ids.length} rules from configuration v{preview.source_version}. Existing cases keep their configuration.</p>
      <ul>{available.filter(candidate => preview.converted_rule_ids.includes(candidate.id)).map(candidate =>
        <li key={candidate.id}>{candidate.label}<small style={{ display: "block" }}>Case and whitespace normalized · matching text required</small></li>)}</ul>
      <button type="button" className="button" onClick={() => onApply(preview.payload)}>Add upgrade to draft</button>
      <p>Use the configuration’s Test and Publish actions when your draft is ready. This preview has not published changes.</p>
    </div>}
  </section>
  {!!configured.length && <section className="panel settings-card" aria-labelledby="configured-comparisons-title">
    <h2 id="configured-comparisons-title">Configurable comparisons</h2>
    <p>Configure matching, compared fields and applicability in your draft.</p>
    {configured.map(rule => {
      const change = (patch: Partial<typeof rule>) => onApply({ ...configuration,
        generic_sop_rules: configuration.generic_sop_rules!.map(value => value.id === rule.id ? { ...value, ...patch } : value),
      });
      return <fieldset key={rule.id}>
        <legend>{rule.label}</legend>
        <label>Rule description<input aria-label={`Description for ${rule.id}`} value={rule.label} onChange={event => change({ label: event.target.value })} /></label>
        <p>{rule.policy.left} ↔ {rule.policy.right}</p>
        <ComparisonFields rule={rule} options={fieldOptions} onChange={change} />
        <label>Matching behavior<select aria-label={`Matching behavior for ${rule.id}`} value={rule.policy.normalization || "literal"}
          onChange={event => change({ policy: { ...rule.policy, normalization: event.target.value as "literal" | "casefold_whitespace" } })}>
          <option value="literal">Exact characters</option>
          <option value="casefold_whitespace">Ignore letter case and extra spaces</option>
        </select></label>
        <label style={{ display: "flex", flexDirection: "row", justifyContent: "flex-start", alignItems: "center", gap: 8 }}><input type="checkbox" style={{ width: "auto", flex: "0 0 auto" }} checked={rule.enabled !== false} onChange={event => change({ enabled: event.target.checked })} /> Check enabled</label>
      </fieldset>;
    })}
  </section>}</>;
}
