"use client";
import { useState } from "react";
import { Plus, CheckCircle2, AlertCircle } from "lucide-react";
import type { Profile } from "@/lib/types";

export function ProfileSchemaEditor({
  profile,
  editable,
  onChange,
}: {
  profile: Profile;
  editable: boolean;
  onChange: (profile: Profile) => void;
}) {
  const [key, setKey] = useState("");
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [type, setType] = useState("string");
  return (
    <section className="field-instructions">
      <div className="section-head">
        <div>
          <span className="eyebrow">DOCUMENT FIELDS</span>
          <h2>Profile fields and schema</h2>
        </div>
        <span className="count-pill">{profile.columns.length} fields</span>
      </div>
      <p className="muted">
        Add fields to this document profile, then publish the configuration.
        Existing cases can use the published profile when reprocessing selected
        fields.
      </p>
      <fieldset disabled={!editable}>
        <details className="add-field-panel">
          <summary>
            <Plus size={16} />
            Add a new field<span>Define what this document should capture</span>
          </summary>
          <div className="schema-form-grid">
            <label>
              Field key
              <input
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="ship_to_address"
              />
              <small>
                Unique identifier. Use lowercase letters, numbers and
                underscores.
              </small>
            </label>
            <label>
              Display label
              <input
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Ship To Address"
              />
            </label>
          </div>
          <label>
            Value type
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="string">
                Text — names, addresses, dates and identifiers
              </option>
              <option value="number">
                Number — quantities and numeric values
              </option>
              <option value="boolean">
                Yes / No — presence or selected state
              </option>
            </select>
            <small>
              Keep account numbers and IDs as text to preserve leading zeros.
            </small>
          </label>
          <label>
            Extraction instruction
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Where to find this field, what to capture, and how to handle blank or unclear values"
            />
          </label>
          <button
            type="button"
            className="primary"
            onClick={() => {
              setSuccess("");
              if (
                !/^[a-z][a-z0-9_]{0,79}$/.test(key) ||
                !label.trim() ||
                !description.trim()
              ) {
                setError(
                  "Enter a lowercase field key, label and extraction instruction.",
                );
                return;
              }
              if (profile.schema?.properties?.[key]) {
                setError(
                  "This field key already exists. Edit its instructions above.",
                );
                return;
              }
              onChange({
                ...profile,
                columns: [...profile.columns, [key, label.trim()]],
                schema: {
                  ...profile.schema,
                  properties: {
                    ...profile.schema?.properties,
                    [key]: {
                      type: [type, "null"],
                      description: description.trim(),
                    },
                  },
                },
              });
              setKey("");
              setLabel("");
              setDescription("");
              setError("");
              setSuccess(
                `${label.trim()} added to the draft. Publish the configuration to make it available.`,
              );
            }}
          >
            <Plus size={15} />
            Add profile field
          </button>
        </details>
        {success && (
          <div className="inline-feedback success" role="status">
            <CheckCircle2 size={17} />
            {success}
          </div>
        )}
        <details>
          <summary>Edit existing field types and labels</summary>
          <p className="muted">
            Spider-AI supports editing field types. Native providers retain
            their existing field types and allow added fields. Keep a display
            column for every field.
          </p>
          <button
            type="button"
            onClick={() =>
              setText(
                JSON.stringify(
                  { schema: profile.schema, columns: profile.columns },
                  null,
                  2,
                ),
              )
            }
          >
            Load current schema
          </button>
          <label>
            Schema and display columns
            <textarea
              rows={18}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </label>
          <button
            type="button"
            onClick={() => {
              try {
                const next = JSON.parse(text);
                if (
                  !next.schema?.properties ||
                  typeof next.schema.properties !== "object" ||
                  Array.isArray(next.schema.properties) ||
                  !Array.isArray(next.columns)
                )
                  throw new Error("Include schema.properties and columns.");
                const keys = Object.keys(next.schema.properties);
                if (
                  !next.columns.every(
                    (c: unknown) =>
                      Array.isArray(c) &&
                      c.length === 2 &&
                      c.every((v) => typeof v === "string" && v.trim()),
                  )
                )
                  throw new Error(
                    "Each display column needs a field key and a non-empty label.",
                  );
                const mapped = next.columns.map((c: string[]) => c[0]);
                if (
                  new Set(mapped).size !== mapped.length ||
                  keys.length !== mapped.length ||
                  keys.some((k) => !mapped.includes(k))
                )
                  throw new Error(
                    "Map every schema field to exactly one display column.",
                  );
                onChange({
                  ...profile,
                  schema: next.schema,
                  columns: next.columns,
                });
                setError("");
                setSuccess(
                  "Schema applied to draft. Test and publish the configuration when ready.",
                );
              } catch (e) {
                setError(e instanceof Error ? e.message : "Invalid JSON");
              }
            }}
          >
            Apply schema to draft
          </button>
        </details>
      </fieldset>
      {error && (
        <div className="inline-feedback error" role="alert">
          <AlertCircle size={17} />
          {error}
        </div>
      )}
    </section>
  );
}
