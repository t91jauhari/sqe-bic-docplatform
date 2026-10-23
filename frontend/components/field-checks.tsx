"use client";
import {useState} from "react";
import type {Profile} from "@/lib/types";

export function FieldChecks({profile,onChange}: {profile: Profile; onChange:(profile:Profile)=>void}) {
  const checks=profile.field_checks || {};
  const available=profile.columns.filter(([key])=>!checks[key] && !profile.schema?.properties?.[key]?.properties?.present);
  const [selected,setSelected]=useState("");
  const save=(key:string,value:NonNullable<Profile["field_checks"]>[string])=>onChange({...profile,field_checks:{...checks,[key]:value}});
  return <details className="panel settings-card"><summary>Data field validation</summary>
    <p>Define checks on extracted values without changing their text. These checks apply on future extraction and rereads after publication. Signature and stamp verification belongs in visual SOP review. Unconfigured Spider fields retain their existing validation behavior.</p>
    <label>Field to validate<select value={selected} onChange={event=>setSelected(event.target.value)}><option value="">Choose a field</option>{available.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
    <button type="button" disabled={!selected || !available.some(([key])=>key===selected)} onClick={()=>{save(selected,{kind:"text",required:true});setSelected("");}}>Add field check</button>
    {Object.entries(checks).map(([key,check])=><fieldset className="panel" key={key}><legend>{profile.columns.find(([field])=>field===key)?.[1] || key}</legend>
      <label>Expected value<select value={check.kind} onChange={event=>save(key,{kind:event.target.value as typeof check.kind,required:check.required??true,...(event.target.value==="choice"?{choices:[]}: {})})}>
        <option value="text">Nonempty text</option><option value="identifier">Digits / identifier</option><option value="date">Calendar date</option><option value="number">Numeric amount</option><option value="choice">Allowed choices</option><option value="boolean">True or false value</option>
      </select></label>
      <label className="check-label"><input type="checkbox" checked={check.required??true} onChange={event=>save(key,{...check,required:event.target.checked})}/>A value is required</label>
      {check.kind==="identifier"&&<label>Exact digit count<input type="number" min={1} max={100} value={check.digits??""} placeholder="Any nonempty digit count" onChange={event=>save(key,{...check,digits:event.target.value?Number(event.target.value):null})}/></label>}
      {check.kind==="choice"&&<><label>Allowed values, one per line<textarea value={(check.choices||[]).join("\n")} onChange={event=>save(key,{...check,choices:event.target.value.split("\n")})}/></label><label>Comparison<select value={check.normalization||"literal"} onChange={event=>save(key,{...check,normalization:event.target.value as "literal"|"casefold_whitespace"})}><option value="literal">Exact text</option><option value="casefold_whitespace">Ignore case and repeated spaces</option></select></label></>}
      {check.kind==="number"&&<><label>Decimal separator<select value={check.decimal_separator||"."} onChange={event=>save(key,{...check,decimal_separator:event.target.value as "."|","})}><option value=".">Dot (.)</option><option value=",">Comma (,)</option></select></label><label>Thousands separator<select value={check.thousands_separator??""} onChange={event=>save(key,{...check,thousands_separator:(event.target.value||null) as "."|","|" "|null})}><option value="">None</option><option value=".">Dot (.)</option><option value=",">Comma (,)</option><option value=" ">Space</option></select></label><label>Required currency prefix, if printed<input value={check.currency||""} maxLength={3} placeholder="For example USD; blank for amount only" onChange={event=>save(key,{...check,currency:event.target.value||null})}/></label></>}
      <button type="button" className="secondary" onClick={()=>{const next={...checks};delete next[key];onChange({...profile,field_checks:next});}}>Remove check</button>
    </fieldset>)}
  </details>;
}
