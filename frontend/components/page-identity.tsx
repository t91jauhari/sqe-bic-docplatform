import Link from "next/link";
import {
  ArrowRight,
  LayoutDashboard,
  Inbox,
  Layers,
  FileCheck2,
  Settings,
  UploadCloud,
  ScanLine,
  GitCompareArrows,
} from "lucide-react";

export function pageIdentity(path: string) {
  if (path.endsWith("/comparison"))
    return {
      icon: GitCompareArrows,
      label: "REFERENCE VALIDATION",
      tone: "violet",
      steps: [
        ["Choose sample", "#main-content"],
        ["Compare fields", "#main-content"],
        ["Review exceptions", "#main-content"],
      ],
    };
  if (path.endsWith("/review"))
    return {
      icon: ScanLine,
      label: "VISUAL REVIEW WORKSPACE",
      tone: "teal",
      steps: [
        ["Choose a check", "#review-queue"],
        ["Inspect evidence", "#review-evidence"],
        ["Record decision", "#review-decision"],
      ],
    };
  if (path.startsWith("/cases/"))
    return {
      icon: ScanLine,
      label: "CUSTOMER REVIEW",
      tone: "blue",
      steps: [
        ["Documents", "#case-documents"],
        ["Field review", "#case-fields"],
        ["SOP & report", "#case-sop"],
      ],
    };
  if (path === "/cases")
    return {
      icon: Layers,
      label: "CASE OPERATIONS",
      tone: "blue",
      steps: [
        ["Find a customer", "#main-content"],
        ["Review their case", "#main-content"],
        ["Resolve findings", "/inbox"],
      ],
    };
  if (path === "/inbox")
    return {
      icon: Inbox,
      label: "ACTION CENTER",
      tone: "amber",
      steps: [
        ["Prioritize", "#main-content"],
        ["Review case", "/cases"],
        ["Track resolution", "/reports"],
      ],
    };
  if (path === "/reports" || path.startsWith("/reports/"))
    return {
      icon: FileCheck2,
      label: "REPORTS & EVIDENCE",
      tone: "violet",
      steps: [
        ["Choose a branch", "#main-content"],
        ["Review versions", "#main-content"],
        ["Export evidence", "#main-content"],
      ],
    };
  if (path === "/settings")
    return {
      icon: Settings,
      label: "CONFIGURATION STUDIO",
      tone: "violet",
      steps: [
        ["Configure", "#main-content"],
        ["Test draft", "#main-content"],
        ["Publish version", "#main-content"],
      ],
    };
  if (path === "/upload")
    return {
      icon: UploadCloud,
      label: "DOCUMENT INTAKE",
      tone: "teal",
      steps: [
        ["Choose a flow", "#main-content"],
        ["Add documents", "#main-content"],
        ["Confirm grouping", "#main-content"],
      ],
    };
  return {
    icon: LayoutDashboard,
    label: "OPERATIONS COMMAND CENTER",
    tone: "teal",
    steps: [
      ["Upload documents", "/upload"],
      ["Review cases", "/cases"],
      ["Prepare reports", "/reports"],
    ],
  };
}

export function PagePath({ path }: { path: string }) {
  const meta = pageIdentity(path);
  // An orientation guide, not a claim that these workflow steps have completed.
  return (
    <div className="page-path">
      <span>WORKSPACE GUIDE</span>
      <ol>
        {meta.steps.map(([label, href], i) => (
          <li key={label}>
            {href === "#main-content" ? (
              <span>
                <b>{String(i + 1).padStart(2, "0")}</b>
                {label}
              </span>
            ) : (
              <Link href={href}>
                <b>{String(i + 1).padStart(2, "0")}</b>
                {label}
              </Link>
            )}
            {i < 2 && <ArrowRight aria-hidden size={13} />}
          </li>
        ))}
      </ol>
    </div>
  );
}
