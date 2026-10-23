"""Twenty eKTP rules; visual evidence is distinct from signature comparison."""
from copy import deepcopy
import math
import re
import unicodedata

from validation import check_schema, clean, parse_date, current_date, confidence_values
from ektp.schema import SCHEMA, COLUMNS, DOCUMENT_NAME


def validate(raw, metadata, policy, as_of=None, directory=None, validation_context=None, extract_job_id=None):
    check_schema(raw, SCHEMA)
    context = {} if validation_context is None else validation_context
    if not isinstance(context, dict) or not isinstance(context.get("signature_comparisons", []), list):
        raise ValueError("eKTP context must contain a signature_comparisons array")
    comparisons = context.get("signature_comparisons", [])
    for record in comparisons:
        if (not isinstance(record, dict) or record.get("status") not in {"matched", "mismatched", "unknown"}
                or not isinstance(record.get("nik"), str) or not re.fullmatch(r"[0-9]{16}", record["nik"])
                or any(not isinstance(record.get(k), str) or not record[k].strip()
                       for k in ["extract_job_id", "reference_id", "comparison_reference", "verified_by"])):
            raise ValueError("Signature comparison needs extract_job_id, 16-digit nik, status, reference_id, comparison_reference and verified_by")
    if not isinstance(policy.get("stamp_rule_confirmed"), bool):
        raise ValueError("stamp_rule_confirmed must be boolean")
    if policy.get("stamp_required") is not None and not isinstance(policy["stamp_required"], bool):
        raise ValueError("stamp_required must be boolean/null")
    fragments = policy.get("required_stamp_text_fragments")
    if not isinstance(fragments, list) or any(not isinstance(x, str) or not x.strip() for x in fragments):
        raise ValueError("required_stamp_text_fragments must be nonempty strings")
    reference_date = as_of or current_date(policy["timezone"])
    normalized = deepcopy(raw)
    reports = {key: {"raw_value": deepcopy(raw[key]), "normalized_value": None, "status": "PASS", "issues": []}
               for key, _ in COLUMNS}
    corrections = []

    def issue(key, code, severity="FAIL"):
        reports[key]["issues"].append({"code": code, "severity": severity})
        if reports[key]["status"] != "FAIL":
            reports[key]["status"] = severity

    def structural(key, before, after, method="trim_and_collapse_whitespace"):
        if before != after:
            corrections.append({"field": key, "before": before, "after": after,
                                "method": method, "review_required": False})

    def text(key, alphabetic=False, city=False):
        observation = raw[key]
        value = clean(observation["raw"]) or None
        normalized[key] = value
        structural(key, observation["raw"], value)
        if not value:
            issue(key, "REQUIRED")
            return
        if alphabetic and not all(c.isalpha() or c.isspace() for c in value):
            issue(key, "ALPHABETIC_CHARACTERS_AND_SPACES_ONLY")
        elif not any(c.isalnum() for c in value):
            issue(key, "SYMBOL_ONLY_TEXT")
        if city and (not any(c.isalpha() for c in value)
                     or any(not (c.isalpha() or c.isspace() or unicodedata.category(c).startswith("P")) for c in value)):
            issue(key, "INVALID_CITY_CHARACTERS")
        if any(unicodedata.category(c).startswith("C") and c not in "\n\r\t" for c in observation["raw"]):
            issue(key, "UNSUPPORTED_CONTROL_SYMBOL")
        if observation["complete"] is False:
            issue(key, "TEXT_INCOMPLETE_OR_UNREADABLE")
        elif observation["complete"] is not True:
            issue(key, "TEXT_COMPLETENESS_UNCERTAIN", "REVIEW")

    nik = raw["nik"]
    # Never strip spaces/dots or pad this identifier: supplied rule rejects them.
    normalized["nik"] = nik
    if nik is None or nik == "":
        issue("nik", "NIK_REQUIRED")
    elif not re.fullmatch(r"[0-9]{16}", nik):
        issue("nik", "NIK_EXACTLY_16_ASCII_DIGITS_NO_SEPARATORS")
    text("name", alphabetic=True)
    text("birth_place", alphabetic=True)
    for key in ["address", "village", "district", "occupation"]:
        text(key)

    aliases = policy.get("enum_aliases", {})
    enum_fields = ["gender", "blood_type", "religion", "marital_status", "citizenship"]
    if not isinstance(aliases, dict) or set(aliases) - set(enum_fields):
        raise ValueError("enum_aliases must map supported enum fields")
    fallback_fields = policy.get("enum_raw_fallback_fields", ["religion"])
    if not isinstance(fallback_fields, list) or any(field not in enum_fields for field in fallback_fields):
        raise ValueError("enum_raw_fallback_fields must list supported enum fields")
    for key in enum_fields:
        values = policy.get(key + "_values")
        if (not isinstance(values, list) or not values or any(not isinstance(x, str) or not x.strip() for x in values)
                or len({clean(x).casefold() for x in values}) != len(values)):
            raise ValueError(key + "_values must contain distinct nonempty text values")
        value = clean(raw[key])
        matched = next((x for x in values if value and clean(x).casefold() == value.casefold()), None)
        mapping = aliases.get(key, {})
        if not isinstance(mapping, dict) or any(not isinstance(a, str) or not clean(a) or b not in values for a, b in mapping.items()) or len({clean(a).casefold() for a in mapping}) != len(mapping):
            raise ValueError(key + " aliases require unique nonempty spellings and approved canonical targets")
        if any(any(clean(a).casefold() == clean(v).casefold() and b != v for v in values) for a, b in mapping.items()):
            raise ValueError(key + " aliases cannot remap canonical enum values")
        alias_matched = next((target for spelling, target in mapping.items() if value and clean(spelling).casefold() == value.casefold()), None) if matched is None else None
        matched = matched or alias_matched
        normalized[key] = matched if matched is not None else value if value and key in fallback_fields else None
        if matched is None and value and key in fallback_fields:
            corrections.append({"field": key, "before": raw[key], "after": value, "method": "unrecognized_enum_raw_fallback", "review_required": True})
        if matched is None:
            issue(key, "MISSING_ENUM" if not value else "UNRECOGNIZED_ENUM", "FAIL" if not value else "REVIEW")
        else:
            structural(key, raw[key], matched, "approved_enum_alias" if alias_matched else "case_insensitive_exact_enum")

    for key in ["rt", "rw"]:
        value = clean(raw[key])
        if not value or not re.fullmatch(r"[0-9]{1,3}", value):
            normalized[key] = None
            issue(key, "ONE_TO_THREE_ASCII_DIGITS_REQUIRED")
        else:
            normalized[key] = value.zfill(3)
            structural(key, raw[key], normalized[key], "trim_and_left_pad_to_three_digits")

    def date_value(key, value, path=None):
        try:
            # Support a printed sentence-ending period after a complete year.
            prepared = clean(value)
            if isinstance(prepared, str) and re.search(r"[0-9]{4}\.$", prepared):
                prepared = prepared[:-1]
            parsed = parse_date(prepared, policy["day_first"], policy["two_digit_year_pivot"])
            result = parsed.strftime("%d-%m-%Y")
            structural(path or key, value, result, "standardize_date")
            if parsed > reference_date:
                issue(key, "FUTURE_DATE")
            return result
        except (ValueError, TypeError, OverflowError):
            issue(key, "INVALID_OR_MISSING_DATE")
            return None

    normalized["birth_date"] = date_value("birth_date", raw["birth_date"])
    expiry = clean(raw["valid_until"])
    if expiry and expiry.casefold() == "seumur hidup":
        normalized["valid_until"] = "SEUMUR HIDUP"
        structural("valid_until", raw["valid_until"], normalized["valid_until"], "case_insensitive_lifetime_validity")
    else:
        # User explicitly supplied a non-future rule for dated validity as well.
        normalized["valid_until"] = date_value("valid_until", raw["valid_until"])
    issuance = raw["issuance"]
    place = clean(issuance["place_raw"]) or None
    structural("issuance.place", issuance["place_raw"], place)
    if not place:
        issue("issuance", "ISSUANCE_PLACE_REQUIRED")
    elif (not any(c.isalpha() for c in place)
          or any(not (c.isalpha() or c.isspace() or unicodedata.category(c).startswith("P")) for c in place)):
        issue("issuance", "INVALID_ISSUANCE_CITY_CHARACTERS")
    if place:
        if issuance["place_complete"] is False:
            issue("issuance", "ISSUANCE_PLACE_INCOMPLETE_OR_UNREADABLE")
        elif issuance["place_complete"] is not True:
            issue("issuance", "ISSUANCE_PLACE_COMPLETENESS_UNCERTAIN", "REVIEW")
    normalized["issuance"] = {"place": place, "date": date_value("issuance", issuance["date_raw"], "issuance.date")}

    signature = raw["owner_signature"]
    for attribute, code in [("present", "OWNER_SIGNATURE_REQUIRED"), ("non_text", "NON_TEXT_SIGNATURE_REGION_REQUIRED"),
                            ("complete", "OWNER_SIGNATURE_CROPPED_OR_INCOMPLETE")]:
        if signature[attribute] is False:
            issue("owner_signature", code)
        elif signature[attribute] is not True:
            issue("owner_signature", attribute.upper() + "_UNCERTAIN", "REVIEW")
    if signature["corrupted"] is True:
        issue("owner_signature", "OWNER_SIGNATURE_CORRUPTED")
    elif signature["corrupted"] is None:
        issue("owner_signature", "OWNER_SIGNATURE_CORRUPTION_UNCERTAIN", "REVIEW")
    if not clean(signature["evidence"]):
        issue("owner_signature", "SIGNATURE_VISUAL_EVIDENCE_MISSING", "REVIEW")
    candidates = [record for record in comparisons if extract_job_id and record["extract_job_id"] == extract_job_id]
    matched = [record for record in candidates if record["nik"] == nik and re.fullmatch(r"[0-9]{16}", nik or "")]
    comparison_status = "unverified"
    if any(record["nik"] != nik for record in candidates):
        issue("owner_signature", "SIGNATURE_COMPARISON_NIK_CONFLICT", "REVIEW")
    if len(candidates) > 1:
        issue("owner_signature", "DUPLICATE_OR_CONFLICTING_SIGNATURE_COMPARISONS", "REVIEW")
    elif len(matched) == 1:
        comparison_status = matched[0]["status"]
        if comparison_status == "mismatched":
            issue("owner_signature", "OWNER_SIGNATURE_REFERENCE_MISMATCH")
    if comparison_status not in {"matched", "mismatched"}:
        issue("owner_signature", "SIGNATURE_MATCH_REQUIRES_EXTERNAL_COMPARISON", "REVIEW")
    normalized["owner_signature"] = {**signature, "comparison_status": comparison_status,
                                     "comparison": deepcopy(matched[0]) if len(matched) == 1 and len(candidates) == 1 else None}

    photo = raw["owner_photo"]
    for attribute, code in [("present", "OWNER_PHOTO_REQUIRED"), ("face_visible", "OWNER_FACE_NOT_VISIBLE")]:
        if photo[attribute] is False:
            issue("owner_photo", code)
        elif photo[attribute] is not True:
            issue("owner_photo", attribute.upper() + "_UNCERTAIN", "REVIEW")
    if photo["face_cropped"] is True:
        issue("owner_photo", "OWNER_FACE_CROPPED")
    elif photo["face_cropped"] is None:
        issue("owner_photo", "OWNER_FACE_CROPPING_UNCERTAIN", "REVIEW")
    if not clean(photo["evidence"]):
        issue("owner_photo", "PHOTO_VISUAL_EVIDENCE_MISSING", "REVIEW")

    stamp = raw["stamp_verification"]
    configured = policy["stamp_rule_confirmed"] and policy.get("stamp_required") is not None
    if not configured:
        issue("stamp_verification", "STAMP_REQUIREMENT_NUMBER_6_NOT_CONFIGURED", "REVIEW")
    else:
        required_stamp = policy["stamp_required"] or bool(fragments)
        if stamp["present"] is False:
            if required_stamp:
                issue("stamp_verification", "STAMP_REQUIRED")
            else:
                reports["stamp_verification"]["status"] = "NOT_APPLICABLE"
        elif stamp["present"] is not True:
            issue("stamp_verification", "STAMP_PRESENCE_UNCERTAIN", "REVIEW")
        if stamp["present"] is True or required_stamp:
            if stamp["complete"] is False:
                issue("stamp_verification", "STAMP_CROPPED_OR_UNREADABLE")
            elif stamp["complete"] is not True:
                issue("stamp_verification", "STAMP_COMPLETENESS_UNCERTAIN", "REVIEW")
            if not clean(stamp["evidence"]):
                issue("stamp_verification", "STAMP_VISUAL_EVIDENCE_MISSING", "REVIEW")
            for fragment in fragments:
                if clean(fragment).casefold() not in (clean(stamp["text"]) or "").casefold():
                    issue("stamp_verification", "REQUIRED_STAMP_TEXT_MISSING: " + fragment)

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
    return {"document_type": "ektp", "document_name": DOCUMENT_NAME, "status": status,
            "raw": raw, "normalized": normalized, "fields": reports, "corrections": corrections,
            "correction_suggestions": [], "checkbox_resolutions": {}, "as_of": reference_date.isoformat(),
            "policy": policy, "validation_context": context, "extract_job_id": extract_job_id}
