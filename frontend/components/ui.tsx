"use client";
import { createPortal } from "react-dom";
import { useEffect, useRef } from "react";
import { X, LoaderCircle, ArrowUpRight, FileText } from "lucide-react";
import Link from "next/link";
import type { CaseSummary } from "@/lib/types";
import { StatusBadge, SopBadge } from "@/components/status";
import { formatWhen } from "@/lib/time";

export function Badge({ value }: { value: string }) {
  const color = [
    "PASS",
    "MATCH",
    "FUZZY_MATCH",
    "READY",
    "COMPLETED",
    "FINAL",
    "FINALIZED",
  ].includes(value)
    ? "good"
    : [
          "FAIL",
          "MISMATCH",
          "VALUE_MISSING",
          "DOCUMENT_MISSING",
          "ERROR",
          "PROCESSING_ERROR",
          "SOP_ERROR",
        ].includes(value)
      ? "bad"
      : [
            "REVIEW",
            "UNMAPPED",
            "NEEDS_REVIEW",
            "NEEDS_CLASSIFICATION",
            "WAITING_DOCUMENTS",
          ].includes(value)
        ? "warn"
        : "neutral";
  return (
    <span className={"badge " + color}>
      {value.replaceAll("_", " ").toLowerCase()}
    </span>
  );
}
export function Busy({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="busy" role="status">
      <LoaderCircle size={18} className="spin" />
      {label}
    </div>
  );
}
export function Empty({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <FileText size={24} />
      </div>
      <h3>{title}</h3>
      <p>{detail}</p>
      {action}
    </div>
  );
}
export function ErrorNotice({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="error-notice" role="alert">
      <span>{message}</span>
      {retry && <button onClick={retry}>Retry</button>}
    </div>
  );
}
export function formatDate(value: number) {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Jakarta",
  }).format(new Date(value * 1000));
}
export function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Missing";
  if (typeof value === "boolean") return value ? "Present" : "Absent";
  if (Array.isArray(value))
    return value.length ? value.map(display).join("; ") : "None selected";
  if (typeof value !== "object") return String(value);
  const v = value as Record<string, unknown>;
  if ("selected" in v) {
    const parts: string[] = [];
    if (Array.isArray(v.selected) ? v.selected.length : v.selected) parts.push(display(v.selected));
    if (v.other_description) parts.push(display(v.other_description));
    if (v.raw != null && v.raw !== "") {
      const raw = display(v.raw), currency = String(v.currency || "");
      parts.push(currency && !raw.toLowerCase().includes(currency.toLowerCase()) ? `${currency} ${raw}` : raw);
    }
    return parts.length ? parts.join(" · ") : display(v.selected);
  }
  if ("currency_raw" in v && "amount_raw" in v) {
    const amount =
      [v.currency_raw, v.amount_raw]
        .filter((part) => part != null && part !== "")
        .map(display)
        .join(" ") || "Missing";
    return amount !== "Missing" && v.unit_raw
      ? `${amount}/${display(v.unit_raw)}`
      : amount;
  }
  if ("formatted_date" in v) return display(v.formatted_date);
  if ("table_complete" in v && Array.isArray(v.items)) {
    const items = v.items.map(display).join("; ") || "Missing";
    return (v.table_complete === false ? "Incomplete table · " : "") + items;
  }
  if ("name" in v || "address" in v || "phone" in v) {
    const parts = [v.name, v.branch, v.address, v.phone].filter(
      (part) => part != null && part !== "",
    );
    if (parts.length) return parts.map(display).join(" · ");
    if ("full_text" in v) return display(v.full_text);
  }
  if ("full_text" in v) return display(v.full_text);
  if ("page_count" in v && Array.isArray(v.pages)) {
    return (
      v.pages
        .map((page) => {
          if (page == null || typeof page !== "object") return display(page);
          const item = page as Record<string, unknown>;
          return `Page ${item.page_number ?? "?"}: ${display(item.footer_present)}`;
        })
        .join(" · ") || "Missing"
    );
  }
  if ("place" in v && "date" in v) {
    let date = display(v.date);
    const match =
      typeof v.date === "string" && /^(\d{2})-(\d{2})-(\d{4})$/.exec(v.date);
    const months = [
      "Januari",
      "Februari",
      "Maret",
      "April",
      "Mei",
      "Juni",
      "Juli",
      "Agustus",
      "September",
      "Oktober",
      "November",
      "Desember",
    ];
    if (match && Number(match[2]) >= 1 && Number(match[2]) <= 12)
      date = `${Number(match[1])} ${months[Number(match[2]) - 1]} ${match[3]}`;
    return `${display(v.place)} — ${date}`;
  }
  const presence =
    "present" in v ? "present" : "stamp_present" in v ? "stamp_present" : null;
  if (presence) {
    const parts = [v[presence] == null ? "Needs review" : display(v[presence])];
    if ("complete" in v)
      parts.push(
        v.complete === true
          ? "Complete"
          : v.complete === false
            ? "Incomplete"
            : "Completeness needs review",
      );
    if (v.text) parts.push(String(v.text));
    for (const key of ["comparison_status", "signature_match"])
      if (v[key] != null)
        parts.push(`${key.replaceAll("_", " ")}: ${display(v[key])}`);
    return parts.join(" · ");
  }
  if ("raw" in v)
    return v.currency != null &&
      v.currency !== "" &&
      v.raw != null &&
      v.raw !== ""
      ? `${display(v.currency)} ${display(v.raw)}`
      : display(v.raw);
  const hidden = new Set([
    "evidence",
    "citation",
    "confidence",
    "extraction_confidence",
    "bounding_boxes",
    "page_dimensions",
  ]);
  return (
    Object.entries(v)
      .filter(([key]) => !hidden.has(key))
      .map(([key, val]) => `${key.replaceAll("_", " ")}: ${display(val)}`)
      .join(" · ") || "Missing"
  );
}
export function CaseTable({ cases }: { cases: CaseSummary[] }) {
  return (
    <div className="table-scroll">
      <table className="case-table">
        <thead>
          <tr>
            <th>Customer / case</th>
            <th>Progress</th>
            <th>Workflow</th>
            <th>SOP</th>
            <th>Updated</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.id}>
              <td>
                <Link className="customer-link" href={"/cases/" + c.id}>
                  {c.customer}
                </Link>
                <div className="subtext">
                  {c.reference} · {c.transaction_flow_label || c.template}
                </div>
              </td>
              <td>
                <div className="mini-progress">
                  <span
                    style={{
                      width:
                        (c.documents_count
                          ? (c.completed_count / c.documents_count) * 100
                          : 0) + "%",
                    }}
                  />
                </div>
                <div className="subtext">
                  {c.completed_count} / {c.documents_count}
                  {c.missing_documents?.length
                    ? " · Missing: " + c.missing_documents.join(", ")
                    : c.documents_count
                      ? " · complete"
                      : ""}
                </div>
              </td>
              <td>
                <StatusBadge value={c.status} />
              </td>
              <td>
                <SopBadge value={c.validation_status} />
              </td>
              <td
                className="muted"
                title={new Date(c.updated_at * 1000).toISOString()}
              >
                {formatWhen(c.updated_at)}
              </td>
              <td>
                <Link href={"/cases/" + c.id} aria-label={"Open " + c.customer}>
                  <ArrowUpRight size={18} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function Modal({
  className = "",
  title,
  onClose,
  children,
}: {
  className?: string;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const focusable = () =>
      Array.from(
        ref.current?.querySelectorAll<HTMLElement>(
          "button,input,textarea,select,a[href]",
        ) || [],
      ).filter((x) => !x.hasAttribute("disabled"));
    focusable()[0]?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const list = focusable();
        if (e.shiftKey && document.activeElement === list[0]) {
          e.preventDefault();
          list[list.length - 1]?.focus();
        } else if (
          !e.shiftKey &&
          document.activeElement === list[list.length - 1]
        ) {
          e.preventDefault();
          list[0]?.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [onClose]);
  if (typeof document === "undefined") return null;
  return createPortal(
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        className={`modal ${className}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="modal-head">
          <h2 id="modal-title">{title}</h2>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="Close dialog"
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
