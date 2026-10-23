"use client";
import { useState } from "react";
import { familyCatalog } from "@/lib/document-family";
import type { Configuration, Profile } from "@/lib/types";

export function ProfileCreate({ configuration, family, editable, onCreate }: {
  configuration: Configuration; family: string; editable: boolean;
  onCreate: (configuration: Configuration, profileId: string) => void;
}) {
  const [id, setId] = useState("");
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  return <details className="panel settings-card">
    <summary><strong>Add document profile</strong></summary>
    <p>Create a profile for this family, then configure its fields and reading instructions. Structural validation checks types and missing required data; business verification belongs in SOP rules.</p>
    {configuration.provider === "fixture" && <p>Select a configured extraction provider before adding a profile. Built-in development fixtures do not cover new document types.</p>}
    <fieldset disabled={!editable || configuration.provider === "fixture"}>
      <div className="form-grid">
        <label>Profile ID<input placeholder="supporting_letter" maxLength={50} value={id} onChange={event => setId(event.target.value)} /></label>
        <label>Profile name<input placeholder="Supporting letter" value={label} maxLength={200} onChange={event => setLabel(event.target.value)} /></label>
        <label>How to recognize this document<textarea value={description} onChange={event => setDescription(event.target.value)} placeholder="Describe its title, layout and distinguishing features." /></label>
      </div>
      {error && <p role="alert">{error}</p>}
      <button type="button" className="secondary" onClick={() => {
        if (!/^[a-z][a-z0-9_]{0,49}$/.test(id) || configuration.profiles[id]) { setError("Use a unique lowercase profile ID."); return; }
        if (!label.trim() || !description.trim()) { setError("Enter a name and recognition description."); return; }
        const instruction = "Extract visible values from the supplied document. Follow the configured field descriptions. Return JSON matching the schema. Never infer missing values.";
        const profile: Profile = { label: label.trim(), validation_adapter: "schema", classification_description: description.trim(),
          parse_prompt: "Read document text and preserve its layout and field boundaries.", system_prompt: instruction, system_instruction: instruction,
          policy: {}, suffixes: [id.replaceAll("_", " "), id], columns: [["reference", "Document reference"]],
          schema: { type: "object", properties: { reference: { type: ["string", "null"], description: "Read the document reference exactly as printed; return null if absent." } }, required: ["reference"] } };
        const catalog = familyCatalog(configuration);
        onCreate({ ...configuration, profiles: { ...configuration.profiles, [id]: profile },
          document_families: { ...configuration.document_families, [family]: { ...catalog[family], profiles: [...catalog[family].profiles, id] } } }, id);
        setId(""); setLabel(""); setDescription(""); setError("");
      }}>Create profile in draft</button>
    </fieldset>
  </details>;
}
