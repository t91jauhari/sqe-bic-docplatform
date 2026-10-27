"use client";
import { useState } from "react";
import { Copy } from "lucide-react";
import type { Document } from "@/lib/types";
import { copyExcel, extractionCheck } from "@/lib/extraction-export";
import { display } from "@/components/ui";
import { usePlatform } from "@/components/platform-provider";

export function CopyExtraction({
  doc,
  columns,
  provider,
}: {
  doc: Document;
  columns?: [string, string][];
  provider?: string;
}) {
  const [busy, setBusy] = useState(false);
  const { notify } = usePlatform();
  const entries = Object.entries(doc.normalized || {}).filter(
    ([field]) => field !== "page_results",
  );
  if (doc.status !== "COMPLETED" || !entries.length) return null;
  return (
    <button
      className="secondary"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          const rows = entries.map(([field, value]) => [
            columns?.find(([key]) => key === field)?.[1] || field,
            value == null &&
            doc.validation?.fields?.[field]?.issues?.some((issue) =>
              ["UNRECOGNIZED_ENUM", "INVALID_OR_MISSING_ENUM"].includes(
                issue.code,
              ),
            )
              ? "Unrecognized value · needs review"
              : display(value),
            extractionCheck(doc, field, provider),
          ]);
          await copyExcel([["Field", "Value", "CHECK"], ...rows]);
          notify(
            `Copied ${entries.length} fields from ${doc.filename}. Paste into Excel with Ctrl+V.`,
          );
        } catch (error) {
          notify(
            error instanceof Error
              ? error.message
              : "Unable to copy extraction",
            "error",
          );
        } finally {
          setBusy(false);
        }
      }}
    >
      <Copy size={15} />
      {busy ? "Copying…" : "Copy to Excel"}
    </button>
  );
}
