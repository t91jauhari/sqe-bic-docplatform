"use client";
import {useData} from "./platform-provider";
import type {Configuration} from "@/lib/types";

type Definitions = NonNullable<Configuration["report_definitions"]>;
export function ReportBindings({configured, onChange, layout}: {configured?: Definitions[string] | null; onChange: (value: Definitions[string]) => void; layout: string}) {
  const {data, error} = useData<Definitions>("/config/report-bindings",0);
  const definition = configured || data?.[layout];
  if (!definition) return error ? <p role="alert">Unable to load report mappings. Reload to configure them.</p> : <p>Loading report mappings…</p>;
  const save = onChange;
  const labels: Record<string,string> = {customer:"Customer name",account:"Account number",transaction_type:"Transaction type",inputter:"Inputter",approver:"Approver",carrier:"Transaction carrier",transaction_date:"Transaction date"};
  return <details><summary>Report field mappings</summary>
    <p>Choose where this family’s report values come from. These mappings affect display only. SOP findings and scores retain their original rules. Changes apply after testing and publishing.</p>
    <label>Report timezone<input value={definition.timezone} placeholder="Asia/Jakarta" onChange={event=>save({...definition,timezone:event.target.value})}/></label>
    {Object.entries(definition.bindings).map(([key,binding])=><fieldset key={key} className="panel">
      <legend>{labels[key] || key}</legend>
      <label>Value source<select value={binding.source} onChange={event=>{
        const source=event.target.value as typeof binding.source;
        save({...definition,bindings:{...definition.bindings,[key]:{source,...(source==="document"||source==="context"?{path:""}:{})}}});
      }}><option value="document">Extracted document field</option><option value="context">Recorded case context</option><option value="customer">Customer grouping name</option><option value="literal">Fixed report text</option></select></label>
      {(binding.source==="document"||binding.source==="context")&&<label>{binding.source==="document"?"Document field path":"Context field ID"}<input value={binding.path||""} maxLength={500} onChange={event=>save({...definition,bindings:{...definition.bindings,[key]:{...binding,path:event.target.value}}})}/><small>{binding.source==="document"?"Use profile.field, for example application.transaction_date. Test settings verifies the field exists.":"Use a field ID from the case context configuration, for example transaction_inputter."}</small></label>}
      <label>{binding.source==="literal"?"Fixed text":"Value when the source is empty"}<input value={binding.default||""} maxLength={500} onChange={event=>save({...definition,bindings:{...definition.bindings,[key]:{...binding,default:event.target.value||null}}})}/></label>
      {binding.source==="document"&&<label className="check-label"><input type="checkbox" checked={binding.fallback_customer||false} onChange={event=>save({...definition,bindings:{...definition.bindings,[key]:{...binding,fallback_customer:event.target.checked}}})}/>Use customer grouping name when this field is empty</label>}
    </fieldset>)}
  </details>;
}
