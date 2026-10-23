"use client";
import { useRef, useState } from "react";
import {
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Search,
  X,
  ShieldCheck,
  WandSparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { useData, usePlatform } from "./platform-provider";
import { Badge, ErrorNotice } from "./ui";

type FieldRequest = {
  id: string;
  status: string;
  reason: string;
  fields: string[];
  config_version: number;
  instruction?: string;
  guidance_saved_to_profile?: boolean;
  error?: string;
  requires_duplicate_charge_ack?: boolean;
  can_retry?: boolean;
};
export function FieldReprocess({
  documentId,
  columns,
  onQueued,
  canReplaceOverrides = false,
}: {
  documentId: string;
  columns: [string, string][];
  onQueued: () => void;
  canReplaceOverrides?: boolean;
}) {
  const { online, user } = usePlatform();
  const canSaveProfile = user?.role === "bank_admin";
  const [saveToProfile, setSaveToProfile] = useState(true);
  const {
    data: history,
    error: historyError,
    refresh,
  } = useData<FieldRequest[]>(`/documents/${documentId}/reprocess-fields`);
  const [fields, setFields] = useState<string[]>([]),
    [query, setQuery] = useState("");
  const [instruction, setInstruction] = useState(""),
    [reason, setReason] = useState("");
  const savingGuidance = canSaveProfile && saveToProfile && !!instruction.trim();
  const [latest, setLatest] = useState(true),
    [replaceOverrides, setReplaceOverrides] = useState(false);
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState<{ text: string; error: boolean } | null>(
      null,
    );
  const [acceptCharge, setAcceptCharge] = useState(false);
  const submitting = useRef(false);
  const visible = columns.filter(([key, label]) =>
    `${key} ${label}`.toLowerCase().includes(query.toLowerCase()),
  );
  const active = history?.some(
    (h) => !["COMPLETED", "ERROR", "CANCELLED"].includes(h.status),
  );
  const blocked = busy || !!active || !online;
  const fieldLabel = (key: string) =>
    columns.find((c) => c[0] === key)?.[1] || key;
  const submit = async (requestId?: string) => {
    if (submitting.current || blocked) return;
    submitting.current = true;
    setBusy(true);
    setMessage(null);
    try {
      await api(
        `/documents/${documentId}/reprocess-fields${requestId ? `/${requestId}/retry` : ""}`,
        {
          method: "POST",
          body: JSON.stringify(
            requestId
              ? { accept_possible_duplicate_charge: acceptCharge }
              : {
                  fields,
                  instruction,
                  reason: reason.trim(),
                  use_latest_config: savingGuidance || latest,
                  save_to_profile: canSaveProfile && saveToProfile,
                  replace_overrides: replaceOverrides,
                },
          ),
        },
      );
      setMessage({
        text: requestId
          ? "Request resumed. Saved provider results will be reused where available."
          : savingGuidance
            ? "Guidance saved to this document profile for future runs. Selected fields are queued for extraction."
            : "Request accepted. Selected fields will update when extraction completes.",
        error: false,
      });
      if (!requestId) {
        setFields([]);
        setReason("");
        setInstruction("");
        setReplaceOverrides(false);
      }
      setAcceptCharge(false);
      await refresh();
      onQueued();
    } catch (e) {
      setMessage({
        text:
          e instanceof Error
            ? e.message
            : "Unable to start extraction. Your selections are preserved; try again.",
        error: true,
      });
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };
  return (
    <details className="field-instructions reprocess-workspace">
      <summary className="reprocess-summary">
        <span className="reprocess-symbol">
          <WandSparkles size={18} />
        </span>
        <span>
          <strong>Reprocess selected fields</strong>
          <small>
            Correct an uncertain extraction using the original document
          </small>
        </span>
        <span className="count-pill">{columns.length} fields</span>
      </summary>
      <div className="reprocess-body">
        <div className="assurance-note">
          <ShieldCheck size={17} />
          <span>
            Only selected fields are updated. Reviewer corrections are preserved
            by default.
          </span>
        </div>
        <fieldset disabled={blocked}>
          <div className="step-title">
            <span>1</span>
            <div>
              <h3>Choose fields to read again</h3>
              <p>Select only the values that need another look.</p>
            </div>
          </div>
          <label className="quick-search">
            <Search size={16} />
            <input
              aria-label="Find a field"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by field name"
            />
          </label>
          <div className="selection-toolbar">
            <span>
              <strong>{fields.length}</strong> selected · {visible.length} shown
            </span>
            <div>
              <button
                type="button"
                className="text-button"
                disabled={!visible.length}
                onClick={() =>
                  setFields([
                    ...new Set([...fields, ...visible.map(([key]) => key)]),
                  ])
                }
              >
                Select shown
              </button>
              <button
                type="button"
                className="text-button"
                disabled={!fields.length}
                onClick={() => setFields([])}
              >
                Clear selection
              </button>
            </div>
          </div>
          {!!fields.length && (
            <div className="selected-fields" aria-label="Selected fields">
              {fields.map((key) => (
                <button
                  type="button"
                  key={key}
                  onClick={() => setFields(fields.filter((f) => f !== key))}
                  aria-label={`Remove ${fieldLabel(key)}`}
                >
                  {fieldLabel(key)}
                  <X size={13} />
                </button>
              ))}
            </div>
          )}
          <div className="field-catalogue selection-grid">
            {visible.map(([key, label]) => (
              <label
                key={key}
                className={fields.includes(key) ? "selected" : ""}
              >
                <input
                  type="checkbox"
                  checked={fields.includes(key)}
                  onChange={(e) =>
                    setFields(
                      e.target.checked
                        ? [...fields, key]
                        : fields.filter((f) => f !== key),
                    )
                  }
                />
                <span>
                  {label}
                  <small>{key}</small>
                </span>
              </label>
            ))}
            {!visible.length && (
              <p className="no-field-match">
                No fields match “{query}”. Try a shorter name.
              </p>
            )}
          </div>
          <div className="step-title">
            <span>2</span>
            <div>
              <h3>Explain what needs attention</h3>
              <p>A short reason keeps the review history useful.</p>
            </div>
          </div>
          <label>
            Reason{" "}
            <span className="required-label">
              Required · at least 3 characters
            </span>
            <input
              value={reason}
              maxLength={2000}
              onChange={(e) => setReason(e.target.value)}
              placeholder="For example: the account number has an unclear final digit"
            />
          </label>
          <label>
            Additional extraction guidance{" "}
            <small>Optional · describe a reusable reading rule, not an expected answer</small>
            <textarea
              rows={3}
              value={instruction}
              maxLength={10000}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="Describe where to look or what to distinguish. Avoid entering an expected answer."
            />
          </label>
          {canSaveProfile ? (
            <label className="checkbox-line">
              <input type="checkbox" checked={saveToProfile} onChange={(e) => setSaveToProfile(e.target.checked)} />
              <span>Save guidance to this document profile
                <small>Appends to Document Instructions for the selected fields and publishes a new configuration version. This rerun and future uploads use it. Existing cases must use the latest published profile. Clear this option for this request only.</small>
              </span>
            </label>
          ) : (
            <p>Guidance applies to this request only. A bank administrator can save it to the shared document profile.</p>
          )}
          <details className="reprocess-options">
            <summary>Profile and correction options</summary>
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={savingGuidance || latest}
                disabled={savingGuidance}
                onChange={(e) => setLatest(e.target.checked)}
              />
              <span>
                Use latest published profile instructions
                <small>
                  Turn off to use this case’s original configuration.
                </small>
              </span>
            </label>
            {canReplaceOverrides && (
              <label className="checkbox-line">
                <input
                  type="checkbox"
                  checked={replaceOverrides}
                  onChange={(e) => setReplaceOverrides(e.target.checked)}
                />
                <span>
                  Replace reviewer corrections for selected fields
                  <small>
                    Previous corrections remain in the request history.
                  </small>
                </span>
              </label>
            )}
          </details>
        </fieldset>
        {replaceOverrides && (
          <div className="inline-feedback warning">
            <AlertCircle size={17} />
            Successful extraction will replace the selected fields’ reviewer
            corrections.
          </div>
        )}
        <div className="reprocess-submit">
          <div>
            <strong>
              {fields.length
                ? `${fields.length} field${fields.length === 1 ? "" : "s"} ready to reprocess`
                : "Select at least one field"}
            </strong>
            <p>
              {!online
                ? "Reconnect to start a request."
                : active
                  ? "A field request is already running for this document."
                  : reason.trim().length < 3
                    ? "Add a reason to enable reprocessing."
                    : "Provider usage may apply. You can continue working after submission."}
            </p>
          </div>
          <button
            className="primary"
            disabled={blocked || !fields.length || reason.trim().length < 3}
            onClick={() => void submit()}
          >
            <RefreshCw size={16} className={busy ? "spin" : ""} />
            {busy ? "Submitting…" : "Reprocess selected fields"}
          </button>
        </div>
        {message && (
          <div
            className={`inline-feedback ${message.error ? "error" : "success"}`}
            role={message.error ? "alert" : "status"}
          >
            {message.error ? (
              <AlertCircle size={18} />
            ) : (
              <CheckCircle2 size={18} />
            )}
            <span>{message.text}</span>
          </div>
        )}
        {historyError && (
          <ErrorNotice
            message={`Reprocessing history is unavailable. ${historyError}`}
            retry={() => void refresh()}
          />
        )}
        {!!history?.length && (
          <details className="reprocess-history" open={!!active||history.some(item=>item.status==='ERROR')}>
            <summary>
              Recent field reprocessing{" "}
              <span className="count-pill">{history.length}</span>
            </summary>
            {history.some((item) => item.status === "ERROR"&&item.requires_duplicate_charge_ack!==false) && (
              <label className="checkbox-line">
                <input
                  type="checkbox"
                  checked={acceptCharge}
                  disabled={blocked}
                  onChange={(e) => setAcceptCharge(e.target.checked)}
                />
                <span>
                  Allow a possible duplicate provider charge when resuming an
                  uncertain submission
                  <small>
                    Only needed if the previous provider submission could not be
                    confirmed.
                  </small>
                </span>
              </label>
            )}
            {history.slice(0, 10).map((item) => (
              <article className="request-card" key={item.id}>
                <div className="request-heading">
                  <Badge value={item.status} />
                  <small>Configuration v{item.config_version}</small>
                </div>
                <strong>{item.reason}</strong>
                <p>{item.fields.map(fieldLabel).join(", ")}</p>
                {item.instruction && <details>
                  <summary>{item.guidance_saved_to_profile ? "Guidance saved to document profile" : "Request-only guidance"}</summary>
                  <p style={{ whiteSpace: "pre-wrap" }}>{item.instruction}</p>
                </details>}
                {item.status==='ERROR'&&item.error&&<p>{item.error}</p>}
                {item.status === "ERROR" && (
                  <button
                    className="secondary"
                    disabled={blocked||item.can_retry===false}
                    onClick={() => void submit(item.id)}
                  >
                    <RefreshCw size={14} />
                    Resume field request
                  </button>
                )}
              </article>
            ))}
          </details>
        )}
      </div>
    </details>
  );
}
