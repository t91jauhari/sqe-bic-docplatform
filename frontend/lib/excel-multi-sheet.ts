import type { Document } from "@/lib/types";

// resolveRow lets the caller control label mapping and value formatting
// (e.g. unrecognized-enum placeholders), keeping this utility decoupled
// from validation/business logic. Returns [label, value].
export type ResolveRow = (
  doc: Document,
  field: string,
  value: unknown,
) => [string, string];

function escapeXml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

// Guard against formula injection: prefix values that start with = + - @
// (after optional leading whitespace) with a single quote. Mirrors the
// safe() helper in extraction-export.ts so exports stay consistent.
function safe(value: string): string {
  return /^[\s]*[=+\-@]/.test(value) ? "'" + value : value;
}

// Excel worksheet names: max 31 chars, cannot contain \ / ? * [ ] :
function sanitizeSheetName(name: string): string {
  const cleaned = name.replaceAll(/[\\/?*\[\]:]/g, " ").trim();
  const trimmed =
    cleaned.length > 31 ? cleaned.slice(0, 31).trimEnd() : cleaned;
  return trimmed || "Sheet";
}

// Excel requires unique worksheet names; append a numeric suffix on collision
// while keeping the total length within the 31-char limit.
function uniqueSheetNames(names: string[]): string[] {
  const used = new Set<string>();
  return names.map((name) => {
    let candidate = name;
    let suffix = 2;
    while (used.has(candidate)) {
      const tag = ` (${suffix})`;
      const base = name.slice(0, 31 - tag.length);
      candidate = `${base}${tag}`;
      suffix++;
    }
    used.add(candidate);
    return candidate;
  });
}

function buildWorksheet(
  doc: Document,
  sheetName: string,
  resolveRow: ResolveRow,
): string {
  const entries = Object.entries(doc.normalized).filter(
    ([field]) => field !== "page_results",
  );
  const header =
    '<Row ss:StyleID="Header">' +
    '<Cell><Data ss:Type="String">Field</Data></Cell>' +
    '<Cell><Data ss:Type="String">Value</Data></Cell>' +
    "</Row>";
  const rows = entries
    .map(([field, value]) => {
      const [label, text] = resolveRow(doc, field, value);
      const labelXml = escapeXml(safe(label));
      const valueXml = escapeXml(safe(text));
      return (
        "<Row>" +
        `<Cell><Data ss:Type="String">${labelXml}</Data></Cell>` +
        `<Cell><Data ss:Type="String">${valueXml}</Data></Cell>` +
        "</Row>"
      );
    })
    .join("");
  return (
    `<Worksheet ss:Name="${escapeXml(sheetName)}">` +
    "<Table>" +
    '<Column ss:Width="200"/><Column ss:Width="300"/>' +
    header +
    rows +
    "</Table>" +
    "</Worksheet>"
  );
}

export function buildMultiSheetExcelXml(
  documents: Document[],
  resolveRow: ResolveRow,
): string {
  const sheetNames = uniqueSheetNames(
    documents.map((d) => sanitizeSheetName(d.filename)),
  );
  const worksheets = documents
    .map((doc, i) => buildWorksheet(doc, sheetNames[i], resolveRow))
    .join("");
  return (
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<?mso-application progid="Excel.Sheet"?>\n' +
    '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"' +
    ' xmlns:o="urn:schemas-microsoft-com:office:office"' +
    ' xmlns:x="urn:schemas-microsoft-com:office:excel"' +
    ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"' +
    ' xmlns:html="http://www.w3.org/TR/REC-html40">' +
    "<Styles>" +
    '<Style ss:ID="Header"><Font ss:Bold="1"/></Style>' +
    "</Styles>" +
    worksheets +
    "</Workbook>"
  );
}

export function downloadMultiSheetExcel(
  documents: Document[],
  resolveRow: ResolveRow,
  filename: string,
): void {
  const xml = buildMultiSheetExcelXml(documents, resolveRow);
  const blob = new Blob([xml], { type: "application/vnd.ms-excel" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
