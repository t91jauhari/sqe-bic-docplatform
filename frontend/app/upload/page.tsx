"use client";
import { useState, useRef, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import {
  UploadCloud,
  FileText,
  X,
  ArrowRight,
  ShieldCheck,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { useData, usePlatform } from "@/components/platform-provider";
import { api } from "@/lib/api";
import { Busy, ErrorNotice } from "@/components/ui";
import type { Branch, ConfigResponse, CaseDetail } from "@/lib/types";
import {familyCatalog} from "@/lib/document-family";
import {
  GroupingDialog,
  type GroupingRow as Preview,
} from "@/components/grouping-dialog";
import {
  TemplateChoiceDialog,
  type TemplateOption,
} from "@/components/template-choice-dialog";
function UploadForm() {
  const router = useRouter(),
    params = useSearchParams(),
    caseId = params.get("case") || "",
    attachBranch = params.get("branch") || "";
  const { startUpload, upload, user } = usePlatform();
  const { data: branches } = useData<Branch[]>("/branches", 0),
    { data: cfg } = useData<ConfigResponse>("/config", 0);
  const [attachedCase, setAttachedCase] = useState<CaseDetail | null>(null);
  const [files, setFiles] = useState<File[]>([]),
    [preview, setPreview] = useState<Preview[]>([]),
    [branch, setBranch] = useState(attachBranch),
    // No default: the flow must be confirmed explicitly for this batch.
    [template, setTemplate] = useState("");
  const [choiceOpen, setChoiceOpen] = useState(false);
  const [error, setError] = useState(""),
    [pending, setPending] = useState(false),
    [dragging, setDragging] = useState(false);
  const [groupingOpen, setGroupingOpen] = useState(false);
  const [viewMode, setViewMode] = useState<"grouped" | "flat">("grouped");
  const [previewPending, setPreviewPending] = useState(false);
  const previewRequest = useRef(0);
  const input = useRef<HTMLInputElement>(null),
    key = useRef("");
  useEffect(() => {
    if (!branch && branches?.length) setBranch(branches[0].id);
  }, [branches, branch]);
  useEffect(() => {
    // Only auto-pick when the flow is pinned by an existing case; free uploads
    // require an explicit choice through the confirmation dialog.
    if (caseId && !template && cfg) {
      const first = Object.entries(cfg.payload.templates).find(
        ([, f]) => f.enabled !== false,
      );
      if (first) setTemplate(first[0]);
    }
  }, [cfg, template, caseId]);
  useEffect(() => {
    if (!caseId) return;
    let active = true;
    api<CaseDetail>(`/cases/${caseId}`).then(value => {
      if (active) { setAttachedCase(value); setTemplate(value.template); }
    }).catch(e => { if (active) setError(e instanceof Error ? e.message : "Unable to load existing case"); });
    return () => { active = false; };
  }, [caseId]);
  const choose = async (next: File[]) => {
    setError("");
    const IMAGE_RE = /\.(pdf|png|jpe?g)$/i;
    const valid = next.filter((f) => IMAGE_RE.test(f.name));
    if (valid.length !== next.length) {
      setError("Only PDF, PNG or JPG files are supported.");
      return;
    }
    if (valid.length > 100 || valid.some((f) => f.size > 30 * 1024 * 1024)) {
      setError("Choose up to 100 files, each below 30 MB.");
      return;
    }
    if (new Set(valid.map((f) => f.name)).size !== valid.length) {
      setError("Filenames must be unique within an upload.");
      return;
    }
    const request = ++previewRequest.current;
    setPreviewPending(true);
    setGroupingOpen(false);
    setPreview([]);
    setFiles(valid);
    key.current = crypto.randomUUID();
    try {
      const next = await api<Preview[]>("/uploads/preview", {
        method: "POST",
        body: JSON.stringify({ filenames: valid.map((f) => f.name) }),
      });
      if (request !== previewRequest.current) return;
      // Guard against a partially-shaped response: never render `undefined`
      // into the customer label inputs.
      const normalized = next.map((p) => ({
        ...p,
        filename: p.filename ?? "",
        hint: p.hint ?? "",
        customer: p.customer ?? "",
        explanation: p.explanation ?? "",
        original_customer: p.original_customer ?? "",
        status: p.status ?? "unresolved",
        candidates: p.candidates ?? [],
      }));
      setPreview(normalized);
      if (!caseId && normalized.some((p) => p.status === "unresolved"))
        setGroupingOpen(true);
      else if (!caseId) setChoiceOpen(true);
    } catch (e) {
      if (request === previewRequest.current)
        setError(e instanceof Error ? e.message : "Preview unavailable.");
    } finally {
      if (request === previewRequest.current) setPreviewPending(false);
    }
  };
  const submit = async () => {
    if (!files.length || pending || previewPending) return;
    if (!caseId && preview.some((p) => !(p.customer ?? "").trim())) {
      setGroupingOpen(true);
      return;
    }
    setPending(true);
    setError("");
    const form = new FormData();
    form.set("branch_id", branch);
    form.set("template", template);
    if (caseId) form.set("case_id", caseId);
    form.set(
      "grouping",
      JSON.stringify(
        Object.fromEntries(
          preview
            .filter((p) => p.status === "manual" && p.customer.trim())
            .map((p) => [p.filename, p.customer]),
        ),
      ),
    );
    files.forEach((f) => form.append("files", f));
    try {
      const result = await startUpload(form, key.current);
      router.push(
        result.case_ids.length === 1
          ? "/cases/" + result.case_ids[0]
          : "/cases",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setPending(false);
    }
  };
  const groups = new Set(
    preview.map((p) => p.customer.trim().toLowerCase()).filter(Boolean),
  ).size;
  return (
    <Shell
      title={caseId ? "Add documents to case" : "Bulk upload"}
      subtitle="Match customer names across the batch, review uncertain matches, then process."
    >
      {groupingOpen && (
        <GroupingDialog
          rows={preview}
          files={files}
          onClose={() => setGroupingOpen(false)}
          onConfirm={(rows) => {
            setPreview(rows);
            setGroupingOpen(false);
            key.current = crypto.randomUUID();
            if (!caseId && !template) setChoiceOpen(true);
          }}
        />
      )}
      {choiceOpen && !caseId && (
        <TemplateChoiceDialog
          options={Object.entries(cfg?.payload.templates || {})
            .filter(([, t]) => t.enabled !== false && familyCatalog(cfg?.payload)[t.document_family||"forex"]?.enabled!==false)
            .map(([id, t]): TemplateOption => ({
              id,
              label: t.label || id,
              description: t.description,
            }))}
          selected={template}
          busy={pending || previewPending}
          onConfirm={(value) => {
            setTemplate(value);
            setChoiceOpen(false);
            key.current = crypto.randomUUID();
          }}
          onClose={() => setChoiceOpen(false)}
        />
      )}
      {user?.role === "auditor" ? (
        <ErrorNotice message="Your role has read-only access." />
      ) : (
        <div className="upload-layout">
          <section className="panel upload-panel">
            <div className="section-head">
              <div>
                <h2>
                  {caseId
                    ? "Supplement an existing case"
                    : "A batch, one upload"}
                </h2>
                <p>Processing continues when you leave this screen.</p>
              </div>
              <span className="small-label">PDF · UP TO 30 MB EACH</span>
            </div>
            <div className="form-row">
              <label>
                Branch
                <select
                  value={branch}
                  disabled={!!caseId || pending}
                  onChange={(e) => setBranch(e.target.value)}
                >
                  {branches?.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Transaction flow
                {caseId && attachedCase ? (
                  <select value={template} disabled>
                    <option value={attachedCase.template}>
                      {attachedCase.transaction_flow_label ||
                        attachedCase.template}{" "}
                      · pinned configuration
                    </option>
                  </select>
                ) : template ? (
                  <span className="template-chip">
                    <strong>
                      {cfg?.payload.templates[template]?.label || template}
                    </strong>
                    <button
                      type="button"
                      className="link-button"
                      disabled={pending || previewPending}
                      onClick={() => setChoiceOpen(true)}
                    >
                      Change
                    </button>
                  </span>
                ) : (
                  <span className="template-chip unset">
                    Not chosen yet
                    <button
                      type="button"
                      className="link-button"
                      disabled={!files.length || previewPending}
                      onClick={() => setChoiceOpen(true)}
                    >
                      Choose
                    </button>
                  </span>
                )}
              </label>
            </div>
            {caseId && cfg?.payload.templates[template]?.description && <div className="info-note">{cfg.payload.templates[template].description}</div>}
            <div
              className={"dropzone " + (dragging ? "dragging" : "")}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                if (!pending) void choose(Array.from(e.dataTransfer.files));
              }}
            >
              <div className="drop-icon">
                <UploadCloud size={29} />
              </div>
              <h3>Drop customer documents here</h3>
              <p>Or choose a batch from your computer</p>
              <button
                className="secondary"
                disabled={pending}
                onClick={() => input.current?.click()}
              >
                Browse files
              </button>
              <input
                ref={input}
                type="file"
                multiple
                accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                hidden
                onChange={(e) => void choose(Array.from(e.target.files || []))}
              />
            </div>
            {previewPending && <p>Matching customer names across the batch…</p>}
            {!!preview.length && !caseId && (
              <button
                className="secondary"
                disabled={pending || previewPending}
                onClick={() => setGroupingOpen(true)}
              >
                Review grouping
                {preview.some((p) => !(p.customer ?? "").trim())
                  ? " · unresolved documents"
                  : ""}
              </button>
            )}
            {error && <ErrorNotice message={error} />}
            {!!preview.length && (
              <>
                <div className="preview-summary">
                  <div>
                    <strong>{files.length} documents</strong>{" "}
                    <span>
                      {"· "}
                      {caseId ? "Existing case" : groups + " customer groups"} {"· "}
                      labels are editable before upload
                    </span>
                  </div>
                  {!caseId && (
                    <div className="field-filter-pills">
                      <button
                        type="button"
                        className={viewMode === "grouped" ? "active" : ""}
                        onClick={() => setViewMode("grouped")}
                      >
                        Customer packages <span>{groups}</span>
                      </button>
                      <button
                        type="button"
                        className={viewMode === "flat" ? "active" : ""}
                        onClick={() => setViewMode("flat")}
                      >
                        Flat file list <span>{files.length}</span>
                      </button>
                    </div>
                  )}
                </div>
                {viewMode === "grouped" && !caseId && (
                  <div className="upload-package-grid">
                    {Array.from(
                      preview.reduce((acc, row) => {
                        const key = row.customer.trim() || "Unassigned customer";
                        const list = acc.get(key) || [];
                        list.push(row);
                        acc.set(key, list);
                        return acc;
                      }, new Map<string, Preview[]>()),
                    ).map(([custName, custRows]) => (
                      <div key={custName} className="upload-package-card">
                        <div className="upload-package-head">
                          <strong>{custName}</strong>
                          <span className="count-pill">
                            {custRows.length} file{custRows.length === 1 ? "" : "s"}
                          </span>
                        </div>
                        <ul className="upload-package-files">
                          {custRows.map((r) => (
                            <li key={r.filename}>
                              <FileText size={13} />
                              <span>{r.filename}</span>
                              <small>{r.hint.replaceAll("_", " ")}</small>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Document</th>
                        <th>Customer label</th>
                        <th>Filename hint</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {preview.map((p, i) => (
                        <tr key={p.filename}>
                          <td>
                            <span className="file-cell">
                              <FileText size={17} />
                              {p.filename}
                            </span>
                          </td>
                          <td>
                            <input
                              aria-label={"Customer for " + p.filename}
                              value={p.customer}
                              disabled={pending || !!caseId}
                              onChange={(e) =>
                                setPreview((previous) =>
                                  previous.map((x, j) =>
                                    i === j
                                      ? {
                                          ...x,
                                          customer: e.target.value,
                                          status: "manual",
                                        }
                                      : x,
                                  ),
                                )
                              }
                            />
                          </td>
                          <td className="muted">
                            {p.hint.replaceAll("_", " ")}
                          </td>
                          <td>
                            <button
                              className="icon-button"
                              disabled={pending}
                              aria-label={"Remove " + p.filename}
                              onClick={() => {
                                void choose(
                                  files.filter((f) => f.name !== p.filename),
                                );
                                key.current = crypto.randomUUID();
                              }}
                            >
                              <X size={16} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            <div className="upload-actions">
              <span>
                {pending
                  ? "Upload " + (upload?.progress || 0) + "%"
                  : "Classification verifies the schema after grouping."}
              </span>
              <button
                className="primary"
                disabled={
                  pending ||
                  previewPending ||
                  !files.length ||
                  !branch ||
                  !template ||
                  preview.length !== files.length ||
                  (!caseId && preview.some((p) => !p.customer.trim()))
                }
                onClick={() => void submit()}
              >
                {pending ? "Uploading…" : "Upload & start processing"}
                <ArrowRight size={17} />
              </button>
            </div>
          </section>
          <aside className="panel guidance">
            <div className="guidance-icon">
              <ShieldCheck size={23} />
            </div>
            <h3>Names bring the case together.</h3>
            <p>
              Full names and unambiguous initials are matched automatically.
              Review uncertain assignments before processing.
            </p>
            <div className="filename-example">
              customer_transaction.pdf
              <br />
              customer_lld.pdf
              <br />
              customer_invoice.pdf
            </div>
            <ol>
              <li>
                <strong>Group first</strong>
                <span>
                  Same customer label, selected branch and upload batch.
                </span>
              </li>
              <li>
                <strong>Classify next</strong>
                <span>The configured provider verifies the document type.</span>
              </li>
              <li>
                <strong>Extract and check</strong>
                <span>
                  The matching schema and SOP rules run automatically.
                </span>
              </li>
            </ol>
            <p className="subtext">
              Later uploads create new cases unless explicitly attached to an
              existing case.
            </p>
            {cfg?.payload.provider === "fixture" && (
              <p className="fixture-note">
                Fixture mode is enabled. Outputs contain synthetic test values.
              </p>
            )}
          </aside>
        </div>
      )}
    </Shell>
  );
}
export default function UploadPage() {
  return (
    <Suspense fallback={<Busy />}>
      <UploadForm />
    </Suspense>
  );
}
