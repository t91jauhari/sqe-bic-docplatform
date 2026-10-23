"use client";

export type NumericConnectorField = { key: string; label: string; minimum?: number; maximum?: number;
  integer: boolean; nullable: boolean; description?: string };
export type NumericConnectorDraft = Record<string, number | null>;

export function numericConnectorValues(fields: NumericConnectorField[], options: Record<string, unknown>, draft: NumericConnectorDraft) {
  return Object.fromEntries(fields.map(field => [field.key,
    Object.prototype.hasOwnProperty.call(draft, field.key) ? draft[field.key] : options[field.key] ?? null]));
}

export function ConnectorOptions({ fields, options, draft, onChange, title = "Advanced request settings" }: {
  fields: NumericConnectorField[]; options: Record<string, unknown>; draft: NumericConnectorDraft;
  onChange: (draft: NumericConnectorDraft) => void; title?: string;
}) {
  if (!fields.length) return null;
  const values = numericConnectorValues(fields, options, draft);
  return <details className="panel"><summary>{title}</summary>
    <p>These limits apply to normal extraction and selected-field rereads. Document-profile reading controls can override sampling.</p>
    <div className="form-grid">{fields.map(field => <label key={field.key}>{field.label}
      <input type="number" required={!field.nullable} min={field.minimum} max={field.maximum}
        step={field.integer ? 1 : "any"} value={values[field.key] as number | null ?? ""}
        placeholder={field.nullable ? "Automatic" : undefined}
        onChange={event => onChange({ ...draft, [field.key]: event.target.value === "" ? null : Number(event.target.value) })} />
      {field.description && <small>{field.description}</small>}
    </label>)}</div>
  </details>;
}
