"use client";
import type { Configuration } from "@/lib/types";

type Rule = NonNullable<Configuration["generic_sop_rules"]>[number];
export type FieldOptions = {
  fields: { path: string; schema_path: string; label: string; profile_label: string }[];
  context_options: Record<string, string[]>;
};

export function ComparisonFields({ rule, options, onChange }: {
  rule: Rule; options: FieldOptions | null; onChange: (patch: Partial<Rule>) => void;
}) {
  function bind(side: "left" | "right", path: string) {
    if (!options) return;
    const selected = options.fields.find(field => field.path === path);
    if (!selected) return;
    const policy = { ...rule.policy, [side]: path };
    const schema_paths = Object.fromEntries([policy.left, policy.right].map(field => [
      field, field === path ? selected.schema_path : rule.schema_paths?.[field] || options.fields.find(option => option.path === field)?.schema_path || field,
    ]));
    onChange({ policy, schema_paths });
  }
  return <details>
    <summary>Edit compared fields and applicability</summary>
    <p>Choose two text fields from this document family. Missing or uncertain data fails the check.</p>
    {!options ? <p role="status">Loading field options…</p> : <>
      {(["left", "right"] as const).map(side => <label key={side}>
        {side === "left" ? "Source field" : "Compared field"}
        <select aria-label={`${side === "left" ? "Source" : "Compared"} field for ${rule.id}`} value={rule.policy[side]}
          onChange={event => bind(side, event.target.value)}>
          {!options.fields.some(field => field.path === rule.policy[side]) && <option value={rule.policy[side]}>Current binding: {rule.policy[side]}</option>}
          {options.fields.map(field => <option key={field.path} value={field.path}
            disabled={field.path === rule.policy[side === "left" ? "right" : "left"]}>
            {field.profile_label} · {field.label} ({field.path})
          </option>)}
        </select>
      </label>)}
      <label>When to run this check
        <select aria-label={`Applicability for ${rule.id}`} value={rule.applicability?.context_key || ""}
          onChange={event => onChange({ applicability: event.target.value ? {
            context_key: event.target.value,
            equals: options.context_options[event.target.value].find(value => value !== "UNKNOWN") || "",
          } : null })}>
          <option value="">Always</option>
          {rule.applicability && !options.context_options[rule.applicability.context_key] &&
            <option value={rule.applicability.context_key}>{rule.applicability.context_key}</option>}
          {Object.keys(options.context_options).map(key => <option key={key} value={key}>When {key.replaceAll("_", " ")} matches</option>)}
        </select>
      </label>
      {rule.applicability && <label>Required context value
        <select aria-label={`Context value for ${rule.id}`} value={rule.applicability.equals}
          onChange={event => onChange({ applicability: { ...rule.applicability!, equals: event.target.value } })}>
          {!(options.context_options[rule.applicability.context_key] || []).includes(rule.applicability.equals) &&
            <option value={rule.applicability.equals}>{rule.applicability.equals}</option>}
          {(options.context_options[rule.applicability.context_key] || []).filter(value => value !== "UNKNOWN").map(value => <option key={value}>{value}</option>)}
        </select>
        <small>Other known values make this rule not applicable. Unknown context fails the check.</small>
      </label>}
    </>}
  </details>;
}
