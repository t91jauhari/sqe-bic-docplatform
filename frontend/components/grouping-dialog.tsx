"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
const EMPTY_URLS: Record<string, string> = {};

export type GroupingRow = {
  filename: string;
  hint: string;
  customer: string;
  explanation: string;
  original_customer: string;
  status: "automatic" | "manual" | "unresolved";
  candidates: string[];
};

export function GroupingDialog({
  rows,
  files,
  previewUrls = EMPTY_URLS,
  busy = false,
  confirmationNote,
  confirmDisabled = false,
  onClose,
  onConfirm,
}: {
  rows: GroupingRow[];
  files: File[];
  previewUrls?: Record<string, string>;
  onClose: () => void;
  onConfirm: (rows: GroupingRow[]) => void;
  busy?: boolean;
  confirmationNote?: ReactNode;
  confirmDisabled?: boolean;
}) {
  const [draft, setDraft] = useState(rows);
  const [extra, setExtra] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [history, setHistory] = useState<GroupingRow[][]>([]);
  const [selected, setSelected] = useState("");
  const [url, setUrl] = useState("");
  const dialog = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.focus();
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  useEffect(() => {
    const file = files.find((f) => f.name === selected);
    if (!file) {
      setUrl(previewUrls[selected] || "");
      return;
    }
    const next = URL.createObjectURL(file);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [selected, files, previewUrls]);
  const groups = Array.from(
    new Set(
      [
        ...draft.map((r) => r.customer).filter(Boolean),
        ...draft.flatMap((r) => r.candidates),
        ...extra,
      ].filter((name): name is string => typeof name === "string" && !!name.trim()),
    ),
  );
  const unresolved = draft.filter((r) => !(r.customer ?? "").trim()).length;
  const move = (filename: string, customer: string) => {
    if (busy) return;
    setHistory((h) => [...h, draft]);
    setDraft((d) =>
      d.map((r) =>
        r.filename === filename
          ? { ...r, customer, status: customer ? "manual" : "unresolved" }
          : r,
      ),
    );
  };
  const card = (customer: string) => (
    <section
      key={customer || "unassigned"}
      className="grouping-card"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const filename = e.dataTransfer.getData("application/x-sqe-document");
        if (draft.some((r) => r.filename === filename))
          move(filename, customer);
      }}
    >
      <h3>{customer || "Unassigned documents"}</h3>
      {draft
        .filter((r) => (r.customer ?? "") === (customer ?? ""))
        .map((r) => (
          <article
            key={r.filename}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData("application/x-sqe-document", r.filename);
              e.dataTransfer.effectAllowed = "move";
            }}
          >
            <strong>{r.filename}</strong>
            <p>
              {r.status === "manual" ? "Assigned by you" : r.explanation || ""}
            </p>
            {!!(r.candidates ?? []).length && (
              <p>Suggested: {(r.candidates ?? []).join(", ")}</p>
            )}
            <label>
              Move to customer
              <select
                value={r.customer}
                onChange={(e) => move(r.filename, e.target.value)}
              >
                <option value="">Unassigned</option>
                {groups.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="secondary"
              onClick={() => setSelected(r.filename)}
            >
              Preview document
            </button>
          </article>
        ))}
      {!draft.some((r) => (r.customer ?? "") === (customer ?? "")) && (
        <p className="muted">Drop a document here.</p>
      )}
    </section>
  );
  return (
    <div className="modal-backdrop">
      <div
        className="modal grouping-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="grouping-title"
        tabIndex={-1}
        ref={dialog}
        onKeyDown={(e) => {
          if (e.key === "Escape" && !busy) {
            e.stopPropagation();
            onClose();
          }
          if (e.key === "Tab") {
            const items = Array.from(
              dialog.current?.querySelectorAll<HTMLElement>(
                'button:not(:disabled), input, select, iframe, [tabindex="0"]',
              ) || [],
            );
            const first = items[0],
              last = items[items.length - 1];
            if (
              e.shiftKey &&
              (document.activeElement === first ||
                document.activeElement === dialog.current)
            ) {
              e.preventDefault();
              last?.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
              e.preventDefault();
              first?.focus();
            }
          }
        }}
      >
        <div className="modal-head">
          <h2 id="grouping-title">Review customer grouping</h2>
          <button className="secondary" disabled={busy} onClick={onClose}>
            Close
          </button>
        </div>
        <p>
          Drag documents to the correct customer, or use “Move to customer”.{" "}
          {unresolved} unassigned.
        </p>
        <div className="grouping-create">
          <label>
            New customer name
            <input
              value={name}
              maxLength={180}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button
            className="secondary"
            disabled={!name.trim()}
            onClick={() => {
              const value = name.trim();
              if (
                !groups.some(
                  (g) => g.toLocaleLowerCase() === value.toLocaleLowerCase(),
                )
              )
                setExtra((g) => [...g, value]);
              setName("");
            }}
          >
            Add customer
          </button>
          <button
            className="secondary"
            disabled={!history.length}
            onClick={() => {
              setDraft(history[history.length - 1]);
              setHistory((h) => h.slice(0, -1));
            }}
          >
            Undo move
          </button>
        </div>
        <div className="grouping-board">
          {card("")}
          {groups.map(card)}
        </div>
        {url && (
          <div className="grouping-preview">
            <strong>{selected}</strong>
            <button className="secondary" onClick={() => setSelected("")}>
              Close preview
            </button>
            {/\.(png|jpe?g)$/i.test(selected) ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img alt={"Document preview: " + selected} src={url} />
            ) : (
              <iframe title={"Document preview: " + selected} src={url} />
            )}
          </div>
        )}
        {confirmationNote}
        <div className="modal-actions">
          <button className="secondary" disabled={busy} onClick={onClose}>
            Cancel
          </button>
          <button
            className="primary"
            disabled={!!unresolved || busy || confirmDisabled}
            onClick={() =>
              onConfirm(draft.map((r) => ({ ...r, status: "manual" })))
            }
          >
            {busy ? "Saving grouping…" : "Confirm grouping"}
          </button>
        </div>
      </div>
    </div>
  );
}
