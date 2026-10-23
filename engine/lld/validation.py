"""LLD rules, conditional category subtypes and externally scoped uniqueness checks."""
from copy import deepcopy
from decimal import Decimal
import re
import unicodedata

import holidays
import pycountry

from context import checkbox_identity, resolve_checkbox
from validation import check_schema, clean, parse_date, parse_number, current_date, confidence_values
from lld.schema import SCHEMA, COLUMNS


def label(value):
    """Remove a printed list prefix and bilingual suffix, retaining the raw elsewhere."""
    value = re.sub(r"^[a-z]\s*[.)]\s*", "", clean(value or ""), flags=re.I)
    # Translation separators have whitespace on at least one side. Keep internal
    # slashes in KC/KP and KIM/KITAS/KITAP intact.
    return re.split(r"(?:\s+/\s*|\s*/\s+)", value, maxsplit=1)[0].strip()


ALIASES = {
    "resident": "Penduduk", "bukan penduduk": "Nonpenduduk", "nonresident": "Nonpenduduk", "non-resident": "Nonpenduduk",
    "non penduduk": "Nonpenduduk", "non bank": "Non Bank", "non-bank": "Non Bank",
    "bank lainnya": "Bank Lainnya", "bank lainya": "Bank Lainnya",
    "lembaga & organisasi internasional": "Lembaga/Organisasi Internasional",
    "lembaga dan organisasi internasional": "Lembaga/Organisasi Internasional",
    "lembaga keuangan non bank": "Lembaga Keuangan Non Bank",
    "kartu tanda penduduk (ktp)": "KTP", "surat izin mengemudi (sim)": "SIM",
    "nomor pokok wajib pajak (npwp)": "NPWP", "passport": "Paspor",
    "kim, kitas dan kitap": "KIM/KITAS/KITAP", "kim, kitas, dan kitap": "KIM/KITAS/KITAP",
    "no. identifikasi yang ditetapkan oleh bank": "No Identifikasi yang ditetapkan Bank",
    "no. identifikasi yang ditetapkan bank": "No Identifikasi yang ditetapkan Bank", "bank-assigned id": "No Identifikasi yang ditetapkan Bank",
    "non afiliasi": "Non Afiliasi", "non-afiliasi": "Non Afiliasi", "shareholder": "Pemegang Saham",
    "affiliated": "Terafiliasi", "non-affiliated": "Non Afiliasi"
}


def canonical(value, allowed, policy):
    value = label(value)
    aliases = {**ALIASES, **policy.get("enum_aliases", {})}
    value = aliases.get(value.casefold(), value)
    return next((x for x in allowed if checkbox_identity(x) == checkbox_identity(value)), None)


def identifier(value, kind=None, policy=None):
    if not isinstance(value, str) or not value.strip():
        return None
    value = re.sub(r"\s+", "", value)
    if kind == "NPWP" and (policy or {}).get("npwp_allow_format_punctuation", True):
        # Formatting separators only; never replace or infer identifier characters.
        value = value.replace(".", "").replace("-", "")
    return value


def validate(raw, metadata, policy, as_of=None, directory=None, validation_context=None):
    check_schema(raw, SCHEMA)
    context = validation_context or {}
    if not isinstance(context, dict) or not isinstance(context.get("transaction_ids", []), list) or not isinstance(context.get("identity_records", []), list):
        raise ValueError("LLD validation context must contain transaction_ids and identity_records arrays")
    if any(not isinstance(x, str) for x in context.get("transaction_ids", [])):
        raise ValueError("Known transaction IDs must be strings to preserve leading zeros")
    if any(not isinstance(x, dict) for x in context.get("identity_records", [])):
        raise ValueError("Identity history records must be objects")
    normalized = deepcopy(raw)
    reports = {k: {"raw_value": deepcopy(raw[k]), "normalized_value": None, "status": "PASS", "issues": []} for k, _ in COLUMNS}
    corrections, selections = [], {}
    reference_date = as_of or current_date(policy["timezone"])

    def issue(key, code, severity="FAIL"):
        reports[key]["issues"].append({"code": code, "severity": severity})
        if reports[key]["status"] != "FAIL":
            reports[key]["status"] = severity

    def empty(key):
        value = raw[key]
        if isinstance(value, dict):
            if any(o.get("state") in {"selected", "uncertain"} or o.get("local_mark_present") is not False
                   for o in (value.get("options") or [])):
                return False
            return not value.get("raw") and not value.get("selected")
        return not value or not value.strip()

    def skip(key, reason):
        if not empty(key):
            return False
        normalized[key] = None
        reports[key].update(status="NOT_APPLICABLE", applicability_reason=reason)
        return True

    def missing(key, required=True):
        normalized[key] = None
        if required:
            issue(key, "REQUIRED")
        elif reports[key]["status"] == "PASS":
            reports[key]["status"] = "NOT_PRESENT"

    def structural(key, before, after, method):
        if before != after:
            corrections.append({"field": key, "before": before, "after": after, "method": method, "review_required": False})

    def text_field(key, required=True):
        value = clean(raw[key]["raw"])
        normalized[key] = value
        if not value:
            missing(key, required)
        elif not any(c.isalnum() for c in value):
            issue(key, "SYMBOL_ONLY_TEXT")
        elif raw[key]["complete"] is False:
            issue(key, "TEXT_INCOMPLETE_OR_UNREADABLE")
        elif raw[key]["complete"] is not True:
            issue(key, "TEXT_COMPLETENESS_UNCERTAIN", "REVIEW")
        if value and any(unicodedata.category(c).startswith("C") and c not in "\n\r\t" for c in raw[key]["raw"]):
            issue(key, "UNSUPPORTED_CONTROL_SYMBOL")

    def date_field(key, business_day=False):
        value = raw[key]
        # Part I date uses explicitly labelled YYYY MM DD cells.
        if key == "transaction_date" and value and re.fullmatch(r"\s*\d{4}\s+\d{1,2}\s+\d{1,2}\s*", value):
            value = "-".join(value.split())
            structural(key, raw[key], value, "labelled_year_month_day_cells")
        try:
            d = parse_date(value, policy["day_first"], policy["two_digit_year_pivot"])
            normalized[key] = d.strftime("%d-%m-%Y")
            if d > reference_date:
                issue(key, "FUTURE_DATE")
            if business_day:
                if d.weekday() >= 5:
                    issue(key, "WEEKEND")
                if policy["include_indonesian_public_holidays"]:
                    categories = [holidays.PUBLIC] + ([holidays.GOVERNMENT] if policy["include_joint_leave"] else [])
                    if d in holidays.country_holidays("ID", years=[d.year], categories=categories):
                        issue(key, "INDONESIAN_HOLIDAY_OR_JOINT_LEAVE")
                if d.isoformat() in policy["additional_closed_dates"]:
                    issue(key, "BANK_CLOSED_DATE")
        except (ValueError, TypeError, OverflowError):
            normalized[key] = None
            issue(key, "INVALID_OR_MISSING_DATE")

    def postal(key):
        value = clean(raw[key])
        normalized[key] = value
        if not value:
            missing(key)
        elif not re.fullmatch(r"[0-9]{1,5}", value):
            issue(key, "POSTAL_CODE_MUST_BE_1_TO_5_DIGITS")

    def phone(key):
        value = clean(raw[key])
        normalized[key] = value
        if not value:
            missing(key, False)
            return
        if not re.fullmatch(r"\+?[0-9()\- ]+", value) or not any(c.isdigit() for c in value):
            issue(key, "INVALID_PHONE_CHARACTERS_OR_FORMAT")
        balance = 0
        for c in value:
            balance += (1 if c == "(" else -1 if c == ")" else 0)
            if balance < 0:
                break
        if balance != 0:
            issue(key, "UNBALANCED_PHONE_PARENTHESES")

    def country(key):
        value = (clean(raw[key]) or "").upper()
        normalized[key] = value or None
        lookup = pycountry.countries.get(alpha_2=value) if len(value) == 2 else pycountry.countries.get(alpha_3=value) if len(value) == 3 else None
        if lookup is None:
            issue(key, "INVALID_OR_MISSING_ISO_COUNTRY_CODE")
        else:
            normalized[key] = lookup.alpha_3 if policy.get("country_code_format") == "alpha3" else lookup.alpha_2

    def choose(key, allowed, codes=None, required=True, invalid_action="FAIL"):
        resolution = resolve_checkbox(raw[key], policy)
        selections[key] = resolution
        reports[key]["checkbox_resolution"] = resolution
        for code in resolution["issues"]:
            issue(key, code, "REVIEW")
        if resolution["reconciled"]:
            corrections.append({"field": key + ".selected", "before": raw[key]["selected"], "after": resolution["selected"],
                                "method": "local_checkbox_evidence", "review_required": True})
        selected = resolution["selected"]
        normalized[key] = None
        if selected is None:
            issue(key, "CHECKBOX_UNCERTAIN", "REVIEW")
            return None
        if not selected:
            missing(key, required)
            return None
        if len(selected) != 1:
            issue(key, "EXACTLY_ONE_SELECTION_REQUIRED")
            return None
        value = canonical(selected[0], allowed, policy)
        observed_codes = [clean(c).upper() for c in (raw[key]["selected_codes"] or [])]
        local_codes = [clean(o["code"]).upper() for o in (raw[key].get("options") or [])
                       if o.get("code") and checkbox_identity(o.get("label")) == checkbox_identity(selected[0])]
        if observed_codes and local_codes and observed_codes != local_codes:
            issue(key, "CHECKBOX_CODE_LABEL_CONFLICT")
        used_codes = local_codes or observed_codes
        if len(used_codes) > 1:
            issue(key, "MULTIPLE_SELECTED_CODES")
        elif used_codes:
            reports[key]["selected_code"] = used_codes[0]
            if codes is not None:
                from_code = codes.get(used_codes[0])
                if from_code is None:
                    issue(key, "INVALID_SELECTED_CODE", invalid_action)
                elif value is not None and value != from_code:
                    issue(key, "CHECKBOX_CODE_LABEL_CONFLICT")
                else:
                    value = from_code
        if value is None:
            normalized[key] = clean(selected[0])
            issue(key, "INVALID_ENUM", invalid_action)
        else:
            normalized[key] = value
        return value

    def category(key):
        # Labels of the physical leaf boxes map to parent categories explicitly.
        code_map = policy["category_codes"]
        leaf_to_parent = {**{x: x for x in code_map.values()},
                          **{x: "Bank" for x in policy["bank_subtype_codes"].values()},
                          "Non Bank": "Lembaga/Organisasi Internasional"}
        # Category Bank under f. (code F1) needs its code to distinguish from c.
        choose(key, list(leaf_to_parent), required=True)
        if normalized[key] is None:
            return None
        value = canonical(normalized[key], list(leaf_to_parent), policy)
        codes = reports[key].get("selected_code")
        parent = code_map.get(codes) if codes else leaf_to_parent.get(value)
        if codes and parent is None:
            issue(key, "INVALID_CATEGORY_CODE")
        if codes and value is not None:
            expected_leaf = (policy["bank_subtype_codes"].get(codes) or policy["international_subtype_codes"].get(codes) or parent)
            # A model may name the parent category, or the literal selected leaf.
            if value not in {parent, expected_leaf}:
                issue(key, "CHECKBOX_CODE_LABEL_CONFLICT")
        if not codes:
            issue(key, "CATEGORY_CODE_NOT_EXTRACTED", "REVIEW")
        if not policy.get("template_category_master_confirmed", False):
            issue(key, "CATEGORY_MASTER_NOT_CONFIRMED", "REVIEW")
        normalized[key] = parent or normalized[key]
        return parent

    def master(key, master_key):
        value = clean(raw[key])
        normalized[key] = value
        if not value:
            missing(key)
            return
        if key in {"account_type", "transaction_code"} and not re.fullmatch(r"[A-Za-z0-9]+", value):
            issue(key, "INVALID_CODE_CHARACTERS")
        values = policy.get(master_key)
        if values is None:
            issue(key, "OFFICIAL_MASTER_NOT_CONFIGURED", "REVIEW")
        elif isinstance(values, dict):
            matched = next((c for c, text in values.items() if value.casefold() in {c.casefold(), str(text).casefold()}), None)
            if matched is None:
                issue(key, "VALUE_NOT_IN_OFFICIAL_MASTER")
            else:
                normalized[key] = matched
        elif isinstance(values, list) and all(isinstance(x, str) for x in values):
            match = next((x for x in values if x.casefold() == value.casefold()), None)
            if match is None:
                issue(key, "VALUE_NOT_IN_OFFICIAL_MASTER")
            else:
                normalized[key] = match
        else:
            raise ValueError(f"{master_key} must be null, a string list or a code/description object")

    date_field("transaction_date", True)
    date_field("declaration_date")
    normalized["transaction_id"] = identifier(raw["transaction_id"])
    tx_id = normalized["transaction_id"]
    if not tx_id or not re.fullmatch(r"[A-Za-z0-9]+", tx_id):
        issue("transaction_id", "INVALID_OR_MISSING_IDENTIFIER")
    else:
        structural("transaction_id", raw["transaction_id"], tx_id, "identifier_format_whitespace")
        if tx_id in {identifier(x) for x in context.get("transaction_ids", [])}:
            issue("transaction_id", "DUPLICATE_TRANSACTION_ID")
        elif context.get("transaction_id_history_complete") is not True:
            issue("transaction_id", "TRANSACTION_UNIQUENESS_NOT_CHECKED", "REVIEW")
    master("account_type", "account_type_master")
    relation = choose("beneficiary_identity_relation", ["Penerima dana ≠ Pembayar", "Penerima dana = Pembayar"])
    # Mathematical relation symbols must be retained: identity() alone discards them.
    if relation:
        observed = label(selections["beneficiary_identity_relation"]["selected"][0])
        if "≠" in observed or "!=" in observed or "not identical" in observed.casefold():
            relation = "Penerima dana ≠ Pembayar"
        elif "=" in observed or "identical with" in observed.casefold():
            relation = "Penerima dana = Pembayar"
        else:
            relation = None
            issue("beneficiary_identity_relation", "IDENTITY_RELATION_SYMBOL_UNCLEAR", "REVIEW")
        normalized["beneficiary_identity_relation"] = relation
    same = relation == "Penerima dana = Pembayar" and policy.get("skip_sections_when_beneficiary_equals_payer", True)

    for party in ["beneficiary", "payer"]:
        for suffix, handler in [("name", text_field), ("address", text_field), ("postal_code", postal), ("phone", phone), ("country_code", country)]:
            key = party + "_" + suffix
            if party == "payer" and same and skip(key, "LLD identity '=' explicitly skips Part III"):
                continue
            handler(key)
        key = party + "_status"
        if not (party == "payer" and same and skip(key, "LLD identity '=' skips Part III")):
            choose(key, ["Penduduk", "Nonpenduduk"])
        category_key = party + "_category"
        parent = None
        if not (party == "payer" and same and skip(category_key, "LLD identity '=' skips Part III")):
            parent = category(category_key)
        for suffix, required_parent, code_map in [("bank", "Bank", policy["bank_subtype_codes"]),
                                                  ("international_organization", "Lembaga/Organisasi Internasional", policy["international_subtype_codes"])]:
            key = party + "_" + suffix
            if party == "payer" and same and skip(key, "LLD identity '=' skips Part III"):
                continue
            if parent != required_parent:
                if parent is None:
                    if empty(key):
                        normalized[key] = None
                    else:
                        choose(key, list(code_map.values()), code_map)
                    issue(key, "CATEGORY_DEPENDENCY_UNKNOWN", "REVIEW")
                elif not skip(key, "This subtype does not apply to the selected parent category"):
                    choose(key, list(code_map.values()), code_map)
                    issue(key, "SUBTYPE_CONFLICTS_WITH_PARENT_CATEGORY", "REVIEW")
            else:
                optional_bank = party == "beneficiary" and suffix == "bank" and policy["beneficiary_bank_allow_blank"]
                choose(key, list(code_map.values()), code_map, required=not optional_bank,
                       invalid_action=policy["beneficiary_bank_invalid_action"] if optional_bank else "FAIL")
                category_code = reports[category_key].get("selected_code")
                subtype_code = reports[key].get("selected_code")
                if category_code and subtype_code and category_code != subtype_code:
                    issue(key, "CATEGORY_SUBTYPE_CODE_CONFLICT")

        kind_key, number_key = party + "_identification_type", party + "_identification_number"
        if same and skip(kind_key, "LLD identity '=' skips I.5 and Part III"):
            kind = None
        else:
            kind = choose(kind_key, policy["identification_types"], policy["identification_codes"])
        if same and skip(number_key, "LLD identity '=' skips I.5 and Part III"):
            continue
        number = identifier(raw[number_key], kind, policy)
        normalized[number_key] = number
        if not number or not re.fullmatch(r"[A-Za-z0-9]+", number):
            issue(number_key, "INVALID_OR_MISSING_IDENTIFIER")
        else:
            structural(number_key, raw[number_key], number, "identifier_format_separators")
            matches = [x for x in context.get("identity_records", []) if identifier(x.get("value"), kind, policy) == number
                       and (policy.get("identity_number_global_uniqueness", False) or
                            (identifier(x.get("transaction_id")) == tx_id and x.get("role") == party))]
            if matches:
                issue(number_key, "DUPLICATE_IDENTITY_ENTRY_IN_CONFIGURED_SCOPE")
            elif not tx_id or context.get("identity_history_complete") is not True:
                issue(number_key, "IDENTITY_UNIQUENESS_NOT_CHECKED", "REVIEW")

    if not (same and skip("financial_relationship", "LLD identity '=' skips Part III")):
        choose("financial_relationship", ["Pemegang Saham", "Terafiliasi", "Group", "Non Afiliasi"],
               {"P": "Pemegang Saham", "T": "Terafiliasi", "G": "Group", "N": "Non Afiliasi"})
    deposit_key = "depository_correspondent_bank_country_code"
    if not (same and skip(deposit_key, "LLD identity '=' skips Part III")):
        if empty(deposit_key) and not policy["depository_country_required_when_payer_section_active"]:
            missing(deposit_key, False)
        else:
            country(deposit_key)

    value = raw["transaction_value"]
    currency = (clean(value["currency_raw"]) or "").upper() or None
    if currency is None or pycountry.currencies.get(alpha_3=currency) is None:
        issue("transaction_value", "INVALID_OR_MISSING_ISO_CURRENCY")
    amount_raw = value["amount_raw"]
    if value["segmented_cells"] is True and amount_raw and re.fullmatch(r"[0-9\s]+", amount_raw):
        joined = re.sub(r"\s+", "", amount_raw)
        structural("transaction_value.amount", amount_raw, joined, "segmented_digit_cells")
        amount_raw = joined
    try:
        amount = parse_number(amount_raw, policy["number_locale"])
    except ValueError as e:
        amount = None
        issue("transaction_value", str(e))
    normalized["transaction_value"] = {"currency": currency, "amount": amount}
    master("purpose", "purpose_master")
    text_field("details", policy["details_required"])
    master("transaction_code", "transaction_code_master")
    for key in ["customer_signature", "bank_officer_signature"]:
        for component in ["present", "handwritten"]:
            if raw[key][component] is False:
                issue(key, component.upper() + "_REQUIRED")
            elif raw[key][component] is None:
                issue(key, component.upper() + "_UNCERTAIN", "REVIEW")
    if raw["bank_stamp"]["present"] is False:
        issue("bank_stamp", "STAMP_REQUIRED")
    elif raw["bank_stamp"]["present"] is None:
        issue("bank_stamp", "STAMP_PRESENCE_UNCERTAIN", "REVIEW")
    if not policy["stamp_rule_confirmed"]:
        issue("bank_stamp", "STAMP_VERIFICATION_RULE_NOT_CONFIGURED", "REVIEW")
    else:
        if raw["bank_stamp"]["complete"] is not True:
            issue("bank_stamp", "STAMP_COMPLETENESS_UNCERTAIN", "REVIEW")
        for fragment in policy["required_stamp_text_fragments"]:
            if fragment.casefold() not in (raw["bank_stamp"]["text"] or "").casefold():
                issue("bank_stamp", "REQUIRED_STAMP_TEXT_MISSING: " + fragment)

    field_meta = ((metadata or {}).get("field_metadata") or {}).get("document_metadata") or {}
    for key, report in reports.items():
        report["normalized_value"] = normalized[key]
        report["metadata"] = field_meta.get(key, {})
        scores = confidence_values(report["metadata"])
        report["confidence"] = min(scores) if scores else None
        if report["status"] not in {"NOT_PRESENT", "NOT_APPLICABLE"}:
            if scores and min(scores) < policy["minimum_confidence"]:
                issue(key, "LOW_EXTRACTION_CONFIDENCE", "REVIEW")
            elif not scores and policy["require_confidence"]:
                issue(key, "CONFIDENCE_UNAVAILABLE", "REVIEW")
    status = "FAIL" if any(x["status"] == "FAIL" for x in reports.values()) else "REVIEW" if any(x["status"] == "REVIEW" for x in reports.values()) else "PASS"
    return {"document_type": "lld", "status": status, "raw": raw, "normalized": normalized, "fields": reports,
            "corrections": corrections, "correction_suggestions": [], "checkbox_resolutions": selections,
            "as_of": reference_date.isoformat(), "policy": policy, "validation_context": context,
            "currency_export_location": "transaction_value.currency (inside Nilai Transaksi)"}
