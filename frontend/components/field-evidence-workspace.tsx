"use client";
import { useEffect, useMemo, useState } from "react";
import {
  ExternalLink,
  Eye,
  Image as ImageIcon,
  Layers,
  Maximize2,
  Minimize2,
  Pencil,
  RefreshCw,
  Sparkles,
  ZoomIn,
  ZoomOut,
  ChevronUp,
  ChevronDown,
} from "lucide-react";
import { Badge, display } from "@/components/ui";
import { VisualRegionEditor } from "@/components/visual-region-editor";
import { extractionCheck } from "@/lib/extraction-export";
import type { Configuration, Document, FieldResult } from "@/lib/types";

type CropItem = {
  kind: "field" | "visual";
  sourceField: string;
  pageNumber?: number;
  revision: string;
  storageKey?: string;
  url?: string;
  available: boolean;
  observedPresent?: boolean | null;
  reviewStatus?: string;
  error?: string;
};

type UnifiedFieldRow = {
  field: string;
  label: string;
  value: unknown;
  isVisualOnly: boolean;
  result?: FieldResult;
  checkStatus: string;
  hasApprovedAlias: boolean;
  crops: CropItem[];
  errors: string[];
  needsAttention: boolean;
  isVisual: boolean;
};

function buildCropUrl(
  docId: string,
  revision: string,
  storageKey?: string,
): string | undefined {
  if (!storageKey || !revision) return undefined;
  const filename = storageKey.split("/").pop();
  if (!filename || filename.length <= revision.length + 5) return undefined;
  const token = filename.slice(revision.length + 1, -4);
  if (!token) return undefined;
  return `/api/documents/${docId}/evidence/${revision}/${token}`;
}

function baseFieldKey(path: string): string {
  return path.split(".")[0] || path;
}

function formatFieldKeyLabel(key: string): string {
  return key
    .replaceAll(".", " · ")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function FieldEvidenceWorkspace({
  doc,
  columns,
  provider,
  canWrite,
  canReview,
  pending,
  onRefreshCrops,
  onCorrectField,
  onRegionSaved,
}: {
  doc: Document;
  columns?: [string, string][];
  provider?: Configuration["provider"];
  canWrite: boolean;
  canReview: boolean;
  pending: boolean;
  onRefreshCrops: () => void;
  onCorrectField: (field: string) => void;
  onRegionSaved: () => void;
}) {
  const [filter, setFilter] = useState<
    "all" | "with_crops" | "attention" | "visual"
  >("all");
  const [selectedField, setSelectedField] = useState<string>("");
  const [showInspector, setShowInspector] = useState<boolean>(true);
  const [inspectorZoom, setInspectorZoom] = useState<number>(100);

  const rows = useMemo<UnifiedFieldRow[]>(() => {
    const labelMap = new Map<string, string>(columns || []);
    const normalizedEntries = Object.entries(doc.normalized || {}).filter(
      ([field]) => field !== "page_results",
    );
    const knownFields = new Set(normalizedEntries.map(([f]) => f));

    const fieldEvidenceList = doc.validation?.field_evidence || [];
    const visualEvidenceList = doc.validation?.visual_evidence || [];

    // Group field_evidence and visual_evidence by their target row key
    const cropsByField = new Map<string, CropItem[]>();
    const errorsByField = new Map<string, string[]>();
    const extraVisualFields = new Set<string>();

    const resolveTargetField = (rawField: string): string => {
      if (knownFields.has(rawField)) return rawField;
      const root = baseFieldKey(rawField);
      if (knownFields.has(root)) return root;
      return root;
    };

    for (const fe of fieldEvidenceList) {
      if (
        fe.field.endsWith(".complete") ||
        fe.field.endsWith(".options_complete")
      ) {
        continue;
      }
      const target = resolveTargetField(fe.field);
      if (!knownFields.has(target)) {
        extraVisualFields.add(target);
      }
      const list = cropsByField.get(target) || [];
      for (const c of fe.crops || []) {
        const url = buildCropUrl(doc.id, c.revision, c.storage_key);
        if (url && !list.some((existing) => existing.url === url)) {
          list.push({
            kind: "field",
            sourceField: fe.field,
            pageNumber: c.page_number,
            revision: c.revision,
            storageKey: c.storage_key,
            url,
            available: true,
            reviewStatus: fe.review_status,
          });
        }
      }
      cropsByField.set(target, list);
      if (fe.error) {
        const errs = errorsByField.get(target) || [];
        if (!errs.includes(fe.error)) errs.push(fe.error);
        errorsByField.set(target, errs);
      }
    }

    for (const ve of visualEvidenceList) {
      const target = resolveTargetField(ve.field);
      if (!knownFields.has(target)) {
        extraVisualFields.add(target);
      }
      const list = cropsByField.get(target) || [];
      const url = ve.available
        ? buildCropUrl(doc.id, ve.revision, ve.storage_key)
        : undefined;
      list.push({
        kind: "visual",
        sourceField: ve.field,
        pageNumber: ve.page_number,
        revision: ve.revision,
        storageKey: ve.storage_key,
        url,
        available: !!(ve.available && url),
        observedPresent: ve.observed_present,
        reviewStatus: ve.review_status,
        error: ve.error,
      });
      cropsByField.set(target, list);
      if (ve.error) {
        const errs = errorsByField.get(target) || [];
        if (!errs.includes(ve.error)) errs.push(ve.error);
        errorsByField.set(target, errs);
      }
    }

    const buildRow = (
      field: string,
      value: unknown,
      isVisualOnly: boolean,
    ): UnifiedFieldRow => {
      const result = doc.validation?.fields?.[field];
      const label = labelMap.get(field) || formatFieldKeyLabel(field);
      const crops = cropsByField.get(field) || [];
      const errors = errorsByField.get(field) || [];
      const checkStatus = isVisualOnly
        ? crops.some((c) => c.observedPresent === false)
          ? "REVIEW"
          : crops.some((c) => c.observedPresent === true)
            ? "VALID"
            : "PENDING"
        : extractionCheck(doc, field, provider) === "OK"
          ? "OK"
          : result?.status || "PENDING";

      const hasApprovedAlias = !!doc.validation?.corrections?.some(
        (c) =>
          typeof c === "object" &&
          c !== null &&
          (c as { field?: string; method?: string }).field === field &&
          (c as { method?: string }).method === "approved_enum_alias",
      );

      const isVisual =
        isVisualOnly ||
        crops.some((c) => c.kind === "visual") ||
        /signature|stamp|paraf|initial|photo|meterai|approval/i.test(field);

      const needsAttention =
        Boolean(result?.issues?.length) ||
        ["INVALID", "FAIL", "REVIEW", "ERROR"].includes(checkStatus) ||
        errors.length > 0 ||
        crops.some((c) => c.kind === "visual" && c.observedPresent === false);

      return {
        field,
        label,
        value,
        isVisualOnly,
        result,
        checkStatus,
        hasApprovedAlias,
        crops,
        errors,
        needsAttention,
        isVisual,
      };
    };

    const allRows: UnifiedFieldRow[] = normalizedEntries.map(([field, value]) =>
      buildRow(field, value, false),
    );

    for (const extraField of extraVisualFields) {
      const extraCrops = cropsByField.get(extraField) || [];
      const observedSummary = extraCrops
        .filter((c) => c.kind === "visual")
        .map((c) =>
          c.observedPresent === true
            ? "Present"
            : c.observedPresent === false
              ? "Absent"
              : "Uncertain",
        );
      allRows.push(
        buildRow(
          extraField,
          observedSummary.length ? observedSummary.join(", ") : null,
          true,
        ),
      );
    }

    return allRows;
  }, [columns, doc, provider]);

  const counts = useMemo(() => {
    return {
      all: rows.length,
      with_crops: rows.filter((r) => r.crops.some((c) => c.url)).length,
      attention: rows.filter((r) => r.needsAttention).length,
      visual: rows.filter((r) => r.isVisual).length,
    };
  }, [rows]);

  const filteredRows = useMemo(() => {
    if (filter === "with_crops") {
      return rows.filter((r) => r.crops.some((c) => c.url));
    }
    if (filter === "attention") {
      return rows.filter((r) => r.needsAttention);
    }
    if (filter === "visual") {
      return rows.filter((r) => r.isVisual);
    }
    return rows;
  }, [filter, rows]);

  // Keep selectedField valid when switching documents or filters
  useEffect(() => {
    if (!rows.length) {
      setSelectedField("");
      return;
    }
    if (selectedField && rows.some((r) => r.field === selectedField)) {
      return;
    }
    const firstWithCropOrIssue =
      rows.find((r) => r.needsAttention && r.crops.some((c) => c.url)) ||
      rows.find((r) => r.crops.some((c) => c.url)) ||
      rows.find((r) => r.needsAttention) ||
      rows[0];
    setSelectedField(firstWithCropOrIssue?.field || "");
  }, [doc.id, rows, selectedField]);

  const activeRow =
    rows.find((r) => r.field === selectedField) ||
    filteredRows[0] ||
    rows[0] ||
    null;

  const activeIndex = activeRow
    ? filteredRows.findIndex((r) => r.field === activeRow.field)
    : -1;

  const stepSelection = (delta: number) => {
    if (!filteredRows.length) return;
    const nextIndex = Math.max(
      0,
      Math.min(
        filteredRows.length - 1,
        (activeIndex >= 0 ? activeIndex : 0) + delta,
      ),
    );
    setSelectedField(filteredRows[nextIndex].field);
  };

  return (
    <div className="field-evidence-workspace">
      <div className="field-evidence-toolbar">
        <div className="field-filter-pills" role="tablist" aria-label="Filter extracted fields">
          <button
            type="button"
            className={filter === "all" ? "active" : ""}
            onClick={() => setFilter("all")}
          >
            All fields <span>{counts.all}</span>
          </button>
          <button
            type="button"
            className={filter === "with_crops" ? "active" : ""}
            onClick={() => setFilter("with_crops")}
          >
            <ImageIcon size={13} />
            With crops <span>{counts.with_crops}</span>
          </button>
          <button
            type="button"
            className={filter === "visual" ? "active" : ""}
            onClick={() => setFilter("visual")}
          >
            <Sparkles size={13} />
            Visual & signatures <span>{counts.visual}</span>
          </button>
          <button
            type="button"
            className={filter === "attention" ? "active" : ""}
            onClick={() => setFilter("attention")}
          >
            Needs attention <span>{counts.attention}</span>
          </button>
        </div>
        <div className="field-toolbar-actions">
          {canWrite && doc.status === "COMPLETED" && (
            <button
              type="button"
              className="secondary compact-btn"
              disabled={pending}
              onClick={onRefreshCrops}
              title="Regenerate or refresh field & visual evidence crops from saved coordinates"
            >
              <RefreshCw size={14} />
              Refresh field crops
            </button>
          )}
          <button
            type="button"
            className="secondary compact-btn"
            onClick={() => setShowInspector((v) => !v)}
            title={
              showInspector
                ? "Hide side-by-side detail inspector"
                : "Show side-by-side detail inspector"
            }
          >
            {showInspector ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            {showInspector ? "Hide inspector" : "Show inspector"}
          </button>
        </div>
      </div>

      <div
        className={
          "field-evidence-split " + (showInspector ? "with-inspector" : "full")
        }
      >
        <div className="table-scroll fields-table side-by-side-table">
          <table>
            <thead>
              <tr>
                <th>Field</th>
                <th>Effective value</th>
                <th>Source crop evidence</th>
                <th>Check</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.length === 0 ? (
                <tr>
                  <td colSpan={4} className="empty-filter-row">
                    No fields match the selected filter.{" "}
                    <button
                      type="button"
                      className="text-link"
                      onClick={() => setFilter("all")}
                    >
                      Show all {counts.all} fields
                    </button>
                  </td>
                </tr>
              ) : (
                filteredRows.map((row) => {
                  const isSelected = activeRow?.field === row.field;
                  const availableCrops = row.crops.filter((c) => c.url);
                  const isOverridden =
                    doc.overrides &&
                    Object.prototype.hasOwnProperty.call(
                      doc.overrides,
                      row.field,
                    ) &&
                    doc.overrides[row.field] !== undefined;

                  return (
                    <tr
                      key={row.field}
                      className={
                        (isSelected ? "selected-field-row " : "") +
                        (row.needsAttention ? "attention-field-row" : "")
                      }
                      onClick={() => setSelectedField(row.field)}
                    >
                      <td className="field-name-cell">
                        <div className="field-label-wrap">
                          <strong>{row.label}</strong>
                          <span className="field-key-code">{row.field}</span>
                        </div>
                        <div className="field-tags-row">
                          {row.isVisual && (
                            <span className="mini-tag visual">Visual</span>
                          )}
                          {isOverridden && (
                            <span className="mini-tag override">Overridden</span>
                          )}
                        </div>
                      </td>

                      <td className="field-value">
                        {row.value == null &&
                        row.result?.issues.some((i) =>
                          [
                            "UNRECOGNIZED_ENUM",
                            "INVALID_OR_MISSING_ENUM",
                          ].includes(i.code),
                        ) ? (
                          <span className="enum-warning-text">
                            Unrecognized value · needs review
                          </span>
                        ) : (
                          <span className="effective-value-text">
                            {display(row.value)}
                          </span>
                        )}
                        {row.crops
                          .filter((c) => c.kind === "visual")
                          .map((c, idx) => (
                            <div key={idx} className="visual-observed-line">
                              Observed:{" "}
                              <strong>
                                {c.observedPresent === null ||
                                c.observedPresent === undefined
                                  ? "uncertain"
                                  : c.observedPresent
                                    ? "present"
                                    : "absent"}
                              </strong>
                              {c.pageNumber ? ` (P${c.pageNumber})` : ""}
                            </div>
                          ))}
                      </td>

                      <td className="field-crop-cell">
                        {availableCrops.length > 0 ? (
                          <div className="inline-crop-strip">
                            {availableCrops.map((crop, idx) => (
                              <div
                                key={`${crop.storageKey || idx}`}
                                className="inline-crop-card"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSelectedField(row.field);
                                  if (!showInspector) setShowInspector(true);
                                }}
                              >
                                <div className="inline-crop-img-wrap">
                                  <img
                                    loading="lazy"
                                    alt={`${row.label}${
                                      crop.pageNumber
                                        ? `, page ${crop.pageNumber}`
                                        : ""
                                    }`}
                                    src={crop.url}
                                  />
                                </div>
                                <div className="inline-crop-meta">
                                  <span>
                                    {crop.pageNumber
                                      ? `Page ${crop.pageNumber}`
                                      : "Crop"}
                                  </span>
                                  {crop.sourceField !== row.field && (
                                    <span className="crop-subpath">
                                      {crop.sourceField.replace(
                                        row.field + ".",
                                        "",
                                      )}
                                    </span>
                                  )}
                                  <Eye size={12} />
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="inline-crop-empty">
                            <span>
                              {row.errors[0] || "No crop image available"}
                            </span>
                            {canReview && (
                              <span
                                className="inline-region-trigger"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <VisualRegionEditor
                                  documentId={doc.id}
                                  field={row.field}
                                  onSaved={onRegionSaved}
                                />
                              </span>
                            )}
                          </div>
                        )}
                      </td>

                      <td className="field-check-cell">
                        <div className="check-action-top">
                          {row.checkStatus === "OK" ? (
                            <span
                              className="badge good"
                              title="Spider-AI extraction result. Native document validation was skipped."
                            >
                              OK
                            </span>
                          ) : (
                            <Badge value={row.checkStatus} />
                          )}
                          {canReview &&
                            !row.isVisualOnly &&
                            doc.status === "COMPLETED" && (
                              <button
                                type="button"
                                className="icon-button"
                                aria-label={"Correct " + row.label}
                                title={"Correct " + row.label}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onCorrectField(row.field);
                                }}
                              >
                                <Pencil size={14} />
                              </button>
                            )}
                        </div>
                        {row.hasApprovedAlias && (
                          <div className="field-issue">
                            Normalized using approved alias
                          </div>
                        )}
                        {row.result?.issues.slice(0, 2).map((i) => (
                          <div key={i.code} className="field-issue">
                            {i.code.replaceAll("_", " ").toLowerCase()}
                          </div>
                        ))}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {showInspector && activeRow && (
          <aside
            className="field-inspector-pane"
            aria-label="Selected field evidence inspector"
          >
            <div className="inspector-head">
              <div>
                <span className="eyebrow">EVIDENCE INSPECTOR</span>
                <h3>{activeRow.label}</h3>
                <span className="field-key-code">{activeRow.field}</span>
              </div>
              <div className="inspector-nav">
                <button
                  type="button"
                  className="icon-button"
                  disabled={activeIndex <= 0}
                  onClick={() => stepSelection(-1)}
                  title="Previous field"
                  aria-label="Previous field"
                >
                  <ChevronUp size={16} />
                </button>
                <span className="inspector-counter">
                  {activeIndex >= 0 ? activeIndex + 1 : 1} /{" "}
                  {filteredRows.length}
                </span>
                <button
                  type="button"
                  className="icon-button"
                  disabled={
                    activeIndex < 0 || activeIndex >= filteredRows.length - 1
                  }
                  onClick={() => stepSelection(1)}
                  title="Next field"
                  aria-label="Next field"
                >
                  <ChevronDown size={16} />
                </button>
              </div>
            </div>

            <div className="inspector-value-box">
              <div className="inspector-value-header">
                <span className="small-label">EFFECTIVE VALUE</span>
                {activeRow.checkStatus === "OK" ? (
                  <span className="badge good">OK</span>
                ) : (
                  <Badge value={activeRow.checkStatus} />
                )}
              </div>
              <div className="inspector-effective-val">
                {display(activeRow.value)}
              </div>
              <div className="inspector-actions-bar">
                {canReview &&
                  !activeRow.isVisualOnly &&
                  doc.status === "COMPLETED" && (
                    <button
                      type="button"
                      className="secondary compact-btn"
                      onClick={() => onCorrectField(activeRow.field)}
                    >
                      <Pencil size={13} />
                      Correct value
                    </button>
                  )}
                {canReview && (
                  <VisualRegionEditor
                    documentId={doc.id}
                    field={activeRow.field}
                    onSaved={onRegionSaved}
                  />
                )}
              </div>
            </div>

            <div className="inspector-crops-section">
              <div className="inspector-crops-head">
                <span className="small-label">
                  SOURCE CROP EVIDENCE (
                  {activeRow.crops.filter((c) => c.url).length})
                </span>
                {activeRow.crops.some((c) => c.url) && (
                  <div className="inspector-zoom-bar">
                    <button
                      type="button"
                      className="icon-button"
                      disabled={inspectorZoom <= 75}
                      onClick={() =>
                        setInspectorZoom((z) => Math.max(75, z - 25))
                      }
                      title="Zoom out crop"
                      aria-label="Zoom out crop"
                    >
                      <ZoomOut size={14} />
                    </button>
                    <span>{inspectorZoom}%</span>
                    <button
                      type="button"
                      className="icon-button"
                      disabled={inspectorZoom >= 200}
                      onClick={() =>
                        setInspectorZoom((z) => Math.min(200, z + 25))
                      }
                      title="Zoom in crop"
                      aria-label="Zoom in crop"
                    >
                      <ZoomIn size={14} />
                    </button>
                  </div>
                )}
              </div>

              {activeRow.crops.filter((c) => c.url).length > 0 ? (
                <div className="inspector-crop-list">
                  {activeRow.crops
                    .filter((c) => c.url)
                    .map((crop, idx) => (
                      <div
                        key={crop.storageKey || idx}
                        className="inspector-crop-card"
                      >
                        <div className="inspector-crop-viewport">
                          <img
                            alt={`${activeRow.label}, page ${
                              crop.pageNumber || 1
                            }`}
                            style={{
                              width:
                                inspectorZoom === 100
                                  ? "auto"
                                  : `${inspectorZoom}%`,
                              maxWidth:
                                inspectorZoom === 100 ? "100%" : "none",
                            }}
                            src={crop.url}
                          />
                        </div>
                        <div className="inspector-crop-foot">
                          <div>
                            <strong>
                              {crop.pageNumber
                                ? `Source page ${crop.pageNumber}`
                                : "Source crop"}
                            </strong>
                            {crop.sourceField !== activeRow.field && (
                              <span className="crop-subpath">
                                {" · "}
                                {crop.sourceField}
                              </span>
                            )}
                            {crop.kind === "visual" && (
                              <span className="crop-subpath">
                                {" · Observed: "}
                                {crop.observedPresent === null ||
                                crop.observedPresent === undefined
                                  ? "uncertain"
                                  : String(crop.observedPresent)}
                              </span>
                            )}
                          </div>
                          <a
                            className="text-link"
                            href={
                              crop.pageNumber
                                ? `/api/documents/${doc.id}/pages/${crop.pageNumber}`
                                : `/api/documents/${doc.id}/file`
                            }
                            target="_blank"
                            rel="noreferrer"
                          >
                            Open page
                            <ExternalLink size={12} />
                          </a>
                        </div>
                      </div>
                    ))}
                </div>
              ) : (
                <div className="inspector-no-crop">
                  <Layers size={20} />
                  <p>
                    {activeRow.errors[0] ||
                      "No bounding-box crop is stored for this field yet."}
                  </p>
                  <span>
                    Use <strong>Select evidence region</strong> above to mark
                    the location on the document page, or open the full PDF.
                  </span>
                </div>
              )}
            </div>

            <details className="inspector-raw-details">
              <summary>Raw, override & validation metadata</summary>
              <pre>
                {JSON.stringify(
                  {
                    raw: doc.raw?.[activeRow.field],
                    override: doc.overrides?.[activeRow.field],
                    evidence: activeRow.result?.metadata,
                    issues: activeRow.result?.issues,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </aside>
        )}
      </div>
    </div>
  );
}
