"use client";
import {DatasetPolicyEditor} from "./dataset-policy";
import {ScoreGroups} from "./score-groups";
import {ReportBindings} from "./report-bindings";
import {DatasetSelect} from "./dataset-select";
import {useState} from "react";
import {Plus, Layers, ArrowRight} from "lucide-react";
import {Modal} from "./ui";
import {familyCatalog, familyProfiles} from "@/lib/document-family";
import type {Configuration, DocumentFamilyConfig, ProfileName} from "@/lib/types";

type Props={draft:Configuration;update:(c:Configuration)=>void;family:string;select:(id:string)=>void;editable:boolean;navigate:(tab:"flows"|"profiles"|"rules")=>void};
export function DocumentFamilies({draft,update,family,select,editable,navigate}:Props){
 const catalog=familyCatalog(draft),f=catalog[family];
 const [open,setOpen]=useState(false),[name,setName]=useState(""),[id,setId]=useState(""),[source,setSource]=useState("forex"),[error,setError]=useState(""),[query,setQuery]=useState("");
 const [section,setSection]=useState("overview");
 const patch=(v:Partial<DocumentFamilyConfig>)=>update({...draft,document_families:{...draft.document_families,[family]:{...f,...v}}});
 const flows=Object.entries(draft.templates).filter(([,flow])=>(flow.document_family||"forex")===family);
 const create=()=>{
  if(!/^[a-z][a-z0-9_-]{0,39}$/.test(id)||catalog[id]){setError("Choose a unique ID starting with a letter; use lowercase letters, digits, underscores or hyphens (up to 40).");return;}
  if(!name.trim()||name.trim().length>120||Object.values(catalog).some(v=>v.label.toLowerCase()===name.trim().toLowerCase())){setError("Enter a unique family name, up to 120 characters.");return;}
  const base=structuredClone(catalog[source]);
  const rules=base.sop_rule_ids ?? [...(draft.sop_rules||[]),...(draft.generic_sop_rules||[])].filter(r=>(r.source_ref||"").startsWith("AO:")===(source==="account_opening")).map(r=>r.id);
  update({...draft,document_families:{...draft.document_families,[id]:{...base,label:name.trim(),description:"",enabled:true,required:base.required||[],sop_rule_ids:rules}}});
  select(id);setSection("overview");setOpen(false);
 };
 return <section className="panel settings-card">
  <div className="section-head"><div><h2><Layers size={19}/> Document families</h2><p>A family groups document profiles, extraction guidance and review defaults. Save and publish when your setup is ready.</p></div>{editable&&<button className="primary" onClick={()=>{setName("");setId("");setError("");setSource(family);setOpen(true);}}><Plus size={16}/> Add document family</button>}</div>
  <div className="profile-workflow-tabs" aria-label="Family configuration sections">{[["overview","1 · Basics"],["documents","2 · Documents & extraction"],["review","3 · Checks & reports"]].map(([key,label])=><button key={key} className={section===key?"active":""} aria-pressed={section===key} onClick={()=>setSection(key)}>{label}</button>)}</div>
  <fieldset disabled={!editable}>
  {section==="overview"&&<div>
   <label className="checkbox-line"><input type="checkbox" checked={draft.family_catalog_mode==="explicit"} disabled={draft.family_catalog_mode==="explicit"&&!Object.values(familyProfiles).flat().every(key=>draft.profiles[key])} onChange={e=>update({...draft,family_catalog_mode:e.target.checked?"explicit":"legacy",document_families:structuredClone(catalog)})}/><span>Use exactly the families configured here<small>Starter families will no longer be added automatically. Existing cases keep their saved catalog. Restore starter profiles before returning to compatibility mode.</small></span></label>
   <h3>{f.label}</h3><small>Stable family ID: {family}. Existing cases keep their published configuration.</small>
   <label>Family name<input value={f.label} maxLength={120} onChange={e=>patch({label:e.target.value})}/></label>
   <label>What is this family used for?<textarea value={f.description||""} maxLength={2000} placeholder="For example: review the documents needed for loan applications" onChange={e=>patch({description:e.target.value})}/></label>
   <label className="checkbox-line"><input type="checkbox" checked={f.enabled!==false} onChange={e=>patch({enabled:e.target.checked})}/><span>Available for new cases<small>Turning this off prevents new uploads to this family's flows. Existing cases remain available.</small></span></label>
   <div className="template-card"><strong>{f.profiles.length} document profiles · {flows.length} transaction flows</strong><p>Use transaction flows to choose required documents for each service within this family.</p><button className="secondary" onClick={()=>navigate("flows")}>Configure transaction flows <ArrowRight size={15}/></button></div>
  </div>}
  {section==="documents"&&<div>
   <h3>Which documents belong to this family?</h3><p>Choose existing extraction profiles. A shared profile keeps the same schema and instructions across families.</p>
   <div className="field-catalogue">{Object.entries(draft.profiles).map(([key,p])=>{const used=Object.entries(catalog).filter(([other,v])=>other!==family&&v.profiles.includes(key as ProfileName));const requiredBy=flows.filter(([,flow])=>flow.required.includes(key as ProfileName));return <label className="checkbox-line" key={key}><input type="checkbox" checked={f.profiles.includes(key as ProfileName)} disabled={requiredBy.length>0} onChange={e=>patch({profiles:e.target.checked?[...f.profiles,key as ProfileName]:f.profiles.filter(x=>x!==key),required:(f.required||[]).filter(x=>x!==key)})}/><span>{p.label}<small>{requiredBy.length?"Required by a flow; change that flow before removing.":used.length?`Shared with ${used.map(([,v])=>v.label).join(", ")}`:"Available extraction profile"}</small></span></label>})}</div>
   {!f.profiles.length&&<p role="alert">Select at least one document profile before publishing.</p>}
   <h3>Default required documents for new flows</h3><p>These choices initialize new flows. Existing flows retain their own requirements.</p>{f.profiles.map(key=><label className="checkbox-label compact" key={key}><input type="checkbox" checked={(f.required||[]).includes(key)} onChange={e=>patch({required:e.target.checked?[...(f.required||[]),key]:(f.required||[]).filter(x=>x!==key)})}/>{draft.profiles[key].label}</label>)}
   <label>Family extraction guidance<textarea rows={5} maxLength={10000} value={f.extraction_guidance||""} placeholder="Reusable reading rules for every document in this family. Describe how to read; do not enter expected customer values." onChange={e=>patch({extraction_guidance:e.target.value})}/><small>Added to this family's model prompts for new uploads and field reruns using the latest profile. Shared profiles in other families keep their own guidance.</small></label>
   <details><summary>Page processing overrides</summary>{[["sequential_page_extraction","Extract each page separately"],["cross_page_reference","Allow cross-page references"]].map(([key,label])=><label key={key}>{label}<select value={f[key as keyof DocumentFamilyConfig]===undefined?"inherit":String(f[key as keyof DocumentFamilyConfig])} onChange={e=>patch({[key]:e.target.value==="inherit"?undefined:e.target.value==="true"})}><option value="inherit">Use processing defaults</option><option value="true">On</option><option value="false">Off</option></select></label>)}</details>
   <button className="secondary" onClick={()=>navigate("profiles")}>Edit profile fields & instructions <ArrowRight size={15}/></button>
  </div>}
  {section==="review"&&<div>
   <h3>SOP checks for new flows</h3><p>Select the checks offered for this family. New flows start with these checks; existing flows keep their selected checks.</p>
   <input aria-label="Find family SOP checks" placeholder="Search by rule name or ID" value={query} onChange={e=>setQuery(e.target.value)}/>
   <details><summary>{(f.sop_rule_ids||[]).length} checks selected · edit selection</summary><div style={{maxHeight:360,overflowY:"auto"}}>{[...(draft.sop_rules||[]),...(draft.generic_sop_rules||[])].filter(r=>`${r.id} ${r.label}`.toLowerCase().includes(query.toLowerCase())).map(r=><label className="checkbox-label compact" key={r.id}><input type="checkbox" checked={(f.sop_rule_ids||[]).includes(r.id)} onChange={e=>patch({sop_rule_ids:e.target.checked?[...(f.sop_rule_ids||[]),r.id]:(f.sop_rule_ids||[]).filter(x=>x!==r.id)})}/>{r.id} · {r.label}</label>)}</div></details>
   <button className="secondary" onClick={()=>navigate("rules")}>Create or edit SOP checks <ArrowRight size={15}/></button>
   <h3>Reference dataset & reports</h3><p>Defaults for new flows. Select a reference workbook only when it contains the relevant customer samples.</p>
   <label>Default reference dataset<DatasetSelect value={f.dataset_id===null?"":f.dataset_id||(family==="account_opening"?"account-opening-sample-v1":"forex-sample-v1")} onChange={value=>patch({dataset_id:value||null})}/></label>
   <label>Default report layout<select value={f.report_layout||(family==="account_opening"?"account_opening":"forex")} onChange={e=>patch({report_layout:e.target.value})}><option value="forex">Forex Kertas Kerja</option><option value="account_opening">Account Opening Kertas Kerja</option></select></label>
   <DatasetPolicyEditor configured={f.comparison_policy} onChange={value=>patch({comparison_policy:value})}/>
   <ScoreGroups configured={f.scoring_policy} layout={f.report_layout||"forex"} onChange={value=>patch({scoring_policy:value})}/>
   <ReportBindings configured={f.report_definition||draft.report_definitions?.[f.report_layout||(family==="account_opening"?"account_opening":"forex")]} onChange={value=>patch({report_definition:value})} layout={f.report_layout||(family==="account_opening"?"account_opening":"forex")}/>
   <details><summary>Default report headings</summary>{["region_name","category","activity","inspection_type","period"].map(key=><label key={key}>{({region_name:"Region",category:"Category",activity:"Activity",inspection_type:"Inspection type",period:"Period"} as Record<string,string>)[key]}<input value={f.report_context?.[key]||""} maxLength={500} onChange={e=>patch({report_context:{...f.report_context,[key]:e.target.value}})}/></label>)}</details>
  </div>}
  </fieldset>
  {open&&<Modal title="Add document family" onClose={()=>setOpen(false)}><p>Start with an existing family, then choose its documents, reading rules and review settings.</p><label>Family name<input value={name} maxLength={120} onChange={e=>{setName(e.target.value);setId(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g,"_").replace(/_$/,""));}} placeholder="For example: Loan Applications"/></label><label>Family ID<input value={id} maxLength={40} onChange={e=>setId(e.target.value)}/><small>A stable ID used by transaction flows.</small></label><label>Start from<select value={source} onChange={e=>setSource(e.target.value)}>{Object.entries(catalog).map(([key,v])=><option key={key} value={key}>{v.label}</option>)}</select></label>{error&&<p role="alert">{error}</p>}<div className="button-row"><button className="secondary" onClick={()=>setOpen(false)}>Cancel</button><button className="primary" onClick={create}>Create family draft</button></div></Modal>}
 </section>;
}
