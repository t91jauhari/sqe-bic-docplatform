"use client";
import { useState } from "react";
import { FileText, Search } from "lucide-react";
import type { SchemaNode } from "@/lib/types";

type Entry = { path: string[]; label: string; node: SchemaNode };
function entries(
  node: SchemaNode,
  path: string[] = [],
  label = "Document instructions",
): Entry[] {
  return [
    { path, label, node },
    ...Object.entries(node.properties || {}).flatMap(([name, child]) =>
      entries(
        child,
        [...path, "properties", name],
        label === "Document instructions" ? name : `${label}.${name}`,
      ),
    ),
    ...(node.items
      ? entries(node.items, [...path, "items"], `${label}[]`)
      : []),
  ];
}

export function FieldDescriptionEditor({
  schema,
  columns,
  editable,
  onChange,
}: {
  schema?: SchemaNode;
  columns: [string, string][];
  editable: boolean;
  onChange: (schema: SchemaNode) => void;
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  if (!schema)
    return (
      <p className="muted">
        Refresh configuration to load the field instructions.
      </p>
    );
  const fields = entries(schema);
  const visible = fields.filter((entry) =>
    `${entry.label} ${columns.find(([key]) => key === entry.label.split(".")[0].replace("[]", ""))?.[1] || ""} ${entry.node.description || ""}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const currentPage = Math.min(
    page,
    Math.max(0, Math.ceil(visible.length / 15) - 1),
  );
  const change = (path: string[], description: string) => {
    const next = JSON.parse(JSON.stringify(schema)) as SchemaNode;
    let node: any = next;
    for (const part of path) node = node[part];
    node.description = description;
    onChange(next);
  };
  return (
    <section className="field-instructions">
      <div className="comparison-heading">
        <span className="case-symbol">
          <FileText size={20} />
        </span>
        <div>
          <span className="eyebrow">EXTRACTION INSTRUCTIONS</span>
          <h2>Field descriptions</h2>
        </div>
        <span className="count-pill">{fields.length} instruction entries</span>
      </div>
      <p className="muted">
        Edit the extraction guidance for individual fields and nested
        observations. Publish the configuration to use these instructions for
        new cases. Existing cases retain their configuration version.
      </p>
      <label className="comparison-search">
        <Search size={16} />
        <input
          aria-label="Search field descriptions"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(0);
          }}
          placeholder="Search field name or instruction"
        />
      </label>
      <div className="button-row">
        <button
          disabled={currentPage === 0}
          onClick={() => setPage(currentPage - 1)}
        >
          Previous
        </button>
        <span>
          {visible.length} results · Page {currentPage + 1} /{" "}
          {Math.max(1, Math.ceil(visible.length / 15))}
        </span>
        <button
          disabled={(currentPage + 1) * 15 >= visible.length}
          onClick={() => setPage(currentPage + 1)}
        >
          Next
        </button>
      </div>
      <div className="instruction-list">
        {visible.slice(currentPage * 15, currentPage * 15 + 15).map((entry) => (
          <details
            className="instruction-field"
            key={entry.path.join("/") || "$"}
            open={query ? true : undefined}
          >
            <summary>
              <span>
                <strong>
                  {columns.find(([name]) => name === entry.label)?.[1] ||
                    entry.label}
                </strong>
                <code>{entry.label}</code>
              </span>
              <span className="count-pill">
                {Array.isArray(entry.node.type)
                  ? entry.node.type.join(" / ")
                  : entry.node.type || "object"}
              </span>
            </summary>
            <label>
              Extraction description
              <textarea
                rows={Math.min(
                  10,
                  Math.max(
                    3,
                    Math.ceil((entry.node.description?.length || 0) / 100),
                  ),
                )}
                value={entry.node.description || ""}
                maxLength={20000}
                disabled={!editable}
                onChange={(event) => change(entry.path, event.target.value)}
                placeholder="Describe what to extract, where to locate it and how to handle missing or ambiguous values."
              />
            </label>
          </details>
        ))}
      </div>
      {!visible.length && <p className="muted">No fields match this search.</p>}
    </section>
  );
}
