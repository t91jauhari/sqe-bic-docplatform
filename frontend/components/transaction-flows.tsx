"use client";
import { DatasetSelect } from "./dataset-select";
import { useEffect, useState } from "react";
import { Plus, Copy, Archive, RotateCcw, Layers } from "lucide-react";
import {
  inFamily,
  ruleInFamily,
  selectableRules,
  familyLabels,
  familyCatalog,
  type DocumentFamily,
} from "@/lib/document-family";
import type { Configuration, ProfileName } from "@/lib/types";
import { Modal } from "@/components/ui";

type Flow = Configuration["templates"][string];
export function TransactionFlows({
  family,
  onFamilyChange,
  draft,
  update,
  canEdit,
}: {
  family: DocumentFamily;
  onFamilyChange: (family: DocumentFamily) => void;
  draft: Configuration;
  update: (v: Configuration) => void;
  canEdit: boolean;
}) {
  const families=familyCatalog(draft), currentFamily=families[family];
  const [open, setOpen] = useState(false),
    [name, setName] = useState(""),
    [key, setKey] = useState(""),
    [copyId, setCopyId] = useState(""),
    [error, setError] = useState(""),
    [keyEdited, setKeyEdited] = useState(false);
  const [selected, setSelected] = useState(
    Object.keys(draft.templates).find(
      (id) => (draft.templates[id].document_family || "forex") === family,
    ) || "",
  );
  useEffect(() => {
    if ((draft.templates[selected]?.document_family || "forex") !== family) {
      setSelected(
        Object.keys(draft.templates).find(
          (id) => (draft.templates[id].document_family || "forex") === family,
        ) || "",
      );
    }
  }, [family, draft.templates, selected]);
  const save = (id: string, flow: Flow) =>
    update({ ...draft, templates: { ...draft.templates, [id]: flow } });
  const create = () => {
    if (!/^[a-z][a-z0-9_-]{0,39}$/.test(key) || draft.templates[key]) {
      setError(
        "Use a unique ID: lowercase letters, digits, underscores or hyphens, starting with a letter (max 40).",
      );
      return;
    }
    if (
      !name.trim() ||
      Object.values(draft.templates).some(
        (f) => f.label.trim().toLowerCase() === name.trim().toLowerCase(),
      )
    ) {
      setError("Enter a unique flow name.");
      return;
    }
    const source = copyId
      ? structuredClone(draft.templates[copyId])
      : {
          required: [],
          sop_rule_ids: currentFamily.sop_rule_ids || [],
          description: "",
          document_family: family,
          dataset_id: currentFamily.dataset_id,
          report_layout: currentFamily.report_layout || "forex",
          report_context: currentFamily.report_context || {},
        };
    save(key, { ...source, required:copyId?source.required:currentFamily.required||[], label: name.trim(), enabled: true });
    setSelected(key);
    setOpen(false);
  };
  return (
    <section className="panel settings-card">
      <div className="section-head">
        <div>
          <h2>
            <Layers size={19} /> Transaction flows
          </h2>
          <p>
            Configure document requirements and SOP checks. Publish to make
            changes available for new cases.
          </p>
        </div>
        {canEdit && (
          <button
            className="primary"
            onClick={() => {
              setName("");
              setKey("");
              setCopyId("");
              setError("");
              setKeyEdited(false);
              setOpen(true);
            }}
          >
            <Plus size={16} />
            Add transaction flow
          </button>
        )}
      </div>
      <label>
        Transaction flow
        <select
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value);
            onFamilyChange(
              (draft.templates[e.target.value].document_family ||
                "forex") as DocumentFamily,
            );
          }}
        >
          {Object.entries(draft.templates)
            .filter(([, flow]) => (flow.document_family || "forex") === family)
            .map(([id, flow]) => (
              <option key={id} value={id}>
                {flow.label}
                {flow.enabled === false ? " · Archived" : ""}
              </option>
            ))}
        </select>
      </label>
      <fieldset disabled={!canEdit}>
        {Object.entries(draft.templates)
          .filter(
            ([id, flow]) =>
              id === selected && (flow.document_family || "forex") === family,
          )
          .map(([id, flow]) => (
            <div className="template-card" key={id}>
              <div className="section-head">
                <strong>
                  {flow.label}{" "}
                  <span className="count-pill">
                    {flow.enabled === false ? "Archived" : "Active"}
                  </span>
                </strong>
                <div className="button-row">
                  <button
                    className="secondary"
                    onClick={() => {
                      setName(flow.label + " copy");
                      setKey("");
                      setCopyId(id);
                      setError("");
                      setKeyEdited(false);
                      setOpen(true);
                    }}
                  >
                    <Copy size={15} />
                    Duplicate
                  </button>
                  <button
                    className="danger"
                    onClick={() =>
                      save(id, { ...flow, enabled: flow.enabled === false })
                    }
                  >
                    {flow.enabled === false ? (
                      <RotateCcw size={15} />
                    ) : (
                      <Archive size={15} />
                    )}
                    {flow.enabled === false ? "Restore" : "Archive"}
                  </button>
                </div>
              </div>
              <small>
                ID: {id} · existing cases retain their published version
              </small>
              <label>
                Flow name
                <input
                  maxLength={120}
                  value={flow.label}
                  onChange={(e) => save(id, { ...flow, label: e.target.value })}
                />
              </label>
              <label>
                Description
                <textarea
                  maxLength={2000}
                  value={flow.description || ""}
                  onChange={(e) =>
                    save(id, { ...flow, description: e.target.value })
                  }
                />
              </label>
              <label>
                Document family
                <select
                  value={flow.document_family || "forex"}
                  onChange={(e) => {
                    const next = e.target.value as DocumentFamily;
                    save(id, {
                      ...flow,
                      document_family: next,
                      dataset_id: families[next].dataset_id,
                      report_layout: families[next].report_layout || "forex",
                      required: flow.required.filter((type) =>
                        inFamily(type, next, draft),
                      ),
                      sop_rule_ids:
                        flow.sop_rule_ids == null
                          ? null
                          : flow.sop_rule_ids.filter((ruleId) =>
                              selectableRules(draft).some(
                                (r) => r.id === ruleId && ruleInFamily(r, next, draft),
                              ),
                            ),
                    });
                    onFamilyChange(next);
                  }}
                >
                  {Object.entries(families).map(([key,value])=><option key={key} value={key}>{value.label}</option>)}
                </select>
              </label>
              <p>
                Changing this flow's family removes incompatible
                required-document and selected SOP choices from the draft.
                Shared documents remain selected. Confirm requirements before
                publishing.
              </p>
              <details>
                <summary>Advanced: reference dataset and report layout</summary>
                <label>
                  Reference dataset
                  <DatasetSelect value={flow.dataset_id===null?"":flow.dataset_id || "forex-sample-v1"}
                    onChange={value => save(id, { ...flow, dataset_id: value || null })}/>

                </label>
                <label>
                  Report layout
                  <select
                    value={flow.report_layout || "forex"}
                    onChange={(e) =>
                      save(id, { ...flow, report_layout: e.target.value })
                    }
                  >
                    <option value="forex">Forex Kertas Kerja</option>
                    <option value="account_opening">
                      Account Opening Kertas Kerja
                    </option>
                  </select>
                </label>
              </details>
              <h3>Required documents · {currentFamily.label}</h3>
              {Object.entries(draft.profiles)
                .filter(([type]) => inFamily(type, family, draft))
                .map(([type, profile]) => (
                  <label className="checkbox-label compact" key={type}>
                    <input
                      type="checkbox"
                      checked={flow.required.includes(type as ProfileName)}
                      onChange={(e) =>
                        save(id, {
                          ...flow,
                          required: e.target.checked
                            ? [...flow.required, type as ProfileName]
                            : flow.required.filter((x) => x !== type),
                        })
                      }
                    />
                    {profile.label}
                  </label>
                ))}
              {!flow.required.length && (
                <p className="info-note">
                  No mandatory documents configured. Confirm your bank's
                  requirements before operational use.
                </p>
              )}
              <h3>Applicable SOP checks · {currentFamily.label}</h3>
              <label className="checkbox-label compact">
                <input
                  type="checkbox"
                  checked={flow.sop_rule_ids == null}
                  onChange={(e) =>
                    save(id, {
                      ...flow,
                      sop_rule_ids: e.target.checked ? null : [],
                    })
                  }
                />
                Use all SOP checks for this document family
              </label>
              {flow.sop_rule_ids != null && (
                <details>
                  <summary>
                    {flow.sop_rule_ids.length} selected checks · edit selection
                  </summary>
                  {selectableRules(draft)
                    .filter((rule) => ruleInFamily(rule, family, draft))
                    .map((rule) => (
                      <label className="checkbox-label compact" key={rule.id}>
                        <input
                          type="checkbox"
                          checked={flow.sop_rule_ids!.includes(rule.id)}
                          onChange={(e) =>
                            save(id, {
                              ...flow,
                              sop_rule_ids: e.target.checked
                                ? [...flow.sop_rule_ids!, rule.id]
                                : flow.sop_rule_ids!.filter(
                                    (x) => x !== rule.id,
                                  ),
                            })
                          }
                        />
                        {rule.id} · {rule.label}
                      </label>
                    ))}
                </details>
              )}
              {flow.sop_rule_ids?.length === 0 && (
                <p className="info-note">
                  No SOP checks selected. Cases remain REVIEW until applicable
                  checks are configured.
                </p>
              )}
            </div>
          ))}
      </fieldset>
      {open && (
        <Modal
          title="Create transaction flow from a starting template"
          onClose={() => setOpen(false)}
        >
          <label>
            Name
            <input
              maxLength={120}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (!keyEdited)
                  setKey(
                    e.target.value
                      .toLowerCase()
                      .replace(/[^a-z0-9]+/g, "_")
                      .replace(/_$/g, "")
                      .slice(0, 40),
                  );
              }}
            />
          </label>
          <label>
            Start from an existing flow
            <select value={copyId} onChange={(e) => setCopyId(e.target.value)}>
              <option value="">
                Family defaults (recommended for a new flow)
              </option>
              {Object.entries(draft.templates)
                .filter(
                  ([, flow]) => (flow.document_family || "forex") === family,
                )
                .map(([id, flow]) => (
                  <option key={id} value={id}>
                    {flow.label}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Stable flow ID
            <input
              maxLength={40}
              value={key}
              onChange={(e) => {
                setKey(e.target.value);
                setKeyEdited(true);
              }}
            />
          </label>
          {error && (
            <p role="alert" className="field-issue">
              {error}
            </p>
          )}
          <button className="primary" onClick={create}>
            <Plus size={16} />
            Add to configuration draft
          </button>
        </Modal>
      )}
    </section>
  );
}
