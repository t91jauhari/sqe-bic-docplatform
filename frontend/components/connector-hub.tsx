"use client";

import { useState } from "react";
import { useData, usePlatform } from "@/components/platform-provider";
import { api } from "@/lib/api";
import { Busy, ErrorNotice, Modal, Badge } from "@/components/ui";
import {
  Plug,
  Plus,
  CheckCircle2,
  AlertTriangle,
  Play,
  Trash2,
  Edit2,
  Sparkles,
  Server,
  KeyRound,
  ShieldCheck,
  Zap,
} from "lucide-react";
import type { ConnectorItem } from "@/lib/types";

const GEMINI_MODELS = [
  { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro (Recommended — Advanced Banking & Table Analysis)" },
  { id: "gemini-flash-3.8", label: "Gemini Flash 3.8 (Ultra High Throughput & Fast OCR)" },
  { id: "gemini-2.0-flash", label: "Gemini 2.0 Flash (Balanced Multimodal)" },
  { id: "gemini-1.5-pro", label: "Gemini 1.5 Pro (Long Context & Dense Docs)" },
  { id: "gemini-1.5-flash", label: "Gemini 1.5 Flash (Lightweight)" },
  { id: "custom", label: "Custom Model ID (Specify below)" },
];

export function ConnectorHub() {
  const { data: connectors, refresh, error } = useData<ConnectorItem[]>("/connectors", 0);
  const { notify } = usePlatform();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingConnector, setEditingConnector] = useState<ConnectorItem | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; latency_ms?: number; error?: string }>>({});
  const [submitting, setSubmitting] = useState(false);

  // Form states for add/edit modal
  const [name, setName] = useState("");
  const [providerType, setProviderType] = useState<"gemini" | "spider-ai">("gemini");
  const [selectedGeminiModel, setSelectedGeminiModel] = useState("gemini-2.5-pro");
  const [customModelId, setCustomModelId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [temperature, setTemperature] = useState(0.1);
  const [topP, setTopP] = useState(0.95);
  const [maxTokens, setMaxTokens] = useState(16384);
  const [modalTestStatus, setModalTestStatus] = useState<{ testing: boolean; result?: { success: boolean; latency_ms?: number; error?: string } }>({ testing: false });

  const openAddModal = () => {
    setEditingConnector(null);
    setName("");
    setProviderType("gemini");
    setSelectedGeminiModel("gemini-2.5-pro");
    setCustomModelId("");
    setApiKey("");
    setBaseUrl("https://generativelanguage.googleapis.com/v1beta");
    setTemperature(0.1);
    setTopP(0.95);
    setMaxTokens(16384);
    setModalTestStatus({ testing: false });
    setDialogOpen(true);
  };

  const openEditModal = (c: ConnectorItem) => {
    setEditingConnector(c);
    setName(c.name);
    setProviderType(c.provider_type === "gemini" ? "gemini" : "spider-ai");
    const isStandardGemini = GEMINI_MODELS.some((m) => m.id === c.model_id);
    if (c.provider_type === "gemini") {
      if (isStandardGemini) {
        setSelectedGeminiModel(c.model_id);
        setCustomModelId("");
      } else {
        setSelectedGeminiModel("custom");
        setCustomModelId(c.model_id);
      }
    } else {
      setSelectedGeminiModel("custom");
      setCustomModelId(c.model_id);
    }
    setApiKey("");
    setBaseUrl(c.base_url || c.options?.base_url || (c.provider_type === "gemini" ? "https://generativelanguage.googleapis.com/v1beta" : ""));
    setTemperature(Number(c.options?.temperature ?? 0.1));
    setTopP(Number(c.options?.top_p ?? 0.95));
    setMaxTokens(Number(c.options?.max_tokens ?? 16384));
    setModalTestStatus({ testing: false });
    setDialogOpen(true);
  };

  const handleActivate = async (c: ConnectorItem) => {
    try {
      await api(`/connectors/${c.id}/activate`, { method: "POST" });
      notify(`Connector "${c.name}" activated as the primary extraction model.`);
      await refresh();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to activate connector", "error");
    }
  };

  const handleDelete = async (c: ConnectorItem) => {
    if (!confirm(`Are you sure you want to remove connector "${c.name}"?`)) return;
    try {
      await api(`/connectors/${c.id}`, { method: "DELETE" });
      notify("Connector removed.");
      await refresh();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to delete connector", "error");
    }
  };

  const runTest = async (c: ConnectorItem) => {
    setTestingId(c.id);
    try {
      const res = await api<{ success: boolean; latency_ms?: number; error?: string }>("/connectors/test", {
        method: "POST",
        body: JSON.stringify({
          connector_id: c.id,
          provider_type: c.provider_type,
          model_id: c.model_id,
          base_url: c.base_url || c.options?.base_url,
        }),
      });
      setTestResults((prev) => ({ ...prev, [c.id]: res }));
      if (res.success) {
        notify(`Connection successful (${res.latency_ms}ms)`);
      } else {
        notify(res.error || "Connection test failed", "error");
      }
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [c.id]: { success: false, error: err instanceof Error ? err.message : "Network error" },
      }));
    } finally {
      setTestingId(null);
    }
  };

  const testModalConnection = async () => {
    setModalTestStatus({ testing: true });
    const model = providerType === "gemini" && selectedGeminiModel !== "custom" ? selectedGeminiModel : customModelId;
    try {
      const res = await api<{ success: boolean; latency_ms?: number; error?: string }>("/connectors/test", {
        method: "POST",
        body: JSON.stringify({
          provider_type: providerType,
          model_id: model,
          base_url: baseUrl,
          api_key: apiKey || undefined,
          connector_id: editingConnector?.id,
        }),
      });
      setModalTestStatus({ testing: false, result: res });
    } catch (err) {
      setModalTestStatus({
        testing: false,
        result: { success: false, error: err instanceof Error ? err.message : "Connection failed" },
      });
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    const model = providerType === "gemini" && selectedGeminiModel !== "custom" ? selectedGeminiModel : customModelId;

    const payload = {
      name: name.trim() || `${providerType === "gemini" ? "Google Gemini" : "Spider-AI"} - ${model}`,
      provider_type: providerType,
      model_id: model.trim(),
      base_url: baseUrl.trim(),
      api_key: apiKey.trim() || undefined,
      options: {
        base_url: baseUrl.trim(),
        model_id: model.trim(),
        temperature,
        top_p: topP,
        max_tokens: maxTokens,
      },
    };

    try {
      if (editingConnector) {
        await api(`/connectors/${editingConnector.id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        notify(`Connector "${payload.name}" updated.`);
      } else {
        await api("/connectors", {
          method: "POST",
          body: JSON.stringify({ ...payload, is_active: (connectors?.length ?? 0) === 0 }),
        });
        notify(`Connector "${payload.name}" registered.`);
      }
      setDialogOpen(false);
      await refresh();
    } catch (err) {
      notify(err instanceof Error ? err.message : "Failed to save connector", "error");
    } finally {
      setSubmitting(false);
    }
  };

  if (!connectors && !error) return <Busy label="Loading model connectors…" />;

  return (
    <section className="panel settings-card" style={{ marginBottom: "2rem" }}>
      <div className="section-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.25rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Plug className="text-primary" size={20} />
            <h2 style={{ margin: 0 }}>Model Connector Hub</h2>
          </div>
          <p style={{ margin: "0.25rem 0 0", color: "var(--text-muted)", fontSize: "0.875rem" }}>
            Register and manage Vision & LLM inference providers. Seamlessly switch between Google Gemini and Spider-AI with guaranteed zero workflow interruption.
          </p>
        </div>
        <button className="primary" onClick={openAddModal} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
          <Plus size={16} />
          Register Connector
        </button>
      </div>

      {error && <ErrorNotice message={error} />}

      <div style={{ display: "grid", gap: "1rem" }}>
        {connectors?.map((c) => {
          const isGemini = c.provider_type === "gemini" || (c.provider_type as string) === "google-gemini";
          const test = testResults[c.id];
          return (
            <div
              key={c.id}
              style={{
                border: c.is_active ? "2px solid var(--primary)" : "1px solid var(--border)",
                borderRadius: "8px",
                padding: "1.25rem",
                background: c.is_active ? "var(--bg-accent, #f8fafc)" : "var(--bg-panel, #ffffff)",
                display: "flex",
                flexDirection: "column",
                gap: "0.75rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                  {isGemini ? (
                    <Sparkles size={20} style={{ color: "#2563eb" }} />
                  ) : (
                    <Server size={20} style={{ color: "#0891b2" }} />
                  )}
                  <div>
                    <strong style={{ fontSize: "1.05rem" }}>{c.name}</strong>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "0.2rem" }}>
                      <span className="badge-tag" style={{ background: isGemini ? "#dbeafe" : "#cffafe", color: isGemini ? "#1e40af" : "#0e7490", padding: "0.15rem 0.5rem", borderRadius: "4px", fontSize: "0.75rem", fontWeight: 600 }}>
                        {isGemini ? "Google Gemini" : "Spider-AI"}
                      </span>
                      <span style={{ fontSize: "0.825rem", color: "var(--text-muted)" }}>
                        Model: <code>{c.model_id}</code>
                      </span>
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  {c.is_active ? (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", background: "#dcfce7", color: "#166534", padding: "0.25rem 0.65rem", borderRadius: "12px", fontSize: "0.8rem", fontWeight: 600 }}>
                      <CheckCircle2 size={14} /> Active Extraction Provider
                    </span>
                  ) : (
                    <button
                      className="secondary"
                      onClick={() => handleActivate(c)}
                      style={{ fontSize: "0.8rem", padding: "0.3rem 0.6rem" }}
                      title="Set this connector as active default"
                    >
                      <Zap size={13} /> Activate
                    </button>
                  )}
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.3rem",
                      fontSize: "0.75rem",
                      color: c.configured ? "#16a34a" : "#dc2626",
                      fontWeight: 500,
                    }}
                  >
                    <KeyRound size={13} /> {c.configured ? "Key Configured" : "Key Required"}
                  </span>
                </div>
              </div>

              <div style={{ fontSize: "0.825rem", color: "var(--text-muted)", display: "flex", flexWrap: "wrap", gap: "1.5rem", background: "rgba(0,0,0,0.02)", padding: "0.6rem 0.8rem", borderRadius: "6px" }}>
                <div>
                  <strong>Endpoint:</strong> <code>{c.base_url || c.options?.base_url || "Default official API"}</code>
                </div>
                <div>
                  <strong>Temperature:</strong> {String(c.options?.temperature ?? 0.1)}
                </div>
                <div>
                  <strong>Max Tokens:</strong> {String(c.options?.max_tokens ?? 16384)}
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: "0.25rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <button
                    className="secondary"
                    onClick={() => runTest(c)}
                    disabled={testingId === c.id}
                    style={{ fontSize: "0.8rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                  >
                    <Play size={13} />
                    {testingId === c.id ? "Pinging…" : "Test Connection"}
                  </button>

                  {test && (
                    <span style={{ fontSize: "0.8rem", color: test.success ? "#16a34a" : "#dc2626", fontWeight: 600 }}>
                      {test.success ? `🟢 Latency: ${test.latency_ms}ms` : `❌ ${test.error || "Failed"}`}
                    </span>
                  )}
                </div>

                <div style={{ display: "flex", gap: "0.4rem" }}>
                  <button
                    className="secondary"
                    onClick={() => openEditModal(c)}
                    style={{ padding: "0.35rem 0.6rem", fontSize: "0.8rem" }}
                    title="Edit settings"
                  >
                    <Edit2 size={14} /> Edit
                  </button>
                  <button
                    className="secondary"
                    onClick={() => handleDelete(c)}
                    disabled={c.is_active}
                    style={{ padding: "0.35rem 0.6rem", fontSize: "0.8rem", color: c.is_active ? "var(--text-muted)" : "#dc2626" }}
                    title={c.is_active ? "Cannot delete the active connector" : "Delete connector"}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          );
        })}

        {connectors?.length === 0 && (
          <div style={{ textAlign: "center", padding: "2.5rem", border: "1px dashed var(--border)", borderRadius: "8px" }}>
            <Plug size={36} style={{ color: "var(--text-muted)", margin: "0 auto 0.75rem" }} />
            <p style={{ margin: "0 0 0.5rem", fontWeight: 600 }}>No Model Connectors Configured</p>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: "0 0 1rem" }}>
              Add Google Gemini (e.g. Gemini 2.5 Pro / Flash 3.8) or Spider-AI to enable multimodal document processing.
            </p>
            <button className="primary" onClick={openAddModal}>
              Register First Connector
            </button>
          </div>
        )}
      </div>

      {dialogOpen && (
        <Modal
          title={editingConnector ? `Configure ${editingConnector.name}` : "Register New Model Connector"}
          onClose={() => setDialogOpen(false)}
        >
          <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <label>
              Connector Name / Label
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Google Gemini 2.5 Pro (Production Hub)"
              />
            </label>

            <label>
              Provider Engine
              <select
                value={providerType}
                onChange={(e) => {
                  const val = e.target.value as "gemini" | "spider-ai";
                  setProviderType(val);
                  if (val === "gemini") {
                    setBaseUrl("https://generativelanguage.googleapis.com/v1beta");
                    setSelectedGeminiModel("gemini-2.5-pro");
                  } else {
                    setBaseUrl("https://spider.thantowijauhari.com/v1");
                    setSelectedGeminiModel("custom");
                    setCustomModelId("pct-prod-spider/pecut/gemini-3.8-flash-high");
                  }
                }}
              >
                <option value="gemini">Google Gemini (Native Multimodal REST & Vertex AI)</option>
                <option value="spider-ai">Spider-AI / OpenAI-compatible Vision Gateway</option>
              </select>
            </label>

            {providerType === "gemini" ? (
              <>
                <label>
                  Gemini Model Tier
                  <select
                    value={selectedGeminiModel}
                    onChange={(e) => setSelectedGeminiModel(e.target.value)}
                  >
                    {GEMINI_MODELS.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </label>

                {selectedGeminiModel === "custom" && (
                  <label>
                    Custom Gemini Model Identifier
                    <input
                      required
                      value={customModelId}
                      onChange={(e) => setCustomModelId(e.target.value)}
                      placeholder="e.g. gemini-flash-3.8 or fine-tuned model path"
                    />
                  </label>
                )}
              </>
            ) : (
              <label>
                Model ID
                <input
                  required
                  value={customModelId}
                  onChange={(e) => setCustomModelId(e.target.value)}
                  placeholder="e.g. pct-prod-spider/pecut/gemini-3.8-flash-high"
                />
              </label>
            )}

            <label>
              API Key / Credential
              <input
                type="password"
                autoComplete="new-password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={editingConnector?.configured ? "Leave blank to keep existing encrypted key" : "Enter API key"}
              />
            </label>

            <label>
              Base URL / Service Endpoint
              <input
                required
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://generativelanguage.googleapis.com/v1beta"
              />
            </label>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <label>
                Temperature (0.0 - 1.0)
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="2"
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value) || 0.1)}
                />
              </label>
              <label>
                Max Output Tokens
                <input
                  type="number"
                  step="1024"
                  min="1024"
                  max="65536"
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(parseInt(e.target.value, 10) || 16384)}
                />
              </label>
            </div>

            <div style={{ borderTop: "1px solid var(--border)", paddingTop: "0.75rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <button
                type="button"
                className="secondary"
                onClick={testModalConnection}
                disabled={modalTestStatus.testing}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.85rem" }}
              >
                <Play size={13} />
                {modalTestStatus.testing ? "Pinging…" : "Verify Credentials"}
              </button>

              {modalTestStatus.result && (
                <span style={{ fontSize: "0.8rem", color: modalTestStatus.result.success ? "#16a34a" : "#dc2626", fontWeight: 600 }}>
                  {modalTestStatus.result.success ? `🟢 Latency: ${modalTestStatus.result.latency_ms}ms` : `❌ ${modalTestStatus.result.error}`}
                </span>
              )}
            </div>

            <div className="modal-actions" style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "0.5rem" }}>
              <button type="button" className="secondary" onClick={() => setDialogOpen(false)}>
                Cancel
              </button>
              <button className="primary" disabled={submitting}>
                {submitting ? "Saving…" : editingConnector ? "Update Connector" : "Save Connector"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </section>
  );
}
