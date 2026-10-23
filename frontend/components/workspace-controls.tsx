"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  Search,
  SlidersHorizontal,
  Check,
  RotateCcw,
} from "lucide-react";
import { Modal } from "./ui";

const destinations = [
  {
    href: "/",
    label: "Overview",
    description: "Workload, progress and recent cases",
  },
  {
    href: "/cases",
    label: "Customer cases",
    description: "Find a customer and review their documents",
  },
  {
    href: "/upload",
    label: "Upload documents",
    description: "Start a new document review",
  },
  {
    href: "/inbox",
    label: "Inbox",
    description: "Processing updates and items needing attention",
  },
  {
    href: "/reports",
    label: "Kertas kerja",
    description: "Work papers and final reports",
  },
  {
    href: "/settings",
    label: "Configuration",
    description: "Document profiles, field instructions and rules",
  },
];
type Preferences = {
  density: "comfortable" | "compact";
  sidebar: "expanded" | "compact";
};
const defaults: Preferences = { density: "comfortable", sidebar: "expanded" };

export function WorkspaceControls() {
  const [dialog, setDialog] = useState<"navigate" | "preferences" | null>(null);
  const [query, setQuery] = useState("");
  const [preferences, setPreferences] = useState<Preferences>(defaults);
  const close = useCallback(() => setDialog(null), []);
  const apply = (next: Preferences) => {
    setPreferences(next);
    document.documentElement.dataset.density = next.density;
    document.documentElement.dataset.sidebar = next.sidebar;
    try {
      localStorage.setItem("sqe.workspace.v1", JSON.stringify(next));
    } catch {
      /* Preferences still apply for this visit. */
    }
  };
  useEffect(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem("sqe.workspace.v1") || "null",
      );
      if (saved)
        apply({
          density: saved.density === "compact" ? "compact" : "comfortable",
          sidebar: saved.sidebar === "compact" ? "compact" : "expanded",
        });
    } catch {
      /* Use accessible defaults if browser storage is unavailable. */
    }
    const shortcut = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setQuery("");
        setDialog((current) => (current === "navigate" ? null : "navigate"));
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  return (
    <>
      <button
        className="workspace-search"
        onClick={() => {
          setQuery("");
          setDialog("navigate");
        }}
        aria-label="Quick navigation"
      >
        <Search size={16} />
        <span>Go to…</span>
        <kbd>Ctrl K</kbd>
      </button>
      <button
        className="icon-button workspace-preferences"
        aria-label="Workspace preferences"
        title="Workspace preferences"
        onClick={() => setDialog("preferences")}
      >
        <SlidersHorizontal size={18} />
      </button>
      {dialog === "navigate" && (
        <Modal
          title="Go to your workspace"
          onClose={close}
          className="workspace-dialog"
        >
          <label className="quick-search">
            <Search size={18} />
            <input
              autoFocus
              aria-label="Find a workspace page"
              placeholder="Find cases, configuration, reports…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="destination-list">
            {destinations
              .filter((d) =>
                `${d.label} ${d.description}`
                  .toLowerCase()
                  .includes(query.toLowerCase()),
              )
              .map((d) => (
                <Link key={d.href} href={d.href} onClick={close}>
                  <div>
                    <strong>{d.label}</strong>
                    <p>{d.description}</p>
                  </div>
                  <ArrowUpRight size={18} />
                </Link>
              ))}
          </div>
          {!destinations.some((d) =>
            `${d.label} ${d.description}`
              .toLowerCase()
              .includes(query.toLowerCase()),
          ) && (
            <p className="quick-empty">
              No pages match. Try “cases” or “configuration”.
            </p>
          )}
          <p className="shortcut-hint">
            Tab to move · Enter to open · Esc to close
          </p>
        </Modal>
      )}
      {dialog === "preferences" && (
        <Modal
          title="Make the workspace yours"
          onClose={close}
          className="workspace-dialog"
        >
          <p>
            Adjust how information appears. Preferences are saved in this
            browser.
          </p>
          <fieldset className="preference-group">
            <legend>Information density</legend>
            <div className="preference-options">
              {(["comfortable", "compact"] as const).map((density) => (
                <button
                  key={density}
                  aria-pressed={preferences.density === density}
                  onClick={() => apply({ ...preferences, density })}
                >
                  <span>
                    <strong>
                      {density === "comfortable" ? "Comfortable" : "Compact"}
                    </strong>
                    <small>
                      {density === "comfortable"
                        ? "More space for reading and review"
                        : "More rows visible at once"}
                    </small>
                  </span>
                  {preferences.density === density && <Check size={18} />}
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset className="preference-group">
            <legend>Desktop navigation</legend>
            <div className="preference-options">
              {(["expanded", "compact"] as const).map((sidebar) => (
                <button
                  key={sidebar}
                  aria-pressed={preferences.sidebar === sidebar}
                  onClick={() => apply({ ...preferences, sidebar })}
                >
                  <span>
                    <strong>
                      {sidebar === "expanded"
                        ? "Labels and icons"
                        : "Icons only"}
                    </strong>
                    <small>
                      {sidebar === "expanded"
                        ? "Easy to find every page"
                        : "More room for your documents"}
                    </small>
                  </span>
                  {preferences.sidebar === sidebar && <Check size={18} />}
                </button>
              ))}
            </div>
          </fieldset>
          <div className="preference-footer">
            <button className="text-button" onClick={() => apply(defaults)}>
              <RotateCcw size={14} />
              Reset preferences
            </button>
            <button className="primary" onClick={close}>
              Done
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
