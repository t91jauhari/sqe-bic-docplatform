"use client";
import { useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { useData, usePlatform } from "./platform-provider";
import { ErrorNotice } from "./ui";

type Request = {id:string;status:string;fields:string[];config_version:number;error?:string;retry_explanation?:string;can_retry?:boolean;requires_duplicate_charge_ack?:boolean};
export function FieldRequestRecovery({documentId,onQueued}:{documentId:string;onQueued:()=>void}) {
 const {online}=usePlatform();
 const {data:history,error,refresh}=useData<Request[]>(`/documents/${documentId}/reprocess-fields`);
 const [busy,setBusy]=useState(false),[accepted,setAccepted]=useState(false),[message,setMessage]=useState("");
 const submitting=useRef(false);
 const failed=history?.find(r=>r.status==="ERROR"&&r.can_retry!==false);
 const active=history?.some(r=>!["COMPLETED","ERROR","CANCELLED"].includes(r.status));
 if(error)return <ErrorNotice message={`Field recovery history is unavailable. ${error}`} retry={()=>void refresh()}/>;
 if(!failed)return null;
 const uncertain=failed.requires_duplicate_charge_ack!==false;
 return <section aria-label="Failed field extraction recovery" className="info-note">
  <strong>Retry the failed field extraction</strong>
  <p>{failed.retry_explanation||failed.error||"The field reread failed. Your saved extraction is preserved."}</p>
  <p>Resumes {failed.fields.length} selected fields with the saved configuration v{failed.config_version}.</p>
  {uncertain&&<label className="checkbox-line"><input type="checkbox" checked={accepted} disabled={busy||!online} onChange={e=>setAccepted(e.target.checked)}/><span>Allow a possible duplicate provider charge for this uncertain field submission</span></label>}
  <button className="primary" disabled={busy||!!active||!online||(uncertain&&!accepted)} onClick={async()=>{
   if(submitting.current)return;submitting.current=true;setBusy(true);setMessage("");
   try{
    await api(`/documents/${documentId}/reprocess-fields/${failed.id}/retry`,{method:"POST",body:JSON.stringify({accept_possible_duplicate_charge:uncertain&&accepted})});
    await refresh();onQueued();
   }catch(e){setMessage(e instanceof Error?e.message:"Unable to retry the field request.");}
   finally{submitting.current=false;setBusy(false);}
  }}><RefreshCw size={15}/>{busy?"Submitting…":"Retry field extraction"}</button>
  {!online&&<p>Reconnect to retry this request.</p>}
  {message&&<p role="alert">{message}</p>}
 </section>;
}
