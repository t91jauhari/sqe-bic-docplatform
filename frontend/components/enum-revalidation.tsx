"use client";
import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { Modal } from "@/components/ui";
import { api } from "@/lib/api";
import { usePlatform } from "@/components/platform-provider";

export function EnumRevalidation({ caseId, refresh }: { caseId: string; refresh: () => Promise<unknown> }) {
  const [open, setOpen] = useState(false), [reason, setReason] = useState(""), [busy, setBusy] = useState(false);
  const { notify } = usePlatform();
  return <>
    <button className="secondary" onClick={() => setOpen(true)} title="Provider tool: re-applies approved eKTP spelling aliases to saved values"><RotateCcw size={16} />Re-run alias validation (provider tool)</button>
    {open && <Modal title="Apply approved eKTP spelling aliases" onClose={() => { if (!busy) setOpen(false); }}>
      <p>Use the latest approved aliases to revalidate saved eKTP values. Raw evidence and extraction prompts stay unchanged. This does not submit another extraction job.</p>
      <label>Reason<textarea value={reason} onChange={e => setReason(e.target.value)} maxLength={1000} /></label>
      <button className="primary" disabled={busy || reason.trim().length < 5} onClick={async () => {
        setBusy(true);
        try {
          await api(`/cases/${caseId}/revalidate-enum-aliases`, { method: "POST", body: JSON.stringify({ reason: reason.trim() }) });
          notify("eKTP revalidation queued"); setOpen(false); await refresh();
        } catch (e) { notify(e instanceof Error ? e.message : "Revalidation failed", "error"); }
        finally { setBusy(false); }
      }}>{busy ? "Queuing…" : "Apply aliases and revalidate"}</button>
    </Modal>}
  </>;
}
