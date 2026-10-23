"use client";
import {useEffect, useState} from "react";
import {api} from "@/lib/api";
import type {Configuration} from "@/lib/types";

type Rule=NonNullable<Configuration["generic_sop_rules"]>[number];
type Policy=Rule["policy"];
type Option={path:string;schema_path:string;label:string;profile_label:string;checks?:string[]};
type Options={fields:Option[];visual_fields:Option[];amount_fields:Option[];context_options:Record<string,string[]>};
const empty:Policy={type:"visual",check:"presence",left:"",right:""};

function Editor({policy,options,change}:{policy:Policy;options:Options;change:(p:Policy)=>void}){
 const unary=policy.type==="visual"&&policy.check!=="consistency";
 const choices=policy.type==="visual"?options.visual_fields.filter(v=>v.checks?.includes(policy.check||"presence")):policy.type==="money"?options.amount_fields:options.fields;
 function select(key:"left"|"right"|"left_currency"|"right_currency",value:string){
  change({...policy,[key]:value,...(key==="left"&&unary?{right:value}:{})});
 }
 const field=(key:"left"|"right"|"left_currency"|"right_currency",label:string,list:Option[])=><label key={key}>{label}<select value={policy[key]||""} onChange={e=>select(key,e.target.value)}>
  <option value="">Choose a field</option>{policy[key]&&!list.some(v=>v.path===policy[key])&&<option value={policy[key]}>Current binding: {policy[key]}</option>}
  {list.map(v=><option key={v.path} value={v.path}>{v.profile_label} · {v.label}</option>)}</select></label>;
 return <div className="form-grid">
  {policy.type==="visual"&&<label>Visual check<select value={policy.check} onChange={e=>change({type:"visual",check:e.target.value as Policy["check"],left:"",right:""})}>
   <option value="presence">Region presence and completeness</option><option value="consistency">Compare two signing regions</option><option value="placement">Stamp in signer region</option><option value="all_pages">Marks on every page</option></select></label>}
  {policy.type==="date"&&<label>Date requirement<select value={policy.relation||"equal"} onChange={e=>change({...policy,relation:e.target.value as Policy["relation"]})}><option value="equal">Dates must match</option><option value="on_or_after">First date is on or after second</option></select></label>}
  {field("left",unary?"Source region":"First field",choices)}{!unary&&field("right","Compared field",choices)}
  {policy.type==="visual"&&policy.check==="all_pages"&&<><label>Expected page count (optional)<input type="number" min={1} max={1000} value={policy.expected_pages??""} onChange={e=>change({...policy,expected_pages:e.target.value?Number(e.target.value):null})}/></label><label className="checkbox-line"><input type="checkbox" checked={policy.exclude_final_page??false} onChange={e=>change({...policy,exclude_final_page:e.target.checked})}/><span>Exclude the final page from paraf checks</span></label></>}
  {policy.type==="money"&&<>{field("left_currency","First currency",options.fields)}{field("right_currency","Compared currency",options.fields)}
   <label>Decimal separator<select value={policy.decimal_separator||"."} onChange={e=>change({...policy,decimal_separator:e.target.value as "."|","})}><option value=".">Dot</option><option value=",">Comma</option></select></label>
   <label>Thousands separator<select value={policy.thousands_separator||""} onChange={e=>change({...policy,thousands_separator:(e.target.value||null) as Policy["thousands_separator"]})}><option value="">None</option><option value=".">Dot</option><option value=",">Comma</option><option value=" ">Space</option></select></label></>}
 </div>;
}

export function PolicyRules({configuration,version,family,editable,onApply}:{configuration:Configuration;version:number;family:string;editable:boolean;onApply:(c:Configuration)=>void}){
 const [options,setOptions]=useState<Options|null>(null),[error,setError]=useState("");
 const [id,setId]=useState(""),[label,setLabel]=useState(""),[policy,setPolicy]=useState<Policy>(empty);
 useEffect(()=>{let live=true;setOptions(null);if(!editable)return;api<Options>("/config/upgrades/comparisons/fields",{method:"POST",body:JSON.stringify({expected_version:version,family,payload:configuration})})
  .then(v=>{if(live)setOptions(v)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[configuration.profiles,configuration.document_families,configuration.context_definitions,version,family,editable]);
 const rules=(configuration.generic_sop_rules||[]).filter(r=>r.families.includes(family)&&r.policy.type&&r.policy.type!=="compare");
 function bind(p:Policy){const all=[...(options?.fields||[]),...(options?.visual_fields||[]),...(options?.amount_fields||[])];return Object.fromEntries([p.left,p.right,p.left_currency,p.right_currency].filter((v):v is string=>!!v).map(path=>[path,all.find(v=>v.path===path)?.schema_path||path]));}
 function change(rule:Rule,patch:Partial<Rule>){onApply({...configuration,generic_sop_rules:configuration.generic_sop_rules!.map(r=>r.id===rule.id?{...r,...patch}:r)});}
 function add(){
  if(!/^[A-Za-z0-9_.-]{1,100}$/.test(id)||[...(configuration.sop_rules||[]),...(configuration.generic_sop_rules||[])].some(r=>r.id===id)){setError("Enter a unique rule ID using letters, digits, dots, underscores or hyphens.");return;}
  if(!label.trim()||!policy.left||!policy.right||(policy.type==="money"&&(!policy.left_currency||!policy.right_currency))){setError("Enter a description and choose every required field.");return;}
  const rule:Rule={id,label:label.trim(),families:[family],enabled:true,report_category:policy.type==="visual"?"CUSTOMER_SIGNATURE":"DATA_COMPLETION",source_ref:"Configured SOP rule",policy,schema_paths:bind(policy)};
  onApply({...configuration,generic_sop_rules:[...(configuration.generic_sop_rules||[]),rule],
   ...(configuration.rule_order?{rule_order:[...configuration.rule_order,id]}:{}),
   ...(configuration.rule_scope?{rule_scope:{family_rule_ids:{...configuration.rule_scope.family_rule_ids,[family]:[...(configuration.rule_scope.family_rule_ids[family]||[]),id]}}}: {})});
  setId("");setLabel("");setPolicy(empty);setError("");
 }
 if(!editable)return null;
 return <section className="panel settings-card"><h2>Visual, date and amount checks</h2><p>Choose source fields from this family. Data checks pass or fail. Visual consistency requires an audited review of both regions; presence alone cannot prove a signature match.</p>
  {error&&<p role="alert">{error}</p>}
  <details><summary>Add a configured check</summary><label>Rule ID<input value={id} onChange={e=>setId(e.target.value)}/></label><label>What must be verified?<input value={label} onChange={e=>setLabel(e.target.value)}/></label>
   <label>Check type<select value={policy.type} onChange={e=>setPolicy({type:e.target.value as Policy["type"],left:"",right:"",...(e.target.value==="visual"?{check:"presence" as const}:{})})}><option value="visual">Visual evidence</option><option value="date">Date comparison</option><option value="money">Amount and currency comparison</option></select></label>
   {options?<Editor policy={policy} options={options} change={setPolicy}/>:<p>Loading available fields…</p>}
   <button type="button" disabled={!options} onClick={add}>Add check to draft</button><small>Choose this rule in the transaction flow, then test and publish the configuration.</small>
  </details>
  {rules.map(rule=><fieldset key={rule.id}><legend>{rule.label}</legend><label>Description<input value={rule.label} onChange={e=>change(rule,{label:e.target.value})}/></label>
   {options&&<Editor policy={rule.policy} options={options} change={p=>change(rule,{policy:p,schema_paths:bind(p)})}/>}
   <label>Report category<select value={rule.report_category} onChange={e=>change(rule,{report_category:e.target.value})}>{["DATA_COMPLETION","CUSTOMER_SIGNATURE","DOCUMENT_COMPLETION","OFFICER_REVIEW_APPROVAL"].map(v=><option key={v} value={v}>{v.replaceAll("_"," ")}</option>)}</select></label>
   <label>When to run<select value={rule.applicability?.context_key||""} onChange={e=>change(rule,{applicability:e.target.value?{context_key:e.target.value,equals:options?.context_options[e.target.value]?.find(v=>v!=="UNKNOWN")||""}:null})}><option value="">Always</option>{Object.keys(options?.context_options||{}).map(key=><option key={key} value={key}>When {key.replaceAll("_"," ")} matches</option>)}</select></label>
   {rule.applicability&&<label>Required context value<select value={rule.applicability.equals} onChange={e=>change(rule,{applicability:{...rule.applicability!,equals:e.target.value}})}>{(options?.context_options[rule.applicability.context_key]||[]).filter(v=>v!=="UNKNOWN").map(v=><option key={v}>{v}</option>)}</select></label>}
   <label><input type="checkbox" checked={rule.enabled!==false} onChange={e=>change(rule,{enabled:e.target.checked})}/> Check enabled</label>
  </fieldset>)}
 </section>;
}
