"use client";
import { useState } from "react";
import { useData, usePlatform } from "@/components/platform-provider";
import { api } from "@/lib/api";
import { ConnectorOptions, numericConnectorValues, type NumericConnectorDraft, type NumericConnectorField } from "@/components/connector-options";
import { Busy, ErrorNotice } from "@/components/ui";
type Connector = {
  configured: boolean;
  options: { base_url: string; model_id: string; [key: string]: unknown };
  numeric_fields?: NumericConnectorField[];
  configuration_warning?: string | null;
};
export function SpiderConnectorForm() {
  const { data, error, refresh } = useData<Connector>(
    "/connectors/spider-ai",
    0,
  );
  const { notify } = usePlatform();
  const [key, setKey] = useState("");
  const [base, setBase] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState<NumericConnectorDraft>({});
  if (!data) return error ? <ErrorNotice message={error} /> : <Busy />;
  return (
    <section className="panel settings-card">
      <h2>Spider-AI connector</h2>
      <p>
        {data.configured ? "API key configured" : "API key required"}.
        Credentials are encrypted and never returned to the browser.
      </p>
      {data.configuration_warning && <ErrorNotice message={data.configuration_warning} />}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await api("/connectors/spider-ai", {
              method: "PUT",
              body: JSON.stringify({
                api_key: key || null,
                base_url: base ?? data.options.base_url,
                model_id: model ?? data.options.model_id,
                ...numericConnectorValues(data.numeric_fields || [], data.options, advanced),
              }),
            });
            setKey(""); setBase(null); setModel(null); setAdvanced({});
            await refresh();
            notify(
              "Spider-AI connector saved. Select Spider-AI under Processing defaults and publish.",
            );
          } catch (e) {
            notify(
              e instanceof Error ? e.message : "Unable to save connector",
              "error",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          API key
          <input
            type="password"
            autoComplete="new-password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={
              data.configured
                ? "Leave blank to retain saved key"
                : "Enter API key"
            }
          />
        </label>
        <label>
          OpenAI-compatible base URL
          <input
            value={base ?? data.options.base_url}
            onChange={(e) => setBase(e.target.value)}
          />
        </label>
        <label>
          Model ID
          <input
            value={model ?? data.options.model_id}
            onChange={(e) => setModel(e.target.value)}
          />
        </label>
        <p>
          All PDF pages are rendered to images before classification and
          extraction.
        </p>
        <ConnectorOptions fields={data.numeric_fields || []} options={data.options} draft={advanced} onChange={setAdvanced} title="Advanced request and image settings" />
        <button className="primary" disabled={busy}>
          {busy ? "Saving…" : "Save Spider-AI connector"}
        </button>
      </form>
    </section>
  );
}
