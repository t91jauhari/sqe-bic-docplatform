"""Document-only SOP contracts. No external lookups or inferred authenticity."""

import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

DATA = Path(__file__).with_name("config_data")
CATEGORIES = (
    "DATA_COMPLETION",
    "CUSTOMER_SIGNATURE",
    "DOCUMENT_COMPLETION",
    "OFFICER_REVIEW_APPROVAL",
)
from .configuration.contexts import enum_options

CONTEXT = enum_options({})  # Compatibility export for older callers.
OPERATORS = {
    "account_check": None,
    "required": None,
    "match_exact": {"text", "identifier"},
    "match_address": {"text"},
    "match_purpose": {"text"},
    "match_money": {"decimal"},
    "date_equal": {"date"},
    "date_on_or_after": {"date"},
    "document_required": None,
    "signature_visible": {"signature_region"},
    "signature_visual_consistency": {"signature_region"},
    "all_pages_marked": {"page_observations"},
    "stamp_present": {"stamp_region"},
    "stamp_placement": {"stamp_region"},
    "policy_review": None,
    "invoice_linkage": None,
}
MATCHES = {
    "invoice_linkage",
    "match_exact",
    "match_address",
    "match_purpose",
    "match_money",
    "date_equal",
    "date_on_or_after",
    "signature_visual_consistency",
}
ACTIONS = [
    "upload",
    "group_by_customer",
    "classify",
    "parse",
    "extract",
    "normalize_validate",
    "case_sop",
    "render_report",
    "notify",
]


def catalog(name):
    return json.loads((DATA / (name + ".json")).read_text(encoding="utf-8"))


def defaults():
    from .configuration.seed_catalog import seed_value

    return {
        "workflow": catalog("workflow"),
        "sop_rules": catalog("rules"),
        **seed_value("bootstrap.sop"),
        "report_mapping": {c: c for c in CATEGORIES},
    }


def fields():
    from .account_opening_sop import fields as account_fields

    return catalog("fields") + account_fields()


def approved_scope():
    from .account_opening_sop import sources

    return catalog("scope") + sources()


def validate_business(cfg):
    if "workflow" not in cfg:
        return  # Immutable historical versions retain legacy execution.
    workflow = cfg["workflow"]
    if not isinstance(workflow, list) or len(workflow) != len(ACTIONS):
        raise ValueError("Workflow must contain the nine registered actions.")
    ordered = sorted(workflow, key=lambda s: s.get("order", 0))
    if [s.get("action") for s in ordered] != ACTIONS or len(
        {s.get("step_id") for s in ordered}
    ) != len(ACTIONS):
        raise ValueError("Workflow dependency order or step IDs are invalid.")
    for s in workflow:
        if s.get("enabled") is not True:
            raise ValueError(
                "Required pipeline steps cannot be disabled; configure their policies instead."
            )
        if (
            not isinstance(s.get("timeout_seconds"), int)
            or not 1 <= s["timeout_seconds"] <= 3600
        ):
            raise ValueError("Step timeout must be 1–3600 seconds.")
        if (
            not isinstance(s.get("read_poll_retries"), int)
            or not 0 <= s["read_poll_retries"] <= 5
        ):
            raise ValueError(
                "Read retry count must be 0–5; paid creation is never retried."
            )
        allowed = catalog("workflow")[ACTIONS.index(s["action"])]
        if s["action"] not in {"classify", "parse", "extract"} and (
            s["timeout_seconds"] != allowed["timeout_seconds"]
            or s["read_poll_retries"] != allowed["read_poll_retries"]
        ):
            raise ValueError(
                "Only provider polling deadlines/retries are configurable in this preset."
            )
        if (
            s.get("preset") != allowed["preset"]
            or s.get("on_error") != allowed["on_error"]
        ):
            raise ValueError("Select a registered preset and error policy.")
        params = s.get("parameters")
        if not isinstance(params, dict) or set(params) != set(allowed["parameters"]):
            raise ValueError("Unknown or missing workflow parameter.")
        # Parameters supported by this implementation are explicit; never accept a no-op switch.
        for k, v in params.items():
            if k == "minimum_confidence":
                if (
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not 0 <= v <= 1
                ):
                    raise ValueError("Invalid classification confidence.")
            elif k == "tier":
                if v not in {"agentic", "agentic_plus", "cost_effective"}:
                    raise ValueError("Invalid step tier.")
            elif k == "version":
                if not isinstance(v, str) or not v.strip():
                    raise ValueError("Invalid provider version.")
            elif k in {"max_files", "max_mb"}:
                if type(v) is not int or not 1 <= v <= (
                    100 if k == "max_files" else 30
                ):
                    raise ValueError("Upload bounds exceeded.")
            elif k == "formats":
                if (
                    not isinstance(v, list)
                    or not v
                    or not set(v) <= {"pdf", "xlsx", "json"}
                ):
                    raise ValueError("Invalid report formats.")
            elif v != allowed["parameters"][k]:
                raise ValueError(
                    f"{s['action']}.{k}: this invariant is fixed by the supported preset."
                )
    steps = {s["action"]: s for s in workflow}
    if any(
        cfg.get(k) != steps[a]["parameters"][p]
        for k, a, p in [
            ("parse_tier", "parse", "tier"),
            ("extract_tier", "extract", "tier"),
            ("parse_version", "parse", "version"),
            ("classification_threshold", "classify", "minimum_confidence"),
        ]
    ):
        raise ValueError("Processing defaults must match their workflow parameters.")
    registry = {f["path"]: f for f in fields()}
    sources = {s["source_ref"]: s["scope_basis"] for s in approved_scope()}
    ids = set()
    for r in cfg.get("sop_rules", []):
        if (
            not isinstance(r.get("id"), str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", r["id"])
            or r["id"] in ids
        ):
            raise ValueError("SOP rule IDs must be unique safe identifiers.")
        ids.add(r["id"])
        if (
            type(r.get("enabled")) is not bool
            or r.get("source_ref") not in sources
            or r.get("scope_basis") != sources[r["source_ref"]]
        ):
            raise ValueError(
                f"{r['id']}: only approved YES sources and SOP3 system sources are allowed."
            )
        op = r.get("operator")
        if (
            op not in OPERATORS
            or r.get("report_category")
            not in (*CATEGORIES, "DOCUMENT_VERIFICATION", "OBSERVATIONS")
            or r.get("severity") not in {"FAIL", "REVIEW"}
        ):
            raise ValueError(f"{r['id']}: invalid operator/category/severity.")
        for key in ["path"] + (
            ["other_path"]
            if op in MATCHES or op == "account_check" and r.get("other_path")
            else []
        ):
            f = registry.get(r.get(key))
            if f is None or (OPERATORS[op] and f["type"] not in OPERATORS[op]):
                raise ValueError(
                    f"{r['id']}: unknown field or incompatible operator: {r.get(key)}."
                )
        if op == "match_money":
            for k in ("currency_path", "other_currency_path"):
                if registry.get(r.get(k), {}).get("type") != "text":
                    raise ValueError(f"{r['id']}: currency companion is required.")
        if op == "account_check":
            try:
                from .configuration.account_policies import parse_policy

                account_policy = parse_policy(r["comparison_policy"])
                if account_policy.get("supporting_paths"):
                    from .configuration.sop_policies import (
                        VisualPolicy,
                        validate_visual_binding,
                    )

                    for evidence_path in account_policy["supporting_paths"]:
                        if evidence_path.split(".", 1)[0] not in {
                            r["path"].split(".", 1)[0],
                            r.get("other_path", "").split(".", 1)[0],
                        }:
                            raise ValueError(
                                "Signature evidence must come from the two compared document profiles."
                            )
                        validate_visual_binding(
                            cfg["profiles"],
                            evidence_path,
                            VisualPolicy(
                                type="visual",
                                check="presence",
                                left=evidence_path,
                                right=evidence_path,
                            ),
                        )
                if (
                    account_policy.get("trigger")
                    and account_policy["trigger"]["path"] not in registry
                ):
                    raise ValueError("Unknown conditional source field")
                if (
                    not isinstance(account_policy, dict)
                    or not r["source_ref"].startswith("AO:")
                    or account_policy.get("kind")
                    not in {
                        "field",
                        "document",
                        "match",
                        "identity_name",
                        "gender",
                        "birth",
                        "nik_birth",
                        "conditional_edd",
                        "conditional_bo",
                        "conditional_visit",
                        "conditional_signature",
                        "conditional_survey",
                        "manual",
                    }
                ):
                    raise ValueError("Unknown Account Opening check")
                for pair in account_policy.get("companion_matches", []):
                    if not isinstance(pair, dict) or any(
                        pair.get(key) not in registry for key in ("path", "other_path")
                    ):
                        raise ValueError("Unknown Account Opening companion field")
                pattern = account_policy.get("required_pattern")
                if pattern is not None:
                    if not isinstance(pattern, str) or len(pattern) > 200:
                        raise ValueError("Invalid literal format pattern")
                    re.compile(pattern)
                allowed = account_policy.get("allowed_values")
                if allowed is not None and (
                    not isinstance(allowed, list)
                    or not allowed
                    or any(not isinstance(value, str) or not value for value in allowed)
                ):
                    raise ValueError("Invalid approved code list")
                if account_policy.get("kind") == "identity_name" and (
                    r["path"] != "ektp.name"
                    or r.get("other_path") != "account_opening_form.customer_name"
                    or account_policy.get("require_two_signatures") is not True
                ):
                    raise ValueError(
                        "Identity abbreviation review requires both official customer signature sources"
                    )
            except (ValueError, TypeError, KeyError, re.error):
                raise ValueError("Invalid Account Opening check policy")
        condition = r.get("condition_operator", "always")
        if condition not in {"always", "equals", "in", "document_present"}:
            raise ValueError("Invalid condition operator.")
        if condition in {"equals", "in"}:
            key = r.get("condition_key")
            values = r.get("condition_value")
            values = (
                values.split(",")
                if isinstance(values, str) and condition == "in"
                else [values]
            )
            if key not in enum_options(cfg) or not set(values) <= set(
                enum_options(cfg)[key]
            ):
                raise ValueError("Invalid case-context condition.")
        if condition == "document_present" and r.get("condition_value") not in {
            f["document"] for f in fields()
        }:
            raise ValueError("Unknown conditional document.")
    if cfg.get("report_mapping") != {c: c for c in CATEGORIES}:
        raise ValueError(
            "Report categories must map to the four approved score columns."
        )


def value_at(documents, path, context=None):
    from .valas_resolution import is_valas_prefix, get_case_valas_document, resolve_valas_path

    parts = path.split(".")
    matches = [
        d for d in documents if d["doc_type"] == parts[0] and d["status"] == "COMPLETED"
    ]
    if len(matches) != 1 and is_valas_prefix(parts[0]):
        valas_doc, valas_type = get_case_valas_document(documents, context)
        if valas_doc:
            remapped_path, applicable, _ = resolve_valas_path(path, valas_type, context)
            if applicable:
                matches = [valas_doc]
                parts = remapped_path.split(".")
    if len(matches) != 1:
        return None, matches
    value = matches[0]["normalized"]
    for key in parts[1:]:
        if not isinstance(value, dict):
            return None, matches
        value = value.get(key)
    return value, matches


def normalize(value):
    return " ".join(str(value).split()).casefold()


def evaluate(documents, cfg, context):
    findings = []
    types = {d["doc_type"] for d in documents}
    templates = cfg.get("sop_message_templates", {})
    visual_review_enabled = cfg.get("visual_evidence_review", True) and not cfg.get("sop_review_bypass", False)

    def tpl(key):
        """Look up a message template with graceful fallback to the hardcoded default."""
        from app.native_profiles import SOP_MESSAGE_TEMPLATES

        return templates.get(key, SOP_MESSAGE_TEMPLATES.get(key, ""))

    for r in cfg.get("sop_rules", []):
        if not r["enabled"]:
            continue
        if r.get("operator") in {
            "configured_compare",
            "configured_visual",
            "configured_date",
            "configured_money",
        }:
            from .configuration.generic_sop import evaluate_generic

            findings.append(evaluate_generic(r, documents, context))
            continue
        if r.get("source_ref", "").startswith("SOP3:"):
            from .forex_sop import evaluate_rule as evaluate_forex_rule

            findings.append(evaluate_forex_rule(r, documents, cfg, context))
            continue
        if r.get("operator") == "account_check":
            from .account_opening_sop import evaluate_rule

            findings.append(evaluate_rule(r, documents, cfg, context))
            continue
        left_path = r["path"]
        right_path = r.get("other_path") or r["path"]
        left_type = left_path.split(".")[0]
        right_type = right_path.split(".")[0]

        from .valas_resolution import (
            is_valas_prefix,
            get_case_valas_document,
            resolve_valas_path,
        )

        valas_doc, active_valas = get_case_valas_document(documents, context)
        l_ok, r_ok = True, True
        l_msg, r_msg = None, None
        if is_valas_prefix(left_type):
            left_path, l_ok, l_msg = resolve_valas_path(
                left_path, active_valas, context
            )
        if is_valas_prefix(right_type):
            right_path, r_ok, r_msg = resolve_valas_path(
                right_path, active_valas, context
            )

        actual, left = value_at(documents, left_path, context)
        expected, right = value_at(documents, right_path, context)
        result, message = "REVIEW", r.get("label", r["id"])
        op = r["operator"]
        cond = r.get("condition_operator", "always")
        unknown_condition = False
        applicable = True
        if cond in {"equals", "in"}:
            v = context.get(r["condition_key"], "UNKNOWN")
            unknown_condition = v in (None, "", "UNKNOWN")
            wanted = r.get("condition_value")
            applicable = v in (
                wanted.split(",")
                if isinstance(wanted, str) and cond == "in"
                else [wanted]
            )
        elif cond == "document_present":
            applicable = r.get("condition_value") in types
        if unknown_condition:
            message += " " + tpl("sop.applicability_context")
        elif not applicable:
            result = "NOT_APPLICABLE"
        elif not l_ok or not r_ok:
            result = "NOT_APPLICABLE"
            expl = l_msg or r_msg
            if expl:
                message += f" ({expl})"
        if result not in {"NOT_APPLICABLE"} and not unknown_condition:
            try:
                valid = None
                if op == "document_required":
                    valid = any(
                        d["doc_type"] == left_type and d["status"] == "COMPLETED"
                        for d in documents
                    )
                elif not left or len(left) != 1:
                    message += " " + tpl("sop.missing_ambiguous_ref")
                elif op == "required":
                    valid = (
                        actual is True
                        if isinstance(actual, bool)
                        else actual not in (None, "", [], {})
                    )
                    if isinstance(actual, str):
                        valid = bool(actual.strip()) and any(
                            c.isalnum() for c in actual
                        )
                elif (
                    op in {"match_exact", "match_address", "match_purpose"}
                    and actual not in (None, "")
                    and expected not in (None, "")
                ):
                    # Semantic equivalence requires an approved map; OCR cannot invent it.
                    kind = next(
                        (f["type"] for f in fields() if f["path"] == r["path"]), None
                    )
                    if kind == "identifier":
                        same = (str(actual).strip() == str(expected).strip())
                    else:
                        from .canonical_normalization import canonical_compare
                        matched, _, _ = canonical_compare(actual, expected)
                        same = matched
                    valid = same
                elif op in {"date_equal", "date_on_or_after"} and actual and expected:
                    from .date_utils import compare_dates

                    try:
                        valid = compare_dates(actual, expected, op=op)
                    except (ValueError, TypeError):
                        valid = False
                elif op == "match_money":
                    if r.get("comparison_policy") == "invoice_payment_basis":
                        basis = context.get("payment_basis", "UNKNOWN")
                        if basis == "PROGRESS_CLAIM":
                            expected, _ = value_at(
                                documents, "invoice.claim_note.amount"
                            )
                        elif basis != "FULL_INVOICE":
                            expected = None
                    currency, _ = value_at(documents, r["currency_path"], context)
                    other_currency, _ = value_at(documents, r["other_currency_path"], context)
                    if (
                        r.get("comparison_policy") == "invoice_payment_basis"
                        and context.get("payment_basis") == "PROGRESS_CLAIM"
                    ):
                        other_currency, _ = value_at(
                            documents, "invoice.claim_note.currency"
                        )
                    if (
                        actual is not None
                        and expected is not None
                        and currency
                        and other_currency
                    ):
                        a, b = Decimal(str(actual)), Decimal(str(expected))
                        if not a.is_finite() or not b.is_finite() or a <= 0 or b <= 0:
                            raise ValueError("Nonpositive money")
                        import pycountry

                        if any(
                            not isinstance(c, str)
                            or len(c) != 3
                            or not c.isupper()
                            or not pycountry.currencies.get(alpha_3=c)
                            for c in (currency, other_currency)
                        ):
                            raise ValueError("Invalid currency")
                        valid = a == b and currency == other_currency
                    message += f" Currency: {currency or 'unknown'} / {other_currency or 'unknown'}."
                elif op in {
                    "signature_visible",
                    "stamp_present",
                    "stamp_placement",
                } and isinstance(actual, dict):
                    keys = (
                        ["present", "non_text", "complete"]
                        if op == "signature_visible"
                        else ["present", "complete"]
                        + (["at_signer_region"] if op == "stamp_placement" else [])
                    )
                    observations = [actual.get(k) for k in keys]
                    if any(v is False for v in observations):
                        valid = False
                    elif (
                        all(v is True for v in observations)
                        and actual.get("page_number")
                        and actual.get("evidence")
                    ):
                        valid = True
                elif op == "all_pages_marked" and isinstance(actual, dict):
                    from page_policy import required_initial_pages, initial_page_records
                    pages = actual.get("pages", [])
                    count = actual.get("page_count")
                    page_policy = cfg["profiles"].get(left_type, {}).get("policy", {})
                    required_count = (
                        cfg["profiles"]
                        .get(left_type, {})
                        .get("policy", {})
                        .get("expected_pages")
                    )
                    if required_count and not page_policy.get("exclude_final_page", False) and count is not None and count != required_count:
                        valid = False
                    if (
                        valid is not False
                        and count
                        and isinstance(pages, list)
                    ):
                        required_pages = required_initial_pages(
                            count,
                            exclude_final_page=page_policy.get("exclude_final_page", False),
                            explicit_pages=page_policy.get("required_initial_pages"),
                        )
                        if not required_pages:
                            result = "NOT_APPLICABLE"
                        pages = initial_page_records(count, pages,
                            exclude_final_page=page_policy.get("exclude_final_page", False),
                            explicit_pages=page_policy.get("required_initial_pages"))
                        marks = [
                            p.get(k)
                            for p in pages
                            for k in ("footer_present", "non_text", "complete")
                        ]
                        if any(v is False for v in marks):
                            valid = False
                        elif required_pages and all(v is True for v in marks) and all(
                            p.get("evidence") for p in pages
                        ):
                            valid = True
                # signature_visual_consistency and policy_review intentionally require reviewed evidence.
                if valid is not None:
                    result = "PASS" if valid else "FAIL"
            except (ValueError, TypeError, InvalidOperation):
                result = "REVIEW"
                message += " " + tpl("sop.unreadable_values")
        if result in {"PASS", "FAIL"}:
            for path, references in (
                [(r["path"], left), (r.get("other_path"), right)]
                if op in MATCHES
                else [(r["path"], left)]
            ):
                if not path:
                    continue
                field_key = path.split(".")[1]
                for d in references:
                    issues = (
                        d.get("validation", {})
                        .get("fields", {})
                        .get(field_key, {})
                        .get("issues", [])
                    )
                    if visual_review_enabled and field_key not in d.get("overrides", {}) and any(
                        i.get("code")
                        in {
                            "LOW_EXTRACTION_CONFIDENCE",
                            "MISSING_CONFIDENCE",
                            "UNREADABLE_TEXT",
                            "INCOMPLETE_TEXT",
                            "CROP_EVIDENCE_REQUIRED",
                            "CROP_LINK_REVIEW_REQUIRED",
                        }
                        for i in issues
                    ):
                        result = "REVIEW"
                        message += " " + tpl("sop.low_confidence_source")
        findings.append(
            {
                "rule_id": r["id"],
                "field": r["path"],
                "source_ref": r.get("source_ref", ""),
                "scope_basis": r.get("scope_basis", "SYSTEM"),
                "category": r.get("report_category", "DATA_COMPLETION"),
                "eligible": True,
                "result": result,
                "message": message,
                "actual": actual,
                "expected": expected,
                "evidence": {
                    "document_ids": [d["id"] for d in left],
                    "reference_document_ids": [d["id"] for d in right],
                    "path": r["path"],
                    "other_path": r.get("other_path"),
                    "policy": r.get("comparison_policy"),
                    "metadata": [
                        d.get("validation", {})
                        .get("fields", {})
                        .get(r["path"].split(".")[1], {})
                        .get("metadata", {})
                        for d in left
                    ],
                },
            }
        )
    from .sop_scoring import normalize_findings

    return normalize_findings(findings, cfg.get("sop_rules", []), cfg=cfg)


def score(findings):
    from .configuration.scoring import category_scores, ScoreGroups, defaults

    return category_scores(findings, ScoreGroups.model_validate(defaults()["forex"]))
