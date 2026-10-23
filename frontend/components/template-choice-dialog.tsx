"use client";
import { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";

export type TemplateOption = {
  id: string;
  label: string;
  description?: string;
};

/** Full-screen confirmation step: the user explicitly picks the processing
 *  flow for the batch before upload. Replaces a small default-preselected
 *  dropdown so the wrong schema can't be applied unnoticed. */
export function TemplateChoiceDialog({
  options,
  selected,
  busy = false,
  onConfirm,
  onClose,
}: {
  options: TemplateOption[];
  selected: string;
  busy?: boolean;
  onConfirm: (template: string) => void;
  onClose: () => void;
}) {
  const [choice, setChoice] = useState(selected);
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
  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onKeyDown={(e) => {
        if (e.key === "Escape" && !busy) {
          e.stopPropagation();
          onClose();
        }
      }}
    >
      <div
        className="modal template-choice-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="template-choice-title"
        tabIndex={-1}
        ref={dialog}
      >
        <div className="modal-head">
          <h2 id="template-choice-title">Choose the processing flow</h2>
          <button className="secondary" disabled={busy} onClick={onClose}>
            Close
          </button>
        </div>
        <p>
          Every document in this batch is processed with the selected flow —
          its schema, SOP rules and classification. Pick the one that matches
          these documents.
        </p>
        <div className="template-choice-grid" role="radiogroup" aria-label="Processing flow">
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={choice === option.id}
              className={
                "template-choice-card" +
                (choice === option.id ? " selected" : "")
              }
              disabled={busy}
              onClick={() => setChoice(option.id)}
            >
              <span className="template-choice-check" aria-hidden="true">
                {choice === option.id && <Check size={14} />}
              </span>
              <strong>{option.label}</strong>
              {option.description && <p>{option.description}</p>}
            </button>
          ))}
        </div>
        <div className="modal-actions">
          <button className="secondary" disabled={busy} onClick={onClose}>
            Cancel
          </button>
          <button
            className="primary"
            disabled={!choice || busy}
            onClick={() => onConfirm(choice)}
          >
            Use this flow
          </button>
        </div>
      </div>
    </div>
  );
}
