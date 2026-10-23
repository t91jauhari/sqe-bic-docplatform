export type User = {
  id: string;
  email: string;
  name: string;
  role: string;
  organization: string;
  branches: string[];
  active: boolean;
};
export type Branch = { id: string; code: string; name: string };
export type ProfileName = string;
export type SchemaNode = {
  description?: string;
  type?: string | string[];
  properties?: Record<string, SchemaNode>;
  items?: SchemaNode;
  [key: string]: unknown;
};
export type Profile = {
  field_checks?: Record<string, {kind: "text" | "identifier" | "date" | "number" | "choice" | "boolean";
    required?: boolean; minimum_length?: number; maximum_length?: number; digits?: number | null;
    choices?: string[]; normalization?: "literal" | "casefold_whitespace";
    decimal_separator?: "." | ","; thousands_separator?: "." | "," | " " | null; currency?: string | null}>;
  validation_adapter?: "native" | "schema";
  schema?: SchemaNode;
  label: string;
  classification_description: string;
  parse_prompt: string;
  system_prompt: string;
  system_instruction?: string;
  policy: Record<string, unknown>;
  suffixes: string[];
  columns: [string, string][];
};
export type Rule = {
  id: string;
  label: string;
  path: string;
  operator: string;
  severity: "FAIL" | "REVIEW";
  value?: unknown;
  other_path?: string;
};
export type ForexSOPPolicy = {
  version?: number;
  purpose_codes: Record<string, string>;
  purpose_equivalences: Record<string, string[]>;
  address_aliases: Record<string, string>;
};
export type SOPPackages = {
  forex?: {
    summary: SOPSummary;
    atomic_summary: SOPSummary;
    coverage: {
      present: number;
      expected: number;
      complete: boolean;
      missing_field_checks: number;
    };
    checkpoints: {
      rule_id: string;
      label?: string;
      result: string;
      child_rules: string[];
    }[];
  };
};
export type ContextDefinition = {
  label: string;
  kind: "enum" | "text" | "digits" | "document_reference";
  options?: string[];
  profiles?: string[];
  families?: string[];
  max_length?: number;
};
export type Configuration = {
  report_definitions?: Record<string, {timezone: string; bindings: Record<string, {
    source: "document" | "context" | "customer" | "literal"; path?: string | null;
    default?: string | null; fallback_customer?: boolean;
  }>}>;
  context_definitions?: Record<string, ContextDefinition>;
  generic_sop_rules?: {
    id: string; label: string; enabled?: boolean; families: string[];
    report_category: string; source_ref?: string;
    policy: { type?: "compare"; left: string; right: string; normalization?: "literal" | "casefold_whitespace"; pattern?: string | null };
    schema_paths?: Record<string, string>;
    applicability?: { context_key: string; equals: string } | null;
  }[];
  rule_order?: string[];
  rule_scope?: { family_rule_ids: Record<string, string[]> };
  forex_sop_policy?: ForexSOPPolicy;
  document_families?: Record<string, DocumentFamilyConfig>;
  profile_variants?: Partial<
    Record<ProfileName, Record<string, { name: string; profile: Profile }>>
  >;
  customer_aliases?: Record<string, string>;
  workflow?: WorkflowStep[];
  sop_rules?: SOPRule[];
  report_context?: Record<string, string>;
  report_mapping?: Record<string, string>;
  provider: "llama" | "spider-ai" | "fixture";
  parse_tier: string;
  extract_tier: string;
  parse_version: string;
  extract_version: string;
  maker_checker: boolean;
  classification_threshold: number;
  profiles: Record<ProfileName, Profile>;
  templates: Record<
    string,
    {
      label: string;
      required: ProfileName[];
      enabled?: boolean;
      description?: string;
      sop_rule_ids?: string[] | null;
      dataset_id?: string | null;
      document_family?: string;
      report_layout?: string;
      report_context?: Record<string, string>;
    }
  >;
  name_directory: Record<string, unknown>;
  rules: Rule[];
  report_title: string;
  // Phase 1 — Enhanced Grouping Logic & Externalized Message Templates (§3.1, §3.3)
  grouping_prefixes?: string[];
  suffix_aliases?: Record<string, string>;
  sop_message_templates?: Record<string, string>;
  // Phase 2 — Configurable SOP Review Bypass (§3.2)
  sop_review_bypass?: boolean;
  sop_review_bypass_result?: "PASS" | "REVIEW" | "NOT_APPLICABLE";
  // Phase 3 — Multi-Page Sequential Extraction (§3.5)
  sequential_page_extraction?: boolean;
  cross_page_reference?: boolean;
};
export type DocumentFamilyConfig = {
  comparison_policy?: Partial<import("@/components/dataset-policy").DatasetPolicy>;
  report_definition?: NonNullable<Configuration["report_definitions"]>[string] | null;
  label: string;
  description?: string;
  enabled?: boolean;
  profiles: ProfileName[];
  required?: ProfileName[];
  sop_rule_ids?: string[];
  extraction_guidance?: string;
  dataset_id?: string | null;
  report_layout?: string;
  report_context?: Record<string, string>;
  sequential_page_extraction?: boolean;
  cross_page_reference?: boolean;
};
export type ConfigResponse = {
  id: string;
  version: number;
  payload: Configuration;
  can_edit: boolean;
};
export type CaseSummary = {
  id: string;
  reference: string;
  customer: string;
  branch_id: string;
  status: string;
  validation_status: string;
  template: string;
  transaction_flow_label?: string;
  created_at: number;
  updated_at: number;
  documents_count: number;
  completed_count: number;
  missing_documents?: string[];
  created_by: string;
  config_version: number;
};
export type FieldResult = {
  status: string;
  issues: { code: string; severity: string }[];
  metadata: unknown;
  raw_value: unknown;
  normalized_value: unknown;
};
export type Document = {
  id: string;
  filename: string;
  batch_id?: string;
  doc_type: string;
  status: string;
  validation_status: string;
  classification: Record<string, unknown>;
  provider_state: Record<string, unknown>;
  raw: Record<string, unknown>;
  normalized: Record<string, unknown>;
  overrides: Record<string, unknown>;
  validation: {
    processing_mode?: string;
    visual_evidence?: {
      field: string;
      available: boolean;
      observed_present: boolean | null;
      review_status: string;
      page_number?: number;
      revision: string;
      storage_key?: string;
      error?: string;
    }[];
    field_evidence?: {
      field: string;
      value: unknown;
      available: boolean;
      image_available: boolean;
      review_status: string;
      revision: string;
      error?: string;
      crops: { page_number: number; revision: string; storage_key: string }[];
    }[];
    fields?: Record<string, FieldResult>;
    corrections?: unknown[];
  };
  error: string;
  case_id: string;
};
export type Finding = {
  evaluation_type?: "VISUAL" | "DATA";
  reason_code?: string;
  automated_result?: string;
  eligible?: boolean;
  rule_id: string;
  field: string;
  result: string;
  message: string;
  actual?: unknown;
  expected?: unknown;
  evidence?: Record<string, unknown>;
};
export type SOPSummary = {
  earned: number;
  possible: number;
  failed: number;
  pending: number;
  resolved: number;
  percentage: number | null;
  provisional: boolean;
};
export type ReportSnapshot = {
  sop_packages?: SOPPackages;
  sop_summary?: SOPSummary;
  scores?: Record<string, number | null>;
  technical_findings?: Finding[];
  findings: Finding[];
  missing: string[];
  validation_status: string;
  provider: string;
  customer: string;
};
export type CaseReport = {
  id: string;
  version: number;
  state: string;
  created_at: number;
  approved_by: string | null;
  snapshot: ReportSnapshot;
};
export type Timeline = {
  id: string;
  event: string;
  actor: string;
  created_at: number;
  details: Record<string, unknown>;
};
export type CaseDetail = CaseSummary & {
  context_suggestions?: {
    field: string;
    value: string;
    document_id: string;
    source: string;
    conflict: boolean;
    requires_acceptance: boolean;
  }[];
  case_context?: Record<string, unknown>;
  sop_runs?: {
    id: string;
    status: string;
    stage: string;
    error: string;
    snapshot_hash: string;
    created_at: number;
  }[];
  documents: Document[];
  reports: CaseReport[];
  timeline: Timeline[];
  can_write: boolean;
  can_review: boolean;
  maker_checker: boolean;
};
export type InboxItem = {
  assigned_to?: string | null;
  due_at?: number | null;
  overdue?: boolean;
  id: string;
  case_id: string;
  title: string;
  body: string;
  severity: string;
  read: boolean;
  created_at: number;
};
export type Dashboard = {
  cases: number;
  documents: number;
  completed_documents: number;
  processing: number;
  attention: number;
  ready: number;
  unread: number;
  provider: string;
  workflow_driver: string;
  config_version: number;
  recent: CaseSummary[];
};
export type ReportListItem = {
  reference: string;
  transaction_flow: string;
  id: string;
  case_id: string;
  version: number;
  state: string;
  created_at: number;
  customer: string;
  validation_status: string;
  provider: string;
};

export type WorkflowStep = {
  order: number;
  step_id: string;
  action: string;
  enabled: boolean;
  preset: string;
  parameters: Record<string, unknown>;
  timeout_seconds: number;
  read_poll_retries: number;
  on_error: string;
};
export type SOPRule = {
  id: string;
  label: string;
  enabled: boolean;
  source_ref: string;
  scope_basis: string;
  report_category: string;
  operator: string;
  path: string;
  other_path: string;
  currency_path?: string;
  other_currency_path?: string;
  condition_key?: string;
  condition_operator?: string;
  condition_value?: string;
  severity: "FAIL" | "REVIEW";
  comparison_policy?: string;
};
export type FieldCatalog = {
  document: string;
  field: string;
  path: string;
  label: string;
  type: string;
};
export type AutomationCatalog = {
  context_definitions?: Record<string, ContextDefinition>;
  fields: FieldCatalog[];
  scope: {
    source_ref: string;
    scope_basis: string;
    instruction: string;
    included_and_excluded_components: string;
  }[];
  operators: Record<string, string[] | null>;
  context: Record<string, string[]>;
  categories: string[];
};
