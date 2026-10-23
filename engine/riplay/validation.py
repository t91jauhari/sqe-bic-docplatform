"""RIPLAY local quality rules; identity/reference verification remains evidence-bound."""

from copy import deepcopy
from decimal import Decimal
import math
from validation import check_schema, clean, parse_date, current_date, confidence_values
from riplay.schema import SCHEMA, COLUMNS, DOCUMENT_NAME


def validate(
    raw,
    metadata,
    policy,
    as_of=None,
    directory=None,
    validation_context=None,
    extract_job_id=None,
):
    check_schema(raw, SCHEMA)
    context = validation_context or {}
    if not isinstance(context, dict):
        raise ValueError("RIPLAY context must be an object")
    records = context.get("signature_comparisons", [])
    if not isinstance(records, list):
        raise ValueError("signature_comparisons must be an array")
    for record in records:
        if (
            not isinstance(record, dict)
            or record.get("status") not in {"matched", "mismatched", "unknown"}
            or any(
                not isinstance(record.get(k), str) or not record[k].strip()
                for k in [
                    "field",
                    "extract_job_id",
                    "signer_name",
                    "reference_id",
                    "verified_by",
                ]
            )
        ):
            raise ValueError(
                "Signature comparison requires field, job, signer, status, reference_id and verified_by"
            )
    for key in (
        "require_signature_comparison",
        "require_identity_match",
        "allow_final_main_signature_as_initial",
        "require_confidence",
    ):
        if not isinstance(policy.get(key), bool):
            raise ValueError(key + " must be boolean")
    expected = policy.get("expected_pages")
    if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1:
        raise ValueError("expected_pages must be a positive integer")
    required = policy.get("required_initial_pages", list(range(1, expected + 1)))
    if not isinstance(required, list) or not required or any(isinstance(n, bool) or not isinstance(n, int) or n < 1 or n > expected for n in required) or len(set(required)) != len(required):
        raise ValueError("required_initial_pages must contain unique physical page numbers")
    threshold = policy.get("minimum_confidence")
    if (
        not isinstance(threshold, (int, float, Decimal))
        or isinstance(threshold, bool)
        or not math.isfinite(threshold)
        or not 0 <= threshold <= 1
    ):
        raise ValueError("minimum_confidence must be in [0,1]")
    reference_date = as_of or current_date(policy["timezone"])
    normalized = deepcopy(raw)
    reports = {
        k: {
            "raw_value": deepcopy(raw[k]),
            "normalized_value": None,
            "status": "PASS",
            "issues": [],
        }
        for k, _ in COLUMNS
    }
    corrections = []

    def issue(key, code, severity="FAIL"):
        reports[key]["issues"].append({"code": code, "severity": severity})
        if severity == "FAIL" or reports[key]["status"] != "FAIL":
            reports[key]["status"] = severity

    for key in ["document_place", "bank_officer_name", "customer_name"]:
        value = clean(raw[key]["raw"]) or None
        normalized[key] = value
        if value != raw[key]["raw"]:
            corrections.append(
                {
                    "field": key,
                    "before": raw[key]["raw"],
                    "after": value,
                    "method": "trim_and_collapse_whitespace",
                    "review_required": False,
                }
            )
        if not value:
            issue(key, "REQUIRED")
        elif not any(c.isalpha() for c in value):
            issue(key, "NUMERIC_OR_SYMBOL_ONLY_TEXT")
        elif key != "document_place" and any(
            not (c.isalpha() or c.isspace() or c in ".'’") for c in value
        ):
            issue(key, "NAME_LETTERS_SPACES_DOT_APOSTROPHE_ONLY")
        if raw[key]["complete"] is False:
            issue(key, "TEXT_INCOMPLETE_OR_UNREADABLE")
        elif raw[key]["complete"] is not True:
            issue(key, "TEXT_COMPLETENESS_UNCERTAIN", "REVIEW")
    dates = {}
    for key in ["document_date", "printed_date"]:
        try:
            dates[key] = parse_date(
                raw[key], policy["day_first"], policy["two_digit_year_pivot"]
            )
            normalized[key] = dates[key].strftime("%d-%m-%Y")
            if normalized[key] != raw[key]:
                corrections.append(
                    {
                        "field": key,
                        "before": raw[key],
                        "after": normalized[key],
                        "method": "standardize_date",
                        "review_required": False,
                    }
                )
            if dates[key] > reference_date:
                issue(key, "FUTURE_DATE")
        except (ValueError, TypeError, OverflowError):
            normalized[key] = None
            issue(key, "INVALID_OR_MISSING_DATE")
    if len(dates) == 2 and dates["printed_date"] < dates["document_date"]:
        issue("printed_date", "PRINT_DATE_BEFORE_DOCUMENT_DATE")

    def integer(value):
        return (
            isinstance(value, (int, float, Decimal))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and int(value) == value
        )

    def compare(field, name, report_key):
        if not policy["require_signature_comparison"]:
            return
        matches = [
            r
            for r in records
            if extract_job_id
            and r["extract_job_id"] == extract_job_id
            and r["field"] == field
            and clean(r["signer_name"]).casefold() == (name or "").casefold()
        ]
        if len(matches) != 1 or matches[0]["status"] == "unknown":
            issue(
                report_key, "SIGNATURE_REFERENCE_COMPARISON_REQUIRED:" + field, "REVIEW"
            )
        elif matches[0]["status"] == "mismatched":
            issue(report_key, "SIGNATURE_REFERENCE_MISMATCH:" + field)

    def visual(key, observation):
        for attribute, code in [
            ("present", "SIGNATURE_REQUIRED"),
            ("non_text", "HANDWRITTEN_SIGNATURE_REQUIRED"),
            ("complete", "SIGNATURE_CROPPED_OR_UNREADABLE"),
        ]:
            if observation[attribute] is False:
                issue(key, code)
            elif observation[attribute] is not True:
                issue(key, attribute.upper() + "_UNCERTAIN", "REVIEW")
        if observation["corrupted"] is True:
            issue(key, "SIGNATURE_REGION_CORRUPTED")
        elif observation["corrupted"] is None:
            issue(key, "SIGNATURE_CORRUPTION_UNCERTAIN", "REVIEW")
        if (
            not integer(observation["page_number"])
            or not 1 <= observation["page_number"] <= expected
        ):
            issue(key, "SIGNATURE_PAGE_INVALID_OR_UNKNOWN", "REVIEW")
        if not clean(observation["evidence"]):
            issue(key, "VISUAL_EVIDENCE_REQUIRED", "REVIEW")

    for key, name in [
        ("bank_officer_signature", "bank_officer_name"),
        ("customer_signature", "customer_name"),
    ]:
        visual(key, raw[key])
        compare(key, normalized[name], key)

    pages = raw["page_initials"]
    count = pages["page_count"]
    if not integer(count) or count != expected:
        issue("page_initials", "EXPECTED_PAGE_COUNT_MISMATCH")
    observed = [p["page_number"] for p in pages["pages"]]
    if any(not integer(n) for n in observed) or sorted(observed) != list(
        range(1, expected + 1)
    ):
        issue("page_initials", "MISSING_DUPLICATE_OR_INVALID_PAGE_RECORDS")
    for page in pages["pages"]:
        n = page["page_number"]
        if n not in required:
            continue
        use_main = (
            n == expected
            and policy["allow_final_main_signature_as_initial"]
            and page["footer_present"] is False
            and page["main_signature_present"] is True
            and raw["customer_signature"]["page_number"] == n
            and all(
                raw["customer_signature"][k] is True
                for k in ["present", "non_text", "complete"]
            )
            and raw["customer_signature"]["corrupted"] is False
        )
        if not use_main:
            if page["footer_present"] is False:
                issue("page_initials", f"PAGE_{n}_BOTTOM_RIGHT_INITIAL_REQUIRED")
            elif page["footer_present"] is not True:
                issue("page_initials", f"PAGE_{n}_INITIAL_PRESENCE_UNCERTAIN", "REVIEW")
            for attribute in ["non_text", "complete"]:
                if page[attribute] is False:
                    issue("page_initials", f"PAGE_{n}_{attribute.upper()}_INVALID")
                elif page[attribute] is not True:
                    issue(
                        "page_initials",
                        f"PAGE_{n}_{attribute.upper()}_UNCERTAIN",
                        "REVIEW",
                    )
        else:
            corrections.append(
                {
                    "field": f"page_initials.pages.{n}",
                    "before": "footer absent",
                    "after": "main customer signature accepted by configured policy",
                    "method": "explicit_final_page_exception",
                    "review_required": False,
                }
            )
        if not clean(page["evidence"]):
            issue("page_initials", f"PAGE_{n}_VISUAL_EVIDENCE_REQUIRED", "REVIEW")
        compare(f"page_initials.{n}", normalized["customer_name"], "page_initials")

    pending = []
    if policy["require_identity_match"]:
        if context.get("defer_identity_to_case") is True:
            pending.append("riplay.customer_name_vs_ektp.name")
        else:
            identity = context.get("ektp_identity")
            if not isinstance(identity, dict) or not all(
                isinstance(identity.get(k), str) and identity[k].strip()
                for k in ["name", "reference_id", "verified_by"]
            ):
                issue("customer_name", "EKTP_IDENTITY_REFERENCE_REQUIRED", "REVIEW")
            elif (
                clean(identity["name"]).casefold()
                != (normalized["customer_name"] or "").casefold()
            ):
                issue("customer_name", "EKTP_NAME_MISMATCH")

    for key in ["customer_stamp", "cs_stamp"]:
        rules, observation = policy.get(key, {}), raw[key]
        if (
            not isinstance(rules.get("rule_confirmed"), bool)
            or (
                rules.get("required") is not None
                and not isinstance(rules["required"], bool)
            )
            or not isinstance(rules.get("text_fragments"), list)
            or any(
                not isinstance(t, str) or not t.strip() for t in rules["text_fragments"]
            )
        ):
            raise ValueError(key + " has an invalid stamp policy")
        if not rules["rule_confirmed"] or rules["required"] is None:
            issue(
                key,
                f"STAMP_REQUIREMENT_{rules.get('requirement_number')}_NOT_CONFIGURED",
                "REVIEW",
            )
        elif (
            rules["required"]
            or rules["text_fragments"]
            or observation["present"] is not False
        ):
            if observation["present"] is False:
                issue(key, "STAMP_REQUIRED")
            elif observation["present"] is not True:
                issue(key, "STAMP_PRESENCE_UNCERTAIN", "REVIEW")
            for attr in ["complete", "at_signer_region"]:
                if observation[attr] is False:
                    issue(key, "STAMP_" + attr.upper() + "_INVALID")
                elif observation[attr] is not True:
                    issue(key, "STAMP_" + attr.upper() + "_UNCERTAIN", "REVIEW")
            if (
                not integer(observation["page_number"])
                or not 1 <= observation["page_number"] <= expected
            ):
                issue(key, "STAMP_PAGE_INVALID_OR_UNKNOWN", "REVIEW")
            if not clean(observation["evidence"]):
                issue(key, "STAMP_VISUAL_EVIDENCE_REQUIRED", "REVIEW")
            for fragment in rules["text_fragments"]:
                if (
                    clean(fragment).casefold()
                    not in (clean(observation["text"]) or "").casefold()
                ):
                    issue(key, "REQUIRED_STAMP_TEXT_MISSING:" + fragment)

    field_meta = ((metadata or {}).get("field_metadata") or {}).get(
        "document_metadata"
    ) or {}
    for key, report in reports.items():
        report["normalized_value"] = normalized[key]
        report["metadata"] = field_meta.get(key, {})
        scores = confidence_values(report["metadata"])
        report["confidence"] = min(scores) if scores else None
        if scores and any(not math.isfinite(x) or not 0 <= x <= 1 for x in scores):
            issue(key, "INVALID_EXTRACTION_CONFIDENCE", "REVIEW")
        elif scores and min(scores) < threshold:
            issue(key, "LOW_EXTRACTION_CONFIDENCE", "REVIEW")
        elif not scores and policy["require_confidence"]:
            issue(key, "CONFIDENCE_UNAVAILABLE", "REVIEW")
    status = (
        "FAIL"
        if any(r["status"] == "FAIL" for r in reports.values())
        else "REVIEW"
        if any(r["status"] == "REVIEW" for r in reports.values())
        else "PASS"
    )
    return {
        "document_type": "riplay",
        "document_name": DOCUMENT_NAME,
        "status": status,
        "raw": raw,
        "normalized": normalized,
        "fields": reports,
        "corrections": corrections,
        "correction_suggestions": [],
        "checkbox_resolutions": {},
        "as_of": reference_date.isoformat(),
        "policy": policy,
        "validation_context": context,
        "extract_job_id": extract_job_id,
        "pending_case_checks": pending,
    }
