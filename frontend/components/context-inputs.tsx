"use client";
import type { ContextDefinition, CaseDetail } from "@/lib/types";

export function ContextInputs({ definitions, values, onChange, documents }: {
  definitions: Record<string, ContextDefinition>;
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
  documents: CaseDetail["documents"];
}) {
  return Object.entries(definitions).map(([key, definition]) => {
    const change = (value: string) => onChange({ ...values, [key]: value });
    return <label key={key}>{definition.label}
      {definition.kind === "enum" ? <select aria-label={definition.label}
        value={values[key] || (definition.options?.includes("UNKNOWN") ? "UNKNOWN" : "")}
        onChange={event => change(event.target.value)}>
        {!definition.options?.includes("UNKNOWN") && <option value="">Choose an option</option>}
        {(definition.options || []).map(option => <option key={option}>{option}</option>)}
      </select> : definition.kind === "document_reference" ? <select aria-label={definition.label}
        value={values[key] || ""} onChange={event => change(event.target.value)}>
        <option value="">Automatic when one document applies</option>
        {documents.filter(doc => definition.profiles?.includes(doc.doc_type || "") && doc.status === "COMPLETED")
          .map(doc => <option key={doc.id} value={doc.id}>{doc.filename}</option>)}
      </select> : <input aria-label={definition.label} value={values[key] || ""}
        inputMode={definition.kind === "digits" ? "numeric" : "text"}
        maxLength={definition.max_length || 200} onChange={event => change(event.target.value)} />}
    </label>;
  });
}
