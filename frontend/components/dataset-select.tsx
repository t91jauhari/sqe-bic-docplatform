"use client";
import { useData } from "@/components/platform-provider";

type Reference = {id: string; source_name: string};
export function DatasetSelect({value, onChange}: {value: string; onChange: (value: string) => void}) {
  const {data, error} = useData<Reference[]>("/reference-datasets", 0);
  const missing = value && data && !data.some(item => item.id === value);
  return <><select value={value} onChange={event => onChange(event.target.value)} disabled={!data}>
    <option value="">No reference dataset</option>
    {!data && value && <option value={value}>{value}</option>}
    {missing && <option value={value}>{value} — unavailable</option>}
    {data?.map(item => <option key={item.id} value={item.id}>{item.source_name}</option>)}
  </select>{error && <small role="alert">Unable to load reference datasets. Reload before changing this setting.</small>}
  {missing && <small role="alert">This reference is unavailable. Import it or choose a registered dataset before publishing.</small>}</>;
}
