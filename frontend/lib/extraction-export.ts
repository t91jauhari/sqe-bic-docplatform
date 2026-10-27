import type { Document } from "@/lib/types";

export function extractionCheck(
  doc: Document,
  field: string,
  provider?: string,
): string {
  return provider === "spider-ai" ||
    doc.provider_state?.processing_provider === "spider-ai" ||
    doc.validation?.processing_mode === "spider_extraction_formatted"
    ? "OK"
    : doc.validation?.fields?.[field]?.status || "PENDING";
}

export function excelClipboard(rows: string[][]) {
  const escape = (value: string) =>
    value
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  // Both representations retain cell boundaries; HTML asks Excel to keep text IDs.
  const safe = (value: string) =>
    /^[\s]*[=+\-@]/.test(value) ? "'" + value : value;
  const tsvCell = (value: string) =>
    /[\t\r\n"]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
  return {
    text: rows
      .map((row) => row.map((value) => tsvCell(safe(value))).join("\t"))
      .join("\r\n"),
    html: `<html><body><table>${rows.map((row) => `<tr>${row.map((value) => `<td style='mso-number-format:"\\@"'>${escape(safe(value)).replace(/\r?\n/g, "<br>")}</td>`).join("")}</tr>`).join("")}</table></body></html>`,
  };
}

export async function copyExcel(rows: string[][]) {
  const payload = excelClipboard(rows);
  if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
    try {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/plain": new Blob([payload.text], { type: "text/plain" }),
          "text/html": new Blob([payload.html], { type: "text/html" }),
        }),
      ]);
      return;
    } catch {
      /* Fall back for browsers/origins without rich clipboard permission. */
    }
  }
  const active = document.activeElement as HTMLElement | null;
  const node = document.createElement("textarea");
  node.value = payload.text;
  node.style.position = "fixed";
  node.style.opacity = "0";
  document.body.appendChild(node);
  const handler = (event: ClipboardEvent) => {
    if (!event.clipboardData) return;
    event.clipboardData.setData("text/plain", payload.text);
    event.clipboardData.setData("text/html", payload.html);
    event.preventDefault();
  };
  try {
    node.focus();
    node.select();
    document.addEventListener("copy", handler);
    if (!document.execCommand("copy"))
      throw new Error(
        "Clipboard access was blocked. Allow clipboard access and try again.",
      );
  } finally {
    document.removeEventListener("copy", handler);
    node.remove();
    active?.focus();
  }
}
