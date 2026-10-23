"use client";
import {useState,useEffect} from "react";
import {useData,usePlatform} from "@/components/platform-provider";
import {api} from "@/lib/api";
export function CaseTask({caseId}:{caseId:string}) {
 const {data,refresh}=useData<{assigned_to:string|null;due_at:number|null;candidates:{id:string;name:string}[];can_edit:boolean}>(`/cases/${caseId}/assignment`);
 const {notify}=usePlatform();const [assigned,setAssigned]=useState(""),[due,setDue]=useState(""),[busy,setBusy]=useState(false);
 useEffect(()=>{if(data){setAssigned(data.assigned_to||"");if(data.due_at){const d=new Date(data.due_at*1000);setDue(new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16));}else setDue("");}},[data]);
 async function save(){setBusy(true);try{await api(`/cases/${caseId}/assignment`,{method:"PUT",body:JSON.stringify({assigned_to:assigned||null,due_at:due?new Date(due).getTime()/1000:null})});await refresh();notify("Case assignment saved.");}catch(e){notify(e instanceof Error?e.message:"Unable to assign","error");}finally{setBusy(false);}}
 return data?<section className="panel" style={{padding:20}}><h3>Case owner and deadline</h3><label>Assignee <select disabled={!data.can_edit} value={assigned} onChange={e=>setAssigned(e.target.value)}><option value="">Unassigned</option>{data.candidates.map(u=><option key={u.id} value={u.id}>{u.name}</option>)}</select></label><label>Due date <input disabled={!data.can_edit} type="datetime-local" value={due} onChange={e=>setDue(e.target.value)}/></label>{data.can_edit&&<button className="secondary" disabled={busy} onClick={save}>{busy?"Saving…":"Save assignment"}</button>}</section>:null;
}
