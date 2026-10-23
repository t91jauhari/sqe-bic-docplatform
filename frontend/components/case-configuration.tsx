"use client";
import {useState} from "react";
import {useData,usePlatform} from "./platform-provider";
import {api} from "@/lib/api";
import type {ConfigResponse} from "@/lib/types";

export function CaseConfiguration({caseId,currentVersion,refresh}:{caseId:string;currentVersion:number;refresh:()=>Promise<unknown>}){
 const {data:latest}=useData<ConfigResponse>("/config",0);
 const {notify}=usePlatform();const [reason,setReason]=useState("");const [busy,setBusy]=useState(false);
 if(!latest||latest.version<=currentVersion)return null;
 return <section className="panel"><h3>Apply published rules to this case</h3>
  <p>This case uses version {currentVersion}. Published version {latest.version} is available. Applying it reruns SOP checks using saved extraction. Previous reports remain available in the audit history.</p>
  <label>Reason for applying version {latest.version}<textarea value={reason} maxLength={1000} disabled={busy} onChange={e=>setReason(e.target.value)}/></label>
  <button disabled={busy||reason.trim().length<10} onClick={async()=>{setBusy(true);try{await api(`/cases/${caseId}/configuration`,{method:"POST",body:JSON.stringify({expected_version:currentVersion,target_version:latest.version,reason:reason.trim()})});notify("Published rules applied; SOP checks queued");setReason("");await refresh();}catch(e){notify(e instanceof Error?e.message:"Unable to apply rules","error");}finally{setBusy(false);}}}>{busy?"Applying…":`Apply version ${latest.version} and rerun SOP checks`}</button>
 </section>;
}
