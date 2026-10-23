"use client";
import { useState } from "react";
import { Modal } from "@/components/ui";
import type { Profile } from "@/lib/types";
function flatten(value: unknown, path = ""): Record<string, string> {
  if (value && typeof value === "object" && !Array.isArray(value))
    return Object.fromEntries(
      Object.entries(value).flatMap(([key, child]) =>
        Object.entries(flatten(child, path ? `${path}.${key}` : key)),
      ),
    );
  return {
    [path]:
      typeof value === "string"
        ? value
        : (JSON.stringify(value) ?? "(missing)"),
  };
}
export function ProfileVersionComparison({
  versions,
  current,
}: {
  versions?: Record<string, { name: string; profile: Profile }>;
  current: Profile;
}) {
  const [open, setOpen] = useState(false);
  const original = versions?.["original-v1"]?.profile;
  const enhanced = versions?.["enhanced-v1"]?.profile;
  if (!original || !enhanced)
    return <p>No Original/Enhanced pair is saved for this profile.</p>;
  const before = flatten(original),
    after = flatten(enhanced);
  const changes = [
    ...new Set([...Object.keys(before), ...Object.keys(after)]),
  ].filter((path) => before[path] !== after[path]);
  const matches = Object.values(versions || {})
    .filter((v) => JSON.stringify(v.profile) === JSON.stringify(current))
    .map((v) => v.name);
  return (
    <div className="profile-version-summary">
      <p>
        <strong>Original vs Enhanced: {changes.length} changed entries.</strong>{" "}
        Current draft: {matches.join(" / ") || "Custom or modified version"}.
      </p>
      <button type="button" onClick={() => setOpen(true)}>
        Compare saved versions
      </button>
      {open && (
        <Modal
          className="document-region-modal"
          title="Original V1 vs Enhanced V1"
          onClose={() => setOpen(false)}
        >
          <p>
            Saved snapshots are compared here. Loading a version changes your
            draft; publishing is required for new cases.
          </p>
          {!changes.length ? (
            <p>
              The saved snapshots are identical. This comparison does not
              establish why they became identical; inspect the published
              configuration before replacing either snapshot.
            </p>
          ) : (
            changes.map((path) => (
              <article key={path}>
                <h3>{path}</h3>
                <div className="version-diff-grid">
                  <div>
                    <strong>Original V1</strong>
                    <pre>{before[path] ?? "(missing)"}</pre>
                  </div>
                  <div>
                    <strong>Enhanced V1</strong>
                    <pre>{after[path] ?? "(missing)"}</pre>
                  </div>
                </div>
              </article>
            ))
          )}
        </Modal>
      )}
    </div>
  );
}
