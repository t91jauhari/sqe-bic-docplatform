"use client";
import { useState } from "react";
import { useData } from "@/components/platform-provider";
import type { AutomationCatalog, Configuration, ContextDefinition } from "@/lib/types";

export function ContextEditor({ configuration, family, editable, onChange }: {
  configuration: Configuration; family: string; editable: boolean;
  onChange: (configuration: Configuration) => void;
}) {
  const { data: catalog } = useData<AutomationCatalog>("/config/catalog", 0);
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const definitions = configuration.context_definitions;
  const update = (id: string, value: ContextDefinition) => onChange({ ...configuration,
    context_definitions: { ...definitions, [id]: value } });
  return <details className="panel settings-card">
    <summary><strong>Case context fields</strong> · Evidence used by conditional SOP checks</summary>
    <p>Configure the values reviewers can record for this document family. Changes apply after publishing; existing cases keep their pinned definitions.</p>
    {!definitions ? <button type="button" className="secondary" disabled={!editable || !catalog?.context_definitions}
      onClick={() => onChange({ ...configuration, context_definitions: structuredClone(catalog?.context_definitions || {}) })}>
      Copy existing context definitions into draft
    </button> : <fieldset disabled={!editable}>
      {Object.entries(definitions).filter(([, spec]) => !spec.families?.length || spec.families.includes(family)).map(([id, spec]) => <details key={id} className="panel">
        <summary>{spec.label} · {spec.kind.replaceAll("_", " ")}</summary>
        <div className="form-grid">
          <label>Field ID<input value={id} readOnly /></label>
          <label>Display label<input value={spec.label} onChange={event => update(id, { ...spec, label: event.target.value })} /></label>
          <label>Value type<select value={spec.kind} onChange={event => update(id, { ...spec,
            kind: event.target.value as ContextDefinition["kind"], options: [], profiles: [] })}>
            <option value="enum">Choice list</option><option value="text">Text</option>
            <option value="digits">Digits (keep leading zeros)</option><option value="document_reference">Document selection</option>
          </select></label>
          <label>Maximum value length<input type="number" min={1} max={200} value={spec.max_length || 200}
            onChange={event => update(id, { ...spec, max_length: Number(event.target.value) })} /></label>
          {spec.kind === "enum" && <label>Choices, one per line<textarea value={(spec.options || []).join("\n")}
            onChange={event => update(id, { ...spec, options: event.target.value.split("\n") })} /></label>}
          {spec.kind === "document_reference" && <label>Allowed document profiles<select multiple value={spec.profiles || []}
            onChange={event => update(id, { ...spec, profiles: Array.from(event.target.selectedOptions, option => option.value) })}>
            {Object.entries(configuration.profiles).map(([profile, value]) => <option key={profile} value={profile}>{value.label}</option>)}
          </select></label>}
        </div>
        <p className="subtext">{spec.families?.length ? "Applies to: " + spec.families.join(", ") : "Shared across document families"}</p>
        <button type="button" className="secondary" onClick={() => {
          const next = { ...definitions }; delete next[id]; onChange({ ...configuration, context_definitions: next });
        }}>Remove field from draft</button>
      </details>)}
      <label>New field ID<input placeholder="customer_risk_band" value={key} onChange={event => setKey(event.target.value)} /></label>
      {error && <p role="alert">{error}</p>}
      <button type="button" className="secondary" onClick={() => {
        if (!/^[a-z][a-z0-9_]{0,79}$/.test(key) || definitions[key]) { setError("Use a unique lowercase ID with letters, numbers or underscores."); return; }
        update(key, { label: key.replaceAll("_", " "), kind: "text", families: [family], max_length: 200 });
        setKey(""); setError("");
      }}>Add context field</button>
    </fieldset>}
  </details>;
}
