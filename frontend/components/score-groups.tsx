"use client";
import {useData} from "./platform-provider";
type Groups={total_a:string[];total_b:string[]};

export function ScoreGroups({configured,layout,onChange}:{configured?:Groups;layout:string;onChange:(value:Groups|undefined)=>void}){
 const {data,error}=useData<{score_groups:Record<string,Groups>}>("/config/catalog",0);
 const current=configured||data?.score_groups?.[layout];
 if(!current)return <p role={error?"alert":"status"}>{error?"Unable to load score groups.":"Loading score groups…"}</p>;
 const categories=[...current.total_a,...current.total_b];
 return <details><summary>Report score groups</summary><p>Assign each category to Total A or Total B. Every applicable SOP still earns one point for PASS and zero for FAIL; pending visual reviews remain in possible points.</p>
  {categories.map(category=><label key={category}>{category.replaceAll("_"," ")}<select value={current.total_a.includes(category)?"total_a":"total_b"} onChange={e=>{
   const group=e.target.value as keyof Groups;
   const next:Groups={total_a:current.total_a.filter(v=>v!==category),total_b:current.total_b.filter(v=>v!==category)};
   next[group].push(category);onChange(next);
  }}><option value="total_a">Total A</option><option value="total_b">Total B</option></select></label>)}
  {configured&&<button type="button" className="secondary" onClick={()=>onChange(undefined)}>Use report-layout defaults</button>}
 </details>;
}
