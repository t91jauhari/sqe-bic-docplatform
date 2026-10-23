"""Shared declaration checks; extraction observations never prove meterai authenticity."""
from copy import deepcopy
import math
import re
import unicodedata

import pycountry

from validation import check_schema, clean, parse_date, current_date, confidence_values


def validate_declaration(raw, metadata, policy, as_of=None, directory=None, validation_context=None, extract_job_id=None,
                         *, schema, columns, document_type, document_name, extra_validator=None):
    check_schema(raw, schema)
    context = {} if validation_context is None else validation_context
    if not isinstance(context, dict) or not isinstance(context.get("stamp_duty_verifications", []), list):
        raise ValueError("Declaration context must contain a stamp_duty_verifications array")
    records = context.get("stamp_duty_verifications", [])
    for record in records:
        if (not isinstance(record, dict) or not isinstance(record.get("extract_job_id"), str)
                or not record["extract_job_id"].strip() or record.get("status") not in {"verified", "rejected", "unknown"}
                or not isinstance(record.get("verification_reference"), str) or not record["verification_reference"].strip()
                or not isinstance(record.get("verified_by"), str) or not record["verified_by"].strip()):
            raise ValueError("Each meterai verification needs extract_job_id, status, verification_reference and verified_by")
    if "stamp_verification" in raw:
        if (policy.get("stamp_required") is not None and not isinstance(policy["stamp_required"], bool)) or not isinstance(policy.get("stamp_rule_confirmed"), bool):
            raise ValueError("Stamp policy needs boolean stamp_rule_confirmed and boolean/null stamp_required")
        fragments = policy.get("required_stamp_text_fragments")
        if not isinstance(fragments, list) or any(not isinstance(x, str) or not x.strip() for x in fragments):
            raise ValueError("required_stamp_text_fragments must be an array of nonempty strings")
    denomination = policy.get("stamp_duty_denomination")
    if not isinstance(denomination, str) or not re.fullmatch(r"[0-9]+", denomination) or int(denomination) <= 0:
        raise ValueError("stamp_duty_denomination must be a positive integer string")
    denomination_aliases = policy.get("stamp_duty_text_aliases", [])
    if not isinstance(denomination_aliases, list) or any(not isinstance(x, str) or not x.strip() for x in denomination_aliases):
        raise ValueError("stamp_duty_text_aliases must be an array of nonempty strings")
    reference_date = as_of or current_date(policy["timezone"])
    normalized = deepcopy(raw)
    reports = {key: {"raw_value": deepcopy(raw[key]), "normalized_value": None, "status": "PASS", "issues": []}
               for key, _ in columns}
    corrections = []

    def issue(key, code, severity="FAIL"):
        reports[key]["issues"].append({"code": code, "severity": severity})
        if reports[key]["status"] != "FAIL":
            reports[key]["status"] = severity

    def structural(key, before, after, method="trim_and_collapse_whitespace"):
        if before != after:
            corrections.append({"field": key, "before": before, "after": after,
                                "method": method, "review_required": False})

    def text(key, required=True, require_letters=False):
        observation = raw[key]
        value = clean(observation["raw"]) or None
        normalized[key] = value
        structural(key, observation["raw"], value)
        if not value:
            if required:
                issue(key, "REQUIRED")
            else:
                reports[key]["status"] = "NOT_PRESENT"
            return
        if not any(c.isalnum() for c in value):
            issue(key, "SYMBOL_ONLY_TEXT")
        elif require_letters and not any(c.isalpha() for c in value):
            issue(key, "NUMERIC_ONLY_TEXT")
        if any(unicodedata.category(c).startswith("C") and c not in "\n\r\t" for c in observation["raw"]):
            issue(key, "UNSUPPORTED_CONTROL_SYMBOL")
        if observation["complete"] is False:
            issue(key, "TEXT_INCOMPLETE_OR_UNREADABLE")
        elif observation["complete"] is not True:
            issue(key, "TEXT_COMPLETENESS_UNCERTAIN", "REVIEW")

    text("customer_name")
    subject = raw["customer_name"]["subject_type"]
    if subject not in {"company", "individual", "uncertain", None}:
        issue("customer_name", "INVALID_SUBJECT_TYPE")
    text("customer_address")
    text("creation_place", require_letters=True)

    if "currency" in raw:
        value = clean(raw["currency"])
        code = (value or "").upper()
        aliases = policy.get("currency_aliases", {})
        if not isinstance(aliases, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in aliases.items()):
            raise ValueError("currency_aliases must map explicit currency names to ISO codes")
        code = {k.upper(): v.upper() for k, v in aliases.items()}.get(code, code)
        normalized["currency"] = code or None
        structural("currency", raw["currency"], normalized["currency"], "uppercase_code_or_explicit_currency_alias")
        if code in {"$", "¥", "DOLLAR", "DOLAR", "YEN", "YUAN"}:
            normalized["currency"] = None
            issue("currency", "CURRENCY_AMBIGUOUS", "REVIEW")
        elif not re.fullmatch(r"[A-Z]{3}", code) or pycountry.currencies.get(alpha_3=code) is None:
            issue("currency", "INVALID_OR_MISSING_ISO_4217_CODE")

    try:
        parsed = parse_date(raw["creation_date"], policy["day_first"], policy["two_digit_year_pivot"])
        normalized["creation_date"] = parsed.strftime("%d-%m-%Y")
        structural("creation_date", raw["creation_date"], normalized["creation_date"], "standardize_date")
        if parsed > reference_date:
            issue("creation_date", "FUTURE_DATE")
    except (ValueError, TypeError, OverflowError):
        normalized["creation_date"] = None
        issue("creation_date", "INVALID_OR_MISSING_DATE")

    signer = raw["signatory"]
    representative = signer["is_company_representative"]
    capacity_evidence = clean(signer["capacity_evidence"])
    capacity_clear = representative is not None and bool(capacity_evidence)
    if not capacity_clear:
        issue("signatory", "SIGNATORY_CAPACITY_UNCERTAIN", "REVIEW")
        issue("signatory_company", "SIGNATORY_CAPACITY_UNCERTAIN", "REVIEW")
    conflict = (subject == "company" and representative is False)
    if conflict:
        issue("signatory", "COMPANY_CUSTOMER_WITH_SELF_SIGNING_INDIVIDUAL_CAPACITY")
    required = representative is True or subject == "company"
    name, role = clean(signer["name_raw"]) or None, clean(signer["role_raw"]) or None
    signer_text = clean(signer["raw"]) or None
    normalized["signatory"] = {"name": name, "position": role,
                               "is_company_representative": representative, "capacity_evidence": capacity_evidence}
    for part, original, after in [("name", signer["name_raw"], name), ("position", signer["role_raw"], role),
                                  ("raw", signer["raw"], signer_text)]:
        structural("signatory." + part, original, after)
    if required:
        if not name:
            issue("signatory", "SIGNATORY_NAME_REQUIRED")
        if not role:
            issue("signatory", "SIGNATORY_ROLE_REQUIRED")
    if role and not name:
        issue("signatory", "SIGNATORY_NAME_MISSING_WITH_ROLE")
    if signer_text and not name and not role:
        issue("signatory", "SIGNATORY_COMPONENTS_UNREADABLE", "REVIEW")
    for part, value in [("NAME", name), ("ROLE", role)]:
        if value and (not any(c.isalpha() for c in value)
                      or any(not (c.isalpha() or c.isspace() or unicodedata.category(c).startswith("P")) for c in value)):
            issue("signatory", "INVALID_SIGNATORY_" + part)
        if value and clean(value).casefold() not in (signer_text or "").casefold():
            issue("signatory", "SIGNATORY_" + part + "_NOT_SUPPORTED_BY_RAW_TEXT", "REVIEW")
    if signer_text or name or role:
        if signer["complete"] is False:
            issue("signatory", "SIGNATORY_TEXT_INCOMPLETE")
        elif signer["complete"] is not True:
            issue("signatory", "SIGNATORY_TEXT_COMPLETENESS_UNCERTAIN", "REVIEW")
    elif not required and capacity_clear and reports["signatory"]["status"] == "PASS":
        reports["signatory"]["status"] = "NOT_APPLICABLE"
    text("signatory_company", required=required)
    # An absent company must not erase uncertainty established by capacity checks.
    if not normalized["signatory_company"] and not required:
        if not capacity_clear:
            reports["signatory_company"]["status"] = "REVIEW"
        else:
            reports["signatory_company"]["status"] = "NOT_APPLICABLE"

    stamp = raw["stamp_duty"]
    if stamp["present"] is False:
        issue("stamp_duty", "STAMP_DUTY_REQUIRED")
    elif stamp["present"] is not True:
        issue("stamp_duty", "STAMP_DUTY_PRESENCE_UNCERTAIN", "REVIEW")
    if stamp["complete"] is False:
        issue("stamp_duty", "STAMP_DUTY_CROPPED_OR_UNREADABLE")
    elif stamp["complete"] is not True:
        issue("stamp_duty", "STAMP_DUTY_COMPLETENESS_UNCERTAIN", "REVIEW")
    denomination_text = clean(stamp["denomination_raw"])
    numeric = re.sub(r"^RP\.?\s*", "", (denomination_text or "").upper())
    digit_text = re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:[ .][0-9]{3})+)", numeric)
    normalized_denomination = re.sub(r"[ .]", "", numeric) if digit_text else None
    if (denomination_text or "").upper() in [x.upper() for x in denomination_aliases]:
        normalized_denomination = denomination
    if normalized_denomination is None or int(normalized_denomination) != int(denomination):
        issue("stamp_duty", "INVALID_OR_MISSING_STAMP_DUTY_DENOMINATION")
    if stamp["suspected_tampering"] is True:
        issue("stamp_duty", "STAMP_DUTY_SUSPECTED_TAMPERING", "REVIEW")
    elif stamp["suspected_tampering"] is None:
        issue("stamp_duty", "STAMP_DUTY_VISUAL_FEATURES_UNCERTAIN", "REVIEW")
    if not clean(stamp["evidence"]):
        issue("stamp_duty", "STAMP_DUTY_VISUAL_EVIDENCE_MISSING", "REVIEW")
    matched = [record for record in records if extract_job_id and record["extract_job_id"] == extract_job_id]
    authenticity = "unverified"
    if len(matched) > 1:
        issue("stamp_duty", "CONFLICTING_OR_DUPLICATE_STAMP_DUTY_VERIFICATIONS", "REVIEW")
    elif len(matched) == 1 and matched[0]["status"] == "verified":
        authenticity = "verified"
    elif len(matched) == 1 and matched[0]["status"] == "rejected":
        authenticity = "rejected"
        issue("stamp_duty", "STAMP_DUTY_AUTHENTICITY_REJECTED")
    if authenticity == "unverified":
        issue("stamp_duty", "STAMP_DUTY_AUTHENTICITY_REQUIRES_EXTERNAL_VERIFICATION", "REVIEW")
    normalized["stamp_duty"] = {**stamp, "denomination": normalized_denomination,
                                "authenticity_status": authenticity,
                                "verification": deepcopy(matched[0]) if len(matched) == 1 else None}

    signature = raw["signatory_signature"]
    for attribute, code in [("present", "SIGNATURE_REQUIRED"), ("handwritten", "HANDWRITTEN_SIGNATURE_REQUIRED"),
                            ("complete", "SIGNATURE_CROPPED_OR_UNREADABLE")]:
        if signature[attribute] is False:
            issue("signatory_signature", code)
        elif signature[attribute] is not True:
            issue("signatory_signature", attribute.upper() + "_UNCERTAIN", "REVIEW")
    if not clean(signature["evidence"]):
        issue("signatory_signature", "SIGNATURE_VISUAL_EVIDENCE_MISSING", "REVIEW")

    if "stamp_verification" in raw:
        rubber_stamp = raw["stamp_verification"]
        configured = policy["stamp_rule_confirmed"] and policy["stamp_required"] is not None
        if not configured:
            issue("stamp_verification", "STAMP_VERIFICATION_RULE_NOT_CONFIGURED", "REVIEW")
        else:
            required_stamp = policy["stamp_required"] or bool(fragments)
            if rubber_stamp["present"] is False:
                if required_stamp:
                    issue("stamp_verification", "STAMP_REQUIRED")
                else:
                    reports["stamp_verification"]["status"] = "NOT_APPLICABLE"
            elif rubber_stamp["present"] is not True:
                issue("stamp_verification", "STAMP_PRESENCE_UNCERTAIN", "REVIEW")
            if rubber_stamp["present"] is True or required_stamp:
                if rubber_stamp["complete"] is False:
                    issue("stamp_verification", "STAMP_CROPPED_OR_UNREADABLE")
                elif rubber_stamp["complete"] is not True:
                    issue("stamp_verification", "STAMP_COMPLETENESS_UNCERTAIN", "REVIEW")
                if not clean(rubber_stamp["evidence"]):
                    issue("stamp_verification", "STAMP_VISUAL_EVIDENCE_MISSING", "REVIEW")
                for fragment in fragments:
                    if clean(fragment).casefold() not in (clean(rubber_stamp["text"]) or "").casefold():
                        issue("stamp_verification", "REQUIRED_STAMP_TEXT_MISSING: " + fragment)

    if extra_validator:
        extra_validator(raw, normalized, reports, issue, structural, policy, reference_date)

    field_meta = ((metadata or {}).get("field_metadata") or {}).get("document_metadata") or {}
    for key, report in reports.items():
        report["normalized_value"] = normalized[key]
        report["metadata"] = field_meta.get(key, {})
        scores = confidence_values(report["metadata"])
        report["confidence"] = min(scores) if scores else None
        if report["status"] not in {"NOT_PRESENT", "NOT_APPLICABLE"}:
            if scores and any(not math.isfinite(x) or not 0 <= x <= 1 for x in scores):
                issue(key, "INVALID_EXTRACTION_CONFIDENCE", "REVIEW")
            elif scores and min(scores) < policy["minimum_confidence"]:
                issue(key, "LOW_EXTRACTION_CONFIDENCE", "REVIEW")
            elif not scores and policy["require_confidence"]:
                issue(key, "CONFIDENCE_UNAVAILABLE", "REVIEW")
    status = "FAIL" if any(x["status"] == "FAIL" for x in reports.values()) else "REVIEW" if any(x["status"] == "REVIEW" for x in reports.values()) else "PASS"
    return {"document_type": document_type, "document_name": document_name, "status": status,
            "raw": raw, "normalized": normalized, "fields": reports, "corrections": corrections,
            "correction_suggestions": [], "checkbox_resolutions": {}, "as_of": reference_date.isoformat(),
            "policy": policy, "validation_context": context, "extract_job_id": extract_job_id}
