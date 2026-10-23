"use client";
import type { Profile } from "@/lib/types";

export function ProfileExtractionControls({profile,editable,onChange}:{profile:Profile;editable:boolean;onChange:(profile:Profile)=>void}) {
  const sampling=profile.policy.extraction_sampling as {temperature?:number;top_p?:number}|undefined;
  const regions=profile.policy.extraction_detail_regions as unknown[]|undefined;
  const reconciliation=profile.policy.case_address_reconciliation as {enabled:boolean;target_field:string;source_profile:string;source_field:string;minimum_similarity:number}|undefined;
  return <section className="field-instructions"><h2>Extraction consistency</h2><p>These settings apply to new uploads and field reprocessing with this published profile.</p><fieldset disabled={!editable}>
    <label>Reading consistency<select value={sampling?.temperature ?? .41} onChange={e=>onChange({...profile,policy:{...profile.policy,extraction_sampling:{temperature:Number(e.target.value),top_p:sampling?.top_p??1}}})}><option value={0}>Precise — lowest sampling variation</option><option value={.2}>Balanced — some sampling variation</option><option value={.41}>Standard — existing provider setting</option></select><small>Lower variation helps repeatability. Ambiguous handwriting can still require review.</small></label>
    <p>{regions?.length||0} enlarged original-page regions are configured. They are included automatically during normal extraction and targeted rereads. Region coordinates can be edited in the advanced profile policy.</p>
    {reconciliation&&<label className="checkbox-line"><input type="checkbox" checked={reconciliation.enabled} onChange={e=>onChange({...profile,policy:{...profile.policy,case_address_reconciliation:{...reconciliation,enabled:e.target.checked}}})}/><span>Reconcile near-identical customer addresses from the same case’s LLD<small>All address numbers must match. Conflicting sources and reviewer-corrected source fields are excluded. The original observation and source document remain traceable.</small></span></label>}
  </fieldset></section>;
}
