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
const settingsSections: Record<
  Tab,
  {
    label: string;
    detail: string;
    icon: any;
    category: "business" | "engine";
  }
> = {
  access: {
    label: "Branches & Staff Access",
    detail: "Staff accounts, maker-checker roles & branch offices",
    icon: Users,
    category: "business",
  },
  flows: {
    label: "Transaction Requirements",
    detail: "Mandatory documents & checks per banking service",
    icon: Route,
    category: "business",
  },
  rules: {
    label: "SOP Compliance Rules",
    detail: "Regulatory checklists, thresholds & validation policies",
    icon: ListChecks,
    category: "business",
  },
  families: {
    label: "Document Packages",
    detail: "Banking service suites (Forex, Retail, Trade)",
    icon: Layers,
    category: "business",
  },
  profiles: {
    label: "Document Profiles (Schema & OCR)",
    detail: "Field definitions, bounding boxes & prompts",
    icon: ScanLine,
    category: "engine",
  },
  workflow: {
    label: "Engine Processing Defaults",
    detail: "Multimodal AI provider, confidence & page flows",
    icon: SlidersHorizontal,
    category: "engine",
  },
  connector: {
    label: "AI Connectors & Credentials",
    detail: "Spider-AI & Google Gemini model endpoints",
    icon: Plug,
    category: "engine",
  },
  automation: {
    label: "Pipeline Automations",
    detail: "Workflow state machine & retry rules",
    icon: Workflow,
    category: "engine",
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
  const { user, notify, online, devMode, setDevMode } = usePlatform(),
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
  const canManageAccess = ["bank_admin", "branch_admin"].includes(user?.role || "");
  const businessTabs: Tab[] = [
    ...(canManageAccess ? ["access" as Tab] : []),
    "flows",
    "rules",
    "families",
  ];
  const developerTabs: Tab[] = [
    "profiles",
    "workflow",
    ...(canEdit ? ["connector" as Tab] : []),
    "automation",
  ];

  useEffect(() => {
    if (user && canManageAccess && tab === "flows" && !dirty) {
      setTab("access");
    }
  }, [user, canManageAccess]);
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
              <div
                className="config-status config-governance-sticky"
                style={{
                  display: "flex",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: "12px",
                  padding: "12px 18px",
                  background: "#ffffff",
                  border: "1px solid #e2e8f0",
                  borderRadius: "10px",
                  boxShadow: "0 1px 3px 0 rgba(0, 0, 0, 0.05)",
                  marginBottom: "18px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <ShieldCheck size={18} style={{ color: "#16a34a" }} />
                  <span style={{ fontSize: "13px", fontWeight: 700, color: "#0f172a" }}>
                    Published Configuration <strong>v{version}</strong>
                  </span>
                  {dirty ? (
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        background: "#fef3c7",
                        color: "#92400e",
                        padding: "2px 8px",
                        borderRadius: "10px",
                        border: "1px solid #fde68a",
                      }}
                    >
                      Unpublished Draft Changes
                    </span>
                  ) : (
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 600,
                        background: "#dcfce7",
                        color: "#166534",
                        padding: "2px 8px",
                        borderRadius: "10px",
                        border: "1px solid #bbf7d0",
                      }}
                    >
                      Active & In Effect
                    </span>
                  )}
                </div>

                <span
                  className="muted"
                  style={{
                    fontSize: "12px",
                    color: "#64748b",
                    maxWidth: "500px",
                  }}
                >
                  {canEdit
                    ? "Changes apply to newly uploaded customer cases; historical runs remain pinned to their creation snapshot."
                    : "You have read-only access to configuration."}
                </span>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    marginLeft: "auto",
                    flexWrap: "wrap",
                  }}
                >
                  {/* Mode Toggle Button */}
                  <button
                    type="button"
                    className="btn-secondary-action compact-btn"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      fontSize: "12px",
                      padding: "5px 11px",
                      borderRadius: "6px",
                      background: devMode ? "#eff6ff" : "#f8fafc",
                      borderColor: devMode ? "#93c5fd" : "#cbd5e1",
                      color: devMode ? "#1d4ed8" : "#475569",
                      fontWeight: 600,
                    }}
                    onClick={() => {
                      const next = !devMode;
                      setDevMode(next);
                      notify(
                        next
                          ? "Developer & engine tools enabled."
                          : "Simplified operator mode active.",
                      );
                    }}
                    title="Toggle between simplified operator view and technical developer controls"
                  >
                    <SlidersHorizontal size={13} />
                    <span>
                      {devMode ? "Developer Mode (Full)" : "Operator Mode (Clean)"}
                    </span>
                  </button>

                  {canEdit && dirty && (
                    <>
                      <button
                        type="button"
                        className="btn-secondary-action compact-btn"
                        disabled={pending}
                        onClick={() => setDiscardOpen(true)}
                      >
                        Discard Draft
                      </button>
                      <button
                        type="button"
                        className="btn-primary-action compact-btn"
                        style={{
                          background: "#16a34a",
                          borderColor: "#15803d",
                          color: "#ffffff",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                        disabled={
                          !dirty ||
                          pending ||
                          !!policyError ||
                          !online ||
                          data?.version !== version
                        }
                        onClick={() => void save()}
                      >
                        <Save size={13} />
                        <span>{pending ? "Working..." : `Publish v${version + 1}`}</span>
                      </button>
                    </>
                  )}
                </div>
              </div>

              {dirty && data?.version !== version && (
                <ErrorNotice message="A newer configuration was published while you were editing. Your draft is preserved. Discard it to load the latest version before editing again." />
              )}

              {/* Categorized Navigation Bar */}
              <div style={{ marginBottom: "20px" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "10px",
                  }}
                >
                  <span
                    style={{
                      fontSize: "12px",
                      fontWeight: 700,
                      color: "#64748b",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                    }}
                  >
                    Business & Operations
                  </span>
                  {!devMode && (
                    <button
                      type="button"
                      className="text-link"
                      style={{
                        fontSize: "12px",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 4,
                      }}
                      onClick={() => {
                        setDevMode(true);
                        notify("Advanced developer & engine settings revealed.");
                      }}
                    >
                      <SlidersHorizontal size={12} />
                      <span>Show Advanced & Developer Settings (4 tools)</span>
                    </button>
                  )}
                </div>

                <nav
                  className="tabs settings-tabs settings-navigation"
                  aria-label="Business sections"
                  style={{ marginBottom: devMode ? "14px" : "20px" }}
                >
                  {businessTabs.map((x) => {
                    const Icon = settingsSections[x].icon;
                    return (
                      <button
                        key={x}
                        aria-label={settingsSections[x].label}
                        aria-pressed={tab === x}
                        className={tab === x ? "active" : ""}
                        onClick={() => setTab(x)}
                      >
                        <span className="settings-navigation-icon">
                          <Icon size={19} aria-hidden />
                        </span>
                        <span>
                          <strong>{settingsSections[x].label}</strong>
                          <small>{settingsSections[x].detail}</small>
                        </span>
                      </button>
                    );
                  })}
                </nav>

                {devMode && (
                  <div
                    style={{
                      padding: "12px 14px",
                      background: "#f8fafc",
                      border: "1px solid #e2e8f0",
                      borderRadius: "8px",
                      marginTop: "12px",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        marginBottom: "10px",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span
                          style={{
                            fontSize: "12px",
                            fontWeight: 700,
                            color: "#2563eb",
                            textTransform: "uppercase",
                            letterSpacing: "0.05em",
                          }}
                        >
                          Engine & Integrations (Developer Mode)
                        </span>
                        <span
                          style={{
                            fontSize: "11px",
                            background: "#dbeafe",
                            color: "#1e40af",
                            padding: "1px 7px",
                            borderRadius: "10px",
                            fontWeight: 600,
                          }}
                        >
                          Advanced
                        </span>
                      </div>
                      <button
                        type="button"
                        className="text-link"
                        style={{ fontSize: "12px", color: "#64748b" }}
                        onClick={() => {
                          setDevMode(false);
                          if (developerTabs.includes(tab)) setTab("flows");
                          notify("Simplified operator mode active.");
                        }}
                      >
                        Hide Advanced Settings
                      </button>
                    </div>

                    <nav
                      className="tabs settings-tabs settings-navigation"
                      aria-label="Developer sections"
                      style={{ marginBottom: 0 }}
                    >
                      {developerTabs.map((x) => {
                        const Icon = settingsSections[x].icon;
                        return (
                          <button
                            key={x}
                            aria-label={settingsSections[x].label}
                            aria-pressed={tab === x}
                            className={tab === x ? "active" : ""}
                            onClick={() => setTab(x)}
                            style={{
                              borderLeft:
                                tab === x ? "3px solid #2563eb" : undefined,
                            }}
                          >
                            <span
                              className="settings-navigation-icon"
                              style={{ color: "#2563eb" }}
                            >
                              <Icon size={19} aria-hidden />
                            </span>
                            <span>
                              <strong>{settingsSections[x].label}</strong>
                              <small>{settingsSections[x].detail}</small>
                            </span>
                          </button>
                        );
                      })}
                    </nav>
                  </div>
                )}
              </div>

              {/* Contextual Document Suite Switcher - Only shown when relevant */}
              {["flows", "rules", "families", "profiles"].includes(tab) && (
                <section
                  className="family-context"
                  style={{
                    marginBottom: 20,
                    padding: "14px 18px",
                    background: "#f0f9ff",
                    border: "1px solid #bae6fd",
                    borderRadius: "8px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: "12px",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <Layers size={18} style={{ color: "#0284c7", flexShrink: 0 }} />
                    <div>
                      <div
                        style={{
                          fontWeight: 700,
                          fontSize: "13px",
                          color: "#0369a1",
                        }}
                      >
                        Active Banking Service Suite:{" "}
                        <span style={{ color: "#0c4a6e" }}>
                          {families[family]?.label}
                        </span>
                      </div>
                      <p
                        style={{
                          margin: "2px 0 0",
                          fontSize: "12px",
                          color: "#075985",
                        }}
                      >
                        Required documents, profile choices, and regulatory SOP
                        rules below apply to this service. eKTP identity cards and
                        RIPLAY are shared across all suites.
                      </p>
                    </div>
                  </div>

                  <label
                    style={{
                      margin: 0,
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "#0369a1",
                    }}
                  >
                    <span>Switch Service:</span>
                    <select
                      value={family}
                      onChange={(e) => {
                        const next = e.target.value as DocumentFamily;
                        setFamily(next);
                        if (!inFamily(profile, next, draft))
                          setProfile(families[next].profiles[0] || profile);
                      }}
                      style={{
                        padding: "5px 10px",
                        borderRadius: "6px",
                        border: "1px solid #7dd3fc",
                        background: "#ffffff",
                        fontSize: "13px",
                        color: "#0c4a6e",
                        fontWeight: 600,
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
                </section>
              )}
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
                <div>
                  <div style={{ marginBottom: 16 }}>
                    <h2 style={{ fontSize: "16px", fontWeight: 700, margin: "0 0 4px", color: "#0f172a" }}>
                      Transaction Service Requirements
                    </h2>
                    <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                      1. Select a transaction type below. 2. Verify its mandatory document checklist and regulatory SOP checks. 3. Publish to activate.
                    </p>
                  </div>
                  <TransactionFlows
                    family={family}
                    onFamilyChange={setFamily}
                    draft={draft}
                    update={update}
                    canEdit={canEdit}
                  />
                </div>
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
                    <h2>Developer & Maintenance Mode</h2>
                    <p>
                      Control visibility of technical diagnostics, low-level database operations, and developer maintenance drawers.
                    </p>
                    <label className="checkbox-label" style={{ marginTop: 16 }}>
                      <input
                        type="checkbox"
                        checked={devMode}
                        onChange={(e) => {
                          setDevMode(e.target.checked);
                          notify(
                            e.target.checked
                              ? "Developer & maintenance mode enabled."
                              : "Developer & maintenance mode disabled; simplified interface active."
                          );
                        }}
                      />
                      <span>
                        <strong>Enable Developer & Maintenance Tools</strong>
                        <small>
                          When enabled, displays grouping repair, technical schema keys, database reconciliation, and advanced JSON editing. When disabled, these technical tools are hidden to provide a clean, intuitive experience for bank operations.
                        </small>
                      </span>
                    </label>
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
                <div>
                  <div style={{ marginBottom: 16 }}>
                    <h2 style={{ fontSize: "16px", fontWeight: 700, margin: "0 0 4px", color: "#0f172a" }}>
                      Document Packages & Banking Service Suites
                    </h2>
                    <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                      Organize banking services into dedicated document packages (Forex Transactions, Retail Account Opening, Trade Finance).
                    </p>
                  </div>
                  <DocumentFamilies
                    key={family}
                    draft={draft}
                    update={update}
                    family={family}
                    select={setFamily}
                    editable={canEdit}
                    navigate={setTab}
                  />
                </div>
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
                <div>
                  <div style={{ marginBottom: 16 }}>
                    <h2 style={{ fontSize: "16px", fontWeight: 700, margin: "0 0 4px", color: "#0f172a" }}>
                      SOP Compliance & Regulatory Checkpoints
                    </h2>
                    <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                      Configure automated banking audit rules, regulatory thresholds (Bank Indonesia PBI USD 100k eq), and validation policies.
                    </p>
                  </div>
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
                </div>
              )}
              {tab === "connector" && canEdit && (
                <>
                  <ConnectorHub />
                </>
              )}
              {tab === "access" && (
                <div>
                  <div style={{ marginBottom: 16 }}>
                    <h2 style={{ fontSize: "16px", fontWeight: 700, margin: "0 0 4px", color: "#0f172a" }}>
                      Branch Network & Staff Access Control
                    </h2>
                    <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                      Manage physical bank branch offices, assign staff user accounts, and enforce segregated maker-checker compliance roles.
                    </p>
                  </div>
                  <AccessManager />
                </div>
              )}
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
