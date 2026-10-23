"use client";
import {useData} from "./platform-provider";
import type {FieldCatalog} from "@/lib/types";
type Condition={path:string;true_values:string[];false_values:string[]};
export function AccountCondition({value,onChange,fields}: {value:string;onChange:(value:string)=>void;fields:FieldCatalog[]}) {
  const {data}=useData<Record<string,Condition>>("/config/account-conditions",0);
  let policy:Record<string,unknown>;
  try {policy=JSON.parse(value);} catch {return null;}
  if (!policy || typeof policy!=="object" || Array.isArray(policy)) return null;
  if (policy.require_two_signatures===true) {
    const paths=Array.isArray(policy.supporting_paths)?policy.supporting_paths as string[]:[];
    return <fieldset className="panel"><legend>Signature evidence bindings</legend><p>Choose the two source signing regions. The reviewer must inspect both before accepting a permitted name abbreviation.</p>
      {[0,1].map(index=><label key={index}>Signing region {index+1}<select value={paths[index]||""} onChange={event=>{const next=[paths[0]||"",paths[1]||""];next[index]=event.target.value;onChange(JSON.stringify({...policy,supporting_paths:next}));}}>
        <option value="">Use historical source region</option>{fields.filter(field=>field.type==="signature_region").map(field=><option key={field.path} value={field.path}>{field.document} · {field.label}</option>)}
      </select></label>)}
      {paths.length>0&&<button type="button" onClick={()=>{const next={...policy};delete next.supporting_paths;onChange(JSON.stringify(next));}}>Use historical evidence bindings</button>}
    </fieldset>;
  }
  if (typeof policy.kind!=="string" || !policy.kind.startsWith("conditional_")) return null;
  const trigger=policy.trigger as Condition|undefined;
  if (trigger && (typeof trigger!=="object" || typeof trigger.path!=="string" || !Array.isArray(trigger.true_values) || !Array.isArray(trigger.false_values) || [...trigger.true_values,...trigger.false_values].some(value=>typeof value!=="string"))) return <p role="alert">Correct the condition structure in the policy field below before using the editor.</p>;
  const save=(next:Condition)=>onChange(JSON.stringify({...policy,trigger:next}));
  return <fieldset className="panel"><legend>When this document is required</legend>
    <p>Choose explicit values that require or exclude the supporting document. Missing, ambiguous or unrecognized values fail the data check; they never silently exclude it.</p>
    {!trigger?<><p>This rule currently uses its historical applicability logic.</p><button type="button" onClick={()=>save(data?.[policy.kind as string]||{path:"",true_values:[],false_values:[]})}>Configure explicit requirement</button></>:<>
      <label>Source field<select value={trigger.path} onChange={event=>save({...trigger,path:event.target.value})}><option value="">Choose extracted field</option>{fields.filter(field=>field.type==="text"||field.type==="identifier").map(field=><option key={field.path} value={field.path}>{field.document} · {field.label}</option>)}</select></label>
      <label>Supporting document is required for these values<textarea value={trigger.true_values.join("\n")} onChange={event=>save({...trigger,true_values:event.target.value.split("\n")})}/><small>One exact choice per line. Case and repeated spaces are ignored.</small></label>
      <label>Supporting document is unnecessary for these values<textarea value={trigger.false_values.join("\n")} onChange={event=>save({...trigger,false_values:event.target.value.split("\n")})}/></label>
    </>}
  </fieldset>;
}
