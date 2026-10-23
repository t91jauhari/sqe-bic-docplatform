"use client";
import {useData} from "./platform-provider";

export type DatasetPolicy = {
  enabled: boolean;
  minimum_similarity: number;
  acceptance_similarity: number;
  minimum_length: number;
  maximum_length: number;
  acceptance_minimum_length: number;
  long_text_length: number;
  short_edit_limit: number;
  long_edit_limit: number;
  descriptive_fields: string[];
  excluded_fields: string[];
  excluded_suffixes: string[];
};

export function DatasetPolicyEditor({configured, onChange}: {
  configured?: Partial<DatasetPolicy>;
  onChange: (value: Partial<DatasetPolicy> | undefined) => void;
}) {
  const {data, error} = useData<{dataset_comparison_policy: DatasetPolicy}>("/config/catalog", 0);
  if (!data?.dataset_comparison_policy) return <p role={error ? "alert" : undefined}>{error ? "Unable to load comparison defaults. Reload this page." : "Loading comparison defaults…"}</p>;
  const policy = {...data.dataset_comparison_policy, ...configured};
  const patch = (value: Partial<DatasetPolicy>) => onChange({...configured, ...value});
  const numbers: [keyof DatasetPolicy, string, number, number, number][] = [
    ["minimum_similarity", "Minimum similarity for review", 0, 1, .01],
    ["acceptance_similarity", "Similarity needed to accept descriptive text", 0, 1, .01],
    ["minimum_length", "Shortest text eligible for typo comparison", 1, 10000, 1],
    ["maximum_length", "Longest text eligible for typo comparison", 1, 10000, 1],
    ["acceptance_minimum_length", "Shortest descriptive text that may be accepted", 1, 10000, 1],
    ["long_text_length", "Length where the longer-text edit limit applies", 1, 10000, 1],
    ["short_edit_limit", "Allowed character edits in short text", 0, 10, 1],
    ["long_edit_limit", "Allowed character edits in longer text", 0, 10, 1],
  ];
  return <details>
    <summary>Reference comparison tolerances</summary>
    <p>These settings compare extracted values with the reference dataset for this family. Different digits always prevent a fuzzy match. SOP scores use their own rules.</p>
    <label className="checkbox-line"><input type="checkbox" checked={policy.enabled} onChange={e=>patch({enabled:e.target.checked})}/><span>Allow conservative text similarity<small>Turn off to require normalized exact matches.</small></span></label>
    {policy.enabled && <>
      <div className="form-row">{numbers.map(([key,label,min,max,step])=><label key={key}>{label}<input type="number" min={min} max={max} step={step} value={policy[key] as number} onChange={e=>{if(e.target.value!=="")patch({[key]:Number(e.target.value)});}}/></label>)}</div>
      {policy.acceptance_similarity < policy.minimum_similarity && <p role="alert">Acceptance similarity must be at least the review similarity.</p>}
      {([['descriptive_fields','Fields eligible for automatic text similarity acceptance'],['excluded_fields','Fields that always require an exact match'],['excluded_suffixes','Field suffixes that require an exact match']] as const).map(([key,label])=><label key={key}>{label}<textarea rows={3} value={policy[key].join("\n")} onChange={e=>patch({[key]:Array.from(new Set(e.target.value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean)))})}/><small>One schema field name or suffix per line.</small></label>)}
    </>}
    {configured && <button type="button" className="secondary" onClick={()=>onChange(undefined)}>Use release defaults</button>}
  </details>;
}
