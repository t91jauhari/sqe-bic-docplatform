"use client";
import {
  familyLabels,
  familyProfiles,
  familyCatalog,
  inFamily,
  type DocumentFamily,
} from "@/lib/document-family";
import { ForexSOPPolicyEditor } from "@/components/forex-sop-policy";
import { ContextEditor } from "@/components/context-editor";
import { ComparisonUpgrade } from "@/components/comparison-upgrade";
import { ProfileVersionComparison } from "@/components/profile-version-comparison";

import { ConnectorHub } from "@/components/connector-hub";
import { AccessManager } from "@/components/access-manager";
import { TransactionFlows } from "@/components/transaction-flows";
import { DocumentFamilies } from "@/components/document-families";
import { useState, useEffect, useCallback, useRef } from "react";
import {
  Save,
  Plus,
  Trash2,
  ShieldCheck,
  KeyRound,
  FlaskConical,
  Layers,
  Route,
  Workflow,
  SlidersHorizontal,
  ScanLine,
  ListChecks,
  Plug,
  Users,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { useData, usePlatform } from "@/components/platform-provider";
import { Busy, ErrorNotice, Modal, Badge } from "@/components/ui";
import { AutomationEditor, SOPBuilder } from "@/components/automation-editor";
import { LocationLearningHistory } from "@/components/location-learning-history";
import { FieldChecks } from "@/components/field-checks";
import { FieldDescriptionEditor } from "@/components/field-description-editor";
import { ProfileCreate } from "@/components/profile-create";
import { ProfileSchemaEditor } from "@/components/profile-schema-editor";
import { ProfileExtractionControls } from "@/components/profile-extraction-controls";
import { api } from "@/lib/api";
import type {
  ConfigResponse,
  Configuration,
  ProfileName,
  Branch,
  User,
} from "@/lib/types";
type Tab =
  | "families"
  | "flows"
  | "automation"
  | "workflow"
  | "profiles"
  | "rules"
  | "connector"
  | "access";
const settingsSections = {
  families: {
    label: "Document families",
    detail: "Group documents & defaults",
    icon: Layers,
  },
  flows: {
    label: "Transaction flows",
    detail: "Required documents per service",
    icon: Route,
  },
  profiles: {
    label: "Document profiles",
    detail: "Fields, prompts & reading rules",
    icon: ScanLine,
  },
  rules: {
    label: "SOP rules",
    detail: "Validation & review checks",
    icon: ListChecks,
  },
  automation: {
    label: "Automation",
    detail: "Workflow steps & replay",
    icon: Workflow,
  },
  workflow: {
    label: "Processing defaults",
    detail: "Shared extraction behavior",
    icon: SlidersHorizontal,
  },
  connector: {
    label: "Connector",
    detail: "Model provider connections",
    icon: Plug,
  },
  access: {
    label: "Branches & users",
    detail: "Organization access controls",
    icon: Users,
  },
};
type Test = {
  sop_results?: {
    case_id: string;
    customer: string;
    scores: Record<string, number | null>;
    findings: { result: string }[];
  }[];
  tested: number;
  results: {
    filename: string;
    before: string;
    after: string;
    issues?: number;
    error?: string;
  }[];
  note: string;
};
export default function Settings() {
  const { user, notify, online } = usePlatform(),
    { data, loading, error, refresh } = useData<ConfigResponse>("/config", 0);
  const [draft, setDraft] = useState<Configuration | null>(null),
    [version, setVersion] = useState(0),
    [tab, setTab] = useState<Tab>("flows"),
    [profile, setProfile] = useState<ProfileName>("application");
  const [familySelection, setFamily] = useState<DocumentFamily>("forex");
  const families = familyCatalog(draft);
  const family = families[familySelection] ? familySelection : Object.keys(families)[0] || "forex";
  const selectedProfile = inFamily(profile, family, draft)
    ? profile
    : families[family]?.profiles[0] || profile;
  const [pending, setPending] = useState(false),
    [dirty, setDirty] = useState(false),
    [policyText, setPolicyText] = useState(""),
    [policyError, setPolicyError] = useState(""),
    [test, setTest] = useState<Test | null>(null);
  const canEdit = user?.role === "bank_admin";
  const dirtyRef = useRef(false);
  const [discardOpen, setDiscardOpen] = useState(false);
  const [draftEpoch, setDraftEpoch] = useState(0);
  const [profileView, setProfileView] = useState("fields");
  useEffect(() => {
    if (data && !dirtyRef.current) {
      setDraft(structuredClone(data.payload));
      setVersion(data.version);
      setDirty(false);
    }
  }, [data]);
  useEffect(() => {
    if (draft) {
      setPolicyText(
        JSON.stringify(draft.profiles[selectedProfile].policy, null, 2),
      );
      setPolicyError("");
    }
  }, [
    selectedProfile,
    version,
    JSON.stringify(draft?.profiles[selectedProfile]?.policy),
  ]); // profile switch intentionally resets the editor
  useEffect(() => {
    if (!dirty) return;
    const stop = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", stop);
    const leave = (e: MouseEvent) => {
      const link = (e.target as HTMLElement).closest?.(
        "a[href]",
      ) as HTMLAnchorElement | null;
      if (
        !link ||
        link.target === "_blank" ||
        link.origin !== location.origin ||
        link.getAttribute("href")?.startsWith("#")
      )
        return;
      if (
        link.pathname !== location.pathname &&
        !window.confirm("Leave configuration and discard unpublished changes?")
      ) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    document.addEventListener("click", leave, true);
    return () => {
      window.removeEventListener("beforeunload", stop);
      document.removeEventListener("click", leave, true);
    };
  }, [dirty]);
  const update = (next: Configuration) => {
    if (next.rule_order) {
      const ids = [...(next.sop_rules || []), ...(next.generic_sop_rules || [])].map(rule => rule.id);
      const known = new Set(ids);
      const ordered = next.rule_order.filter(id => known.has(id));
      next = { ...next, rule_order: [...ordered, ...ids.filter(id => !ordered.includes(id))] };
    }
    if (next.workflow && draft) {
      if (next.parse_tier !== draft.parse_tier)
        next.workflow = next.workflow.map((s) =>
          s.action === "parse"
            ? { ...s, parameters: { ...s.parameters, tier: next.parse_tier } }
            : s,
        );
      if (next.parse_version !== draft.parse_version)
        next.workflow = next.workflow.map((s) =>
          s.action === "parse"
            ? {
                ...s,
                parameters: { ...s.parameters, version: next.parse_version },
              }
            : s,
        );
      if (next.extract_tier !== draft.extract_tier)
        next.workflow = next.workflow.map((s) =>
          s.action === "extract"
            ? { ...s, parameters: { ...s.parameters, tier: next.extract_tier } }
            : s,
        );
      if (next.classification_threshold !== draft.classification_threshold)
        next.workflow = next.workflow.map((s) =>
          s.action === "classify"
            ? {
                ...s,
                parameters: {
                  ...s.parameters,
                  minimum_confidence: next.classification_threshold,
                },
              }
            : s,
        );
    }
    setDraft(next);
    dirtyRef.current = true;
    setDirty(true);
    setTest(null);
  };
  const save = async () => {
    if (!draft) return;
    setPending(true);
    try {
      await api("/config/publish", {
        method: "POST",
        body: JSON.stringify({ expected_version: version, payload: draft }),
      });
      notify("Configuration published. New cases use the new version.");
      dirtyRef.current = false;
      setDirty(false);
      await refresh();
    } catch (e) {
      notify(e instanceof Error ? e.message : "Publication failed.", "error");
    } finally {
      setPending(false);
    }
  };
  return (
    <Shell
      title="Configuration"
      subtitle="Manage business behavior here. Every case keeps the version it started with."
      action={
        canEdit && (
          <div className="button-row">
            <button
              className="secondary"
              disabled={!draft || pending || !!policyError}
              onClick={async () => {
                setPending(true);
                try {
                  setTest(
                    await api<Test>("/config/test", {
                      method: "POST",
                      body: JSON.stringify({
                        expected_version: version,
                        payload: draft,
                      }),
                    }),
                  );
                } catch (e) {
                  notify(
                    e instanceof Error ? e.message : "Test failed.",
                    "error",
                  );
                } finally {
                  setPending(false);
                }
              }}
            >
              <FlaskConical size={16} />
              Test settings
            </button>
            <button
              className="primary"
              disabled={
                !dirty ||
                pending ||
                !!policyError ||
                !online ||
                data?.version !== version
              }
              onClick={() => void save()}
            >
              <Save size={16} />
              {pending ? "Working…" : "Publish settings"}
            </button>
          </div>
        )
      }
    >
      {error && <ErrorNotice message={error} retry={() => void refresh()} />}
      {loading && !draft ? (
        <Busy />
      ) : (
        draft && (
          <>
            <fieldset className="configuration-content" disabled={pending}>
              <div className="config-status config-governance-sticky">
                <ShieldCheck size={17} />
                <span>
                  Published configuration <strong>v{version}</strong>
                </span>
                {dirty && <span className="unsaved">Unpublished changes</span>}
                <span className="muted">
                  {canEdit
                    ? "Changes apply to new cases; historical runs stay pinned."
                    : "You have read-only access to configuration."}
                </span>
                {canEdit && dirty && (
                  <div className="button-row" style={{ marginLeft: "auto" }}>
                    <button
                      type="button"
                      className="secondary compact-btn"
                      disabled={pending}
                      onClick={() => setDiscardOpen(true)}
                    >
                      Discard draft
                    </button>
                    <button
                      type="button"
                      className="primary compact-btn"
                      disabled={
                        !dirty ||
                        pending ||
                        !!policyError ||
                        !online ||
                        data?.version !== version
                      }
                      onClick={() => void save()}
                    >
                      <Save size={14} />
                      {pending ? "Working..." : "Publish v" + (version + 1)}
                    </button>
                  </div>
                )}
              </div>
              {dirty && data?.version !== version && (
                <ErrorNotice message="A newer configuration was published while you were editing. Your draft is preserved. Discard it to load the latest version before editing again." />
              )}
              <section className="family-context">
                <label>
                  Document family
                  <select
                    value={family}
                    onChange={(e) => {
                      const next = e.target.value as DocumentFamily;
                      setFamily(next);
                      if (!inFamily(profile, next, draft))
                        setProfile(families[next].profiles[0] || profile);
                    }}
                  >
                    {Object.entries(families).map(([key, value]) => (
                      <option key={key} value={key}>
                        {value.label}
                        {value.enabled === false ? " · Inactive" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <strong>{families[family]?.label} configuration</strong>
                <p>
                  Required documents, profile choices and SOP rules show this
                  family. eKTP and RIPLAY are shared.
                </p>
              </section>
              <nav
                className="tabs settings-tabs settings-navigation"
                aria-label="Configuration sections"
              >
                {(
                  [
                    "families",
                    "flows",
                    "profiles",
                    "rules",
                    "automation",
                    "workflow",
                    ...(canEdit ? ["connector"] : []),
                    ...(["bank_admin", "branch_admin"].includes(
                      user?.role || "",
                    )
                      ? ["access"]
                      : []),
                  ] as Tab[]
                ).map((x) => (
                  <button
                    key={x}
                    aria-label={settingsSections[x].label}
                    aria-pressed={tab === x}
                    className={tab === x ? "active" : ""}
                    onClick={() => setTab(x)}
                  >
                    {(() => {
                      const Icon = settingsSections[x].icon;
                      return (
                        <>
                          <span className="settings-navigation-icon">
                            <Icon size={20} aria-hidden />
                          </span>
                          <span>
                            <strong>{settingsSections[x].label}</strong>
                            <small>{settingsSections[x].detail}</small>
                          </span>
                        </>
                      );
                    })()}
                  </button>
                ))}
              </nav>
              {test && (
                <section className="panel test-results">
                  <div className="section-head">
                    <div>
                      <h2>Configuration test · {test.tested} documents</h2>
                      <p>{test.note}</p>
                    </div>
                  </div>
                  {test.tested ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Document</th>
                          <th>Current result</th>
                          <th>Proposed result</th>
                          <th>Issues</th>
                        </tr>
                      </thead>
                      <tbody>
                        {test.results.map((r, i) => (
                          <tr key={i}>
                            <td>{r.filename}</td>
                            <td>
                              <Badge value={r.before} />
                            </td>
                            <td>
                              <Badge value={r.after} />
                            </td>
                            <td>{r.issues ?? r.error}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <p className="panel-pad muted">
                      Complete a document first to test changes against its
                      stored extraction.
                    </p>
                  )}
                  {test.sop_results?.length ? (
                    <>
                      <h3>Case SOP replay</h3>
                      <table>
                        <thead>
                          <tr>
                            <th>Case</th>
                            <th>PASS</th>
                            <th>FAIL</th>
                            <th>REVIEW</th>
                            <th>Total score</th>
                          </tr>
                        </thead>
                        <tbody>
                          {test.sop_results.map((c) => (
                            <tr key={c.case_id}>
                              <td>{c.customer}</td>
                              {["PASS", "FAIL", "REVIEW"].map((s) => (
                                <td key={s}>
                                  {
                                    c.findings.filter((f) => f.result === s)
                                      .length
                                  }
                                </td>
                              ))}
                              <td>
                                {c.scores.total === null
                                  ? "Unresolved"
                                  : c.scores.total}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </>
                  ) : null}
                </section>
              )}
              {tab === "flows" && (
                <>
                  <p>
                    1. Choose a transaction flow. 2. Confirm its documents and
                    SOP checks. 3. Test and publish using the configuration
                    actions. Uploads use the published version; document
                    profiles are shared across flows.
                  </p>
                  <TransactionFlows
                    family={family}
                    onFamilyChange={setFamily}
                    draft={draft}
                    update={update}
                    canEdit={canEdit}
                  />
                </>
              )}
              {tab === "workflow" && (
                <div className="settings-grid">
                  <section className="panel settings-card">
                    <h2>Processing</h2>
                    <p>
                      Classification verifies the schema after filename
                      grouping.
                    </p>
                    <fieldset disabled={!canEdit}>
                      <label>
                        Provider
                        <select
                          aria-label="Provider"
                          value={draft.provider}
                          onChange={(e) =>
                            update({
                              ...draft,
                              provider: e.target
                                .value as Configuration["provider"],
                            })
                          }
                        >
                          <option value="spider-ai">
                            Spider-AI (recommended) · image-based extraction
                          </option>
                          <option value="gemini">
                            Google Gemini (Native Multimodal) · Pro / Flash 3.8
                          </option>
                          {draft.provider === "llama" && <option value="llama" disabled>Llama removed - select Spider-AI</option>}
                          <option value="fixture">
                            Synthetic fixtures · development only
                          </option>
                        </select>
                      </label>
                      {draft.provider === "spider-ai" && (
                        <p>
                          Spider-AI renders every PDF page to an image and uses
                          the profile’s system, parser and extraction
                          instructions, including saved field descriptions.
                        </p>
                      )}
                      {draft.provider === "gemini" && (
                        <p>
                          Google Gemini uses native multimodal reasoning (Gemini 2.5 Pro or Flash 3.8) to extract structured fields, detect visual document structures, and perform validation checks. Active model and API keys can be managed in the Connector tab.
                        </p>
                      )}
                      {draft.provider === "gemini" && (
                        <p className="info-note">
                          Gemini extraction results are automatically normalized to SQE enterprise schemas, ensuring full compatibility with bounding box crops, SOP audits, and work paper generation.
                        </p>
                      )}
                      {draft.provider === "fixture" && (
                        <div className="fixture-note">
                          Synthetic test values are used. Uploaded content is
                          not extracted in this mode.
                        </div>
                      )}
                      {draft.provider === "spider-ai" && (
                        <p className="info-note">
                          Spider-AI extracts and formats final values in one
                          request. Native document normalization and validation
                          are skipped. Case SOP checks still run.
                        </p>
                      )}
                      <label>
                        Classification confidence threshold
                        <input
                          type="number"
                          min="0"
                          max="1"
                          step=".01"
                          value={draft.classification_threshold}
                          onChange={(e) =>
                            update({
                              ...draft,
                              classification_threshold: Number(e.target.value),
                            })
                          }
                        />
                      </label>
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={draft.maker_checker}
                          onChange={(e) =>
                            update({
                              ...draft,
                              maker_checker: e.target.checked,
                            })
                          }
                        />
                        <span>
                          <strong>Require a different approver</strong>
                          <small>
                            A case maker cannot release their own report.
                          </small>
                        </span>
                      </label>
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={draft.visual_evidence_review ?? true}
                          onChange={(e) =>
                            update({
                              ...draft,
                              visual_evidence_review: e.target.checked,
                            })
                          }
                        />
                        <span>
                          <strong>Visual evidence review (Mandatory human sign-off)</strong>
                          <small>
                            When enabled, visual evidence checks (signatures, stamps, meterai, photo regions) force human visual review regardless of automated detection. When disabled, valid detections evaluate directly to PASS without triggering visual review.
                          </small>
                        </span>
                      </label>
                      <p className="subtext">
                        SOP scoring applies to every document family: PASS earns
                        1 point; FAIL earns 0. Only visual checks can await
                        review. Pending reviews cannot be bypassed and remain in
                        possible points.
                      </p>
                      {/* Phase 3 §3.5.4 — Sequential extraction settings */}
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={draft.sequential_page_extraction ?? true}
                          onChange={(e) =>
                            update({
                              ...draft,
                              sequential_page_extraction: e.target.checked,
                            })
                          }
                        />
                        <span>
                          <strong>Sequential page extraction</strong>
                          <small>
                            Multi-page documents are extracted one page per
                            request with per-page checkpointing and conservative
                            merge. Disable to send all pages in a single
                            request.
                          </small>
                        </span>
                      </label>
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={draft.cross_page_reference ?? true}
                          onChange={(e) =>
                            update({
                              ...draft,
                              cross_page_reference: e.target.checked,
                            })
                          }
                        />
                        <span>
                          <strong>Cross-page reference</strong>
                          <small>
                            Pass extracted values from prior pages as continuity
                            context to subsequent page requests. The model is
                            instructed not to duplicate values unless they also
                            appear on the current page.
                          </small>
                        </span>
                      </label>
                      <label>
                        Report title
                        <input
                          value={draft.report_title}
                          onChange={(e) =>
                            update({ ...draft, report_title: e.target.value })
                          }
                        />
                      </label>
                    </fieldset>
                  </section>
                  <section className="panel settings-card">
                    <h2>Customer filename aliases</h2>
                    <p>
                      Map an abbreviated filename label to a confirmed customer
                      name. Applies within the selected branch and upload batch.
                    </p>
                    <fieldset disabled={!canEdit}>
                      {Object.entries(draft.customer_aliases || {}).map(
                        ([alias, canonical]) => (
                          <div key={alias}>
                            <label>
                              {alias}
                              <input
                                value={canonical}
                                onChange={(e) =>
                                  update({
                                    ...draft,
                                    customer_aliases: {
                                      ...draft.customer_aliases,
                                      [alias]: e.target.value,
                                    },
                                  })
                                }
                              />
                            </label>
                            <button
                              onClick={() => {
                                const aliases = { ...draft.customer_aliases };
                                delete aliases[alias];
                                update({ ...draft, customer_aliases: aliases });
                              }}
                            >
                              Remove alias
                            </button>
                          </div>
                        ),
                      )}
                      <button
                        onClick={() => {
                          const alias = window.prompt(
                            "Filename customer label",
                          );
                          if (alias?.trim())
                            update({
                              ...draft,
                              customer_aliases: {
                                ...draft.customer_aliases,
                                [alias.trim()]: alias.trim(),
                              },
                            });
                        }}
                      >
                        Add alias
                      </button>
                    </fieldset>
                  </section>
                </div>
              )}
              {tab === "families" && (
                <DocumentFamilies
                  key={family}
                  draft={draft}
                  update={update}
                  family={family}
                  select={setFamily}
                  editable={canEdit}
                  navigate={setTab}
                />
              )}
              {tab === "profiles" && (
                <section className="panel settings-card">
                  <ProfileCreate configuration={draft} family={family} editable={canEdit}
                    onCreate={(configuration, id) => { update(configuration); setProfile(id); }} />
                  <div className="profile-selector">
                    <label>
                      Document profile
                      <select
                        value={selectedProfile}
                        onChange={(e) =>
                          setProfile(e.target.value as ProfileName)
                        }
                      >
                        {Object.entries(draft.profiles)
                          .filter(([id]) => inFamily(id, family, draft))
                          .map(([id, p]) => (
                            <option key={id} value={id}>
                              {p.label}
                            </option>
                          ))}
                      </select>
                    </label>
                    <span className="count-pill">
                      {draft.profiles[selectedProfile].columns.length} fields
                    </span>
                  </div>
                  <p>
                    Profiles are shared across transaction flows. Required by:{" "}
                    {Object.values(draft.templates)
                      .filter((flow) => flow.required.includes(selectedProfile))
                      .map((flow) => flow.label)
                      .join(", ") || "No flow currently requires this profile"}
                    . Optional documents may also use this profile.
                  </p>
                  <div
                    className="profile-workflow-tabs"
                    aria-label="Profile editing section"
                  >
                    {[
                      ["fields", "Fields & guidance"],
                      ["instructions", "Document instructions"],
                      ["advanced", "Versions & advanced"],
                    ].map(([value, label]) => (
                      <button
                        key={value}
                        aria-pressed={profileView === value}
                        className={profileView === value ? "active" : ""}
                        onClick={() => setProfileView(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <div hidden={profileView !== "instructions"}>
                    <ProfileExtractionControls
                      profile={draft.profiles[selectedProfile]}
                      editable={canEdit}
                      onChange={(profile) =>
                        update({
                          ...draft,
                          profiles: {
                            ...draft.profiles,
                            [selectedProfile]: profile,
                          },
                        })
                      }
                    />
                    <label>
                      System Instruction · All extraction providers
                      <textarea
                        rows={6}
                        maxLength={30000}
                        disabled={!canEdit}
                        value={
                          draft.profiles[selectedProfile].system_instruction ||
                          ""
                        }
                        placeholder="Shared instructions for document extraction"
                        onChange={(e) =>
                          update({
                            ...draft,
                            profiles: {
                              ...draft.profiles,
                              [selectedProfile]: {
                                ...draft.profiles[selectedProfile],
                                system_instruction: e.target.value,
                              },
                            },
                          })
                        }
                      />
                    </label>
                  </div>
                  <div hidden={profileView !== "advanced"}>
                    <ProfileVersionComparison
                      key={selectedProfile}
                      versions={draft.profile_variants?.[selectedProfile]}
                      current={draft.profiles[selectedProfile]}
                    />
                    <fieldset disabled={!canEdit}>
                      <label>
                        Load a named prompt version into this draft
                        <select
                          value=""
                          onChange={(e) => {
                            const variant =
                              draft.profile_variants?.[selectedProfile]?.[
                                e.target.value
                              ];
                            if (variant)
                              update({
                                ...draft,
                                profiles: {
                                  ...draft.profiles,
                                  [selectedProfile]: structuredClone({
                                    ...variant.profile,
                                    system_instruction:
                                      draft.profiles[selectedProfile]
                                        .system_instruction,
                                  }),
                                },
                              });
                          }}
                        >
                          <option value="">Select a saved version…</option>
                          {Object.entries(
                            draft.profile_variants?.[selectedProfile] || {},
                          ).map(([key, variant]) => (
                            <option key={key} value={key}>
                              {variant.name}
                            </option>
                          ))}
                        </select>
                        <span className="muted">
                          Review the loaded descriptions and prompts below, then
                          publish to apply to new cases. Existing cases retain
                          their configuration.
                        </span>
                      </label>
                      <label>
                        Filename document labels
                        <input
                          value={draft.profiles[selectedProfile].suffixes.join(
                            ", ",
                          )}
                          onChange={(e) =>
                            update({
                              ...draft,
                              profiles: {
                                ...draft.profiles,
                                [selectedProfile]: {
                                  ...draft.profiles[selectedProfile],
                                  suffixes: e.target.value
                                    .split(",")
                                    .map((x) => x.trim())
                                    .filter(Boolean),
                                },
                              },
                            })
                          }
                        />
                        <small>
                          Customer label appears before the suffix.
                          Classification verifies content.
                        </small>
                      </label>
                      <label>
                        Classification description
                        <textarea
                          rows={3}
                          value={
                            draft.profiles[selectedProfile]
                              .classification_description || ""
                          }
                          onChange={(e) =>
                            update({
                              ...draft,
                              profiles: {
                                ...draft.profiles,
                                [selectedProfile]: {
                                  ...draft.profiles[selectedProfile],
                                  classification_description: e.target.value,
                                },
                              },
                            })
                          }
                        />
                      </label>
                      <details>
                        <summary>
                          Advanced: parser and extraction instructions
                        </summary>
                        <label>
                          Parser instructions
                          <small>
                            Used as reading guidance
                            during extraction with either provider.
                          </small>
                          <textarea
                            rows={8}
                            value={draft.profiles[selectedProfile].parse_prompt}
                            onChange={(e) =>
                              update({
                                ...draft,
                                profiles: {
                                  ...draft.profiles,
                                  [selectedProfile]: {
                                    ...draft.profiles[selectedProfile],
                                    parse_prompt: e.target.value,
                                  },
                                },
                              })
                            }
                          />
                        </label>
                        <label>
                          Extraction instructions
                          <textarea
                            rows={8}
                            value={
                              draft.profiles[selectedProfile].system_prompt
                            }
                            onChange={(e) =>
                              update({
                                ...draft,
                                profiles: {
                                  ...draft.profiles,
                                  [selectedProfile]: {
                                    ...draft.profiles[selectedProfile],
                                    system_prompt: e.target.value,
                                  },
                                },
                              })
                            }
                          />
                        </label>
                      </details>
                      <details className="policy-editor">
                        <summary>
                          Advanced profile policy · master lists, dates,
                          thresholds and verification
                        </summary>
                        <p className="muted">
                          The existing engine's policy structure is preserved.
                          Test changes before publishing.
                        </p>
                        <textarea
                          className="code-input"
                          rows={18}
                          value={
                            policyText ||
                            JSON.stringify(
                              draft.profiles[selectedProfile].policy,
                              null,
                              2,
                            )
                          }
                          onChange={(e) => {
                            setPolicyText(e.target.value);
                            try {
                              const policy = JSON.parse(e.target.value);
                              if (
                                !policy ||
                                Array.isArray(policy) ||
                                typeof policy !== "object"
                              )
                                throw new Error("Policy must be an object.");
                              setPolicyError("");
                              update({
                                ...draft,
                                profiles: {
                                  ...draft.profiles,
                                  [selectedProfile]: {
                                    ...draft.profiles[selectedProfile],
                                    policy,
                                  },
                                },
                              });
                            } catch {
                              dirtyRef.current = true;
                              setDirty(true);
                              setPolicyError(
                                "Enter valid JSON policy before publishing.",
                              );
                            }
                          }}
                        />
                        {policyError && <ErrorNotice message={policyError} />}
                      </details>
                    </fieldset>
                    <LocationLearningHistory documentType={selectedProfile} />
                  </div>
                  <div hidden={profileView !== "fields"}>
                    <ProfileSchemaEditor
                      key={`${selectedProfile}-schema-${version}-${draftEpoch}`}
                      profile={draft.profiles[selectedProfile]}
                      editable={canEdit}
                      onChange={(profile) =>
                        update({
                          ...draft,
                          profiles: {
                            ...draft.profiles,
                            [selectedProfile]: profile,
                          },
                        })
                      }
                    />
                    <fieldset disabled={!canEdit}><FieldChecks
                      key={`${selectedProfile}-checks-${version}-${draftEpoch}`}
                      profile={draft.profiles[selectedProfile]}
                      onChange={profile=>update({...draft,profiles:{...draft.profiles,[selectedProfile]:profile}})}
                    /></fieldset>
                    <FieldDescriptionEditor
                      key={`${selectedProfile}-instructions-${version}-${draftEpoch}`}
                      schema={draft.profiles[selectedProfile].schema}
                      columns={draft.profiles[selectedProfile].columns}
                      editable={canEdit}
                      onChange={(schema) =>
                        update({
                          ...draft,
                          profiles: {
                            ...draft.profiles,
                            [selectedProfile]: {
                              ...draft.profiles[selectedProfile],
                              schema,
                            },
                          },
                        })
                      }
                    />
                    <details className="policy-editor">
                      <summary>Schema field catalogue</summary>
                      <div className="field-catalogue">
                        {draft.profiles[selectedProfile].columns.map(
                          ([key, label]) => (
                            <div key={key}>
                              <code>{key}</code>
                              <span>{label}</span>
                            </div>
                          ),
                        )}
                      </div>
                    </details>
                  </div>
                </section>
              )}
              {tab === "automation" && (
                <AutomationEditor
                  draft={draft}
                  update={update}
                  editable={canEdit}
                />
              )}
              {tab === "rules" && (
                <>
                  <section className="panel settings-card" style={{ marginBottom: 16 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                      <div>
                        <h2 style={{ margin: 0 }}>Visual Evidence Review Policy</h2>
                        <p style={{ margin: "4px 0 0", color: "var(--text-muted)", fontSize: "0.875rem" }}>
                          Configure whether SOP visual checks require mandatory human verification or evaluate automatically.
                        </p>
                      </div>
                      <span className="count-pill">
                        {draft.visual_evidence_review ?? true ? "Enforced" : "Automatic / Bypassed"}
                      </span>
                    </div>
                    <div style={{ marginTop: 12 }}>
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={draft.visual_evidence_review ?? true}
                          onChange={(e) =>
                            update({
                              ...draft,
                              visual_evidence_review: e.target.checked,
                            })
                          }
                        />
                        <span>
                          <strong>Enable Visual Evidence Review (Mandatory Human Sign-off)</strong>
                          <small>
                            When <strong>enabled</strong>, visual checks (signatures, stamps, meterai, photo regions) force human review in the Visual Review Workspace regardless of automated detection. When <strong>disabled</strong>, visual checks pass directly if present and valid without blocking the case.
                          </small>
                        </span>
                      </label>
                    </div>
                  </section>
                  <ContextEditor configuration={draft} family={family} editable={canEdit} onChange={update} />
                  <ComparisonUpgrade configuration={draft} version={version} editable={canEdit} onApply={update} family={family} />
                  {family === "forex" && (
                    <ForexSOPPolicyEditor
                      draft={draft}
                      update={(patch) => update({ ...draft, ...patch })}
                      editable={canEdit}
                    />
                  )}
                  <SOPBuilder
                    key={family}
                    family={family}
                    draft={draft}
                    update={update}
                    editable={canEdit}
                  />
                </>
              )}
              {tab === "connector" && canEdit && (
                <>
                  <ConnectorHub />
                </>
              )}
              {tab === "access" && <AccessManager />}
            </fieldset>
            {policyError && (
              <ErrorNotice
                message={
                  policyError +
                  " Open Versions & advanced to correct the profile policy."
                }
              />
            )}
            {dirty && (
              <div
                className="draft-action-bar"
                role="region"
                aria-label="Unpublished configuration changes"
              >
                <div>
                  <strong>Unpublished changes</strong>
                  <p>Your draft is separate from published v{version}.</p>
                </div>
                <div className="button-row">
                  <button
                    className="secondary"
                    disabled={pending}
                    onClick={() => setDiscardOpen(true)}
                  >
                    Discard draft
                  </button>
                  <button
                    className="primary"
                    disabled={
                      pending ||
                      !!policyError ||
                      !online ||
                      data?.version !== version
                    }
                    onClick={() => void save()}
                  >
                    <Save size={16} />
                    {pending ? "Working…" : "Publish configuration"}
                  </button>
                </div>
              </div>
            )}
            {discardOpen && (
              <Modal
                title="Discard unpublished changes?"
                onClose={() => setDiscardOpen(false)}
              >
                <p>
                  This returns all settings to the latest loaded published
                  configuration.
                </p>
                <div className="modal-actions">
                  <button
                    className="secondary"
                    onClick={() => setDiscardOpen(false)}
                  >
                    Keep editing
                  </button>
                  <button
                    className="primary"
                    onClick={() => {
                      if (data) {
                        dirtyRef.current = false;
                        setDraft(structuredClone(data.payload));
                        setVersion(data.version);
                        setDirty(false);
                        setDraftEpoch((previous) => previous + 1);
                        setPolicyError("");
                        setPolicyText("");
                        setTest(null);
                      }
                      setDiscardOpen(false);
                    }}
                  >
                    Discard draft
                  </button>
                </div>
              </Modal>
            )}
          </>
        )
      )}
    </Shell>
  );
}
