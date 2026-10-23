"""Deterministic validation. Unverifiable rules require REVIEW, never implicit PASS."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import holidays
import pycountry
from dateutil.parser import parse as parse_datetime
from num2words import num2words

from schema import COLUMNS, SCHEMA
from context import check_directory, correct_name, resolve_checkbox


def clean(value):
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else value


def letters(value):
    return isinstance(value, str) and any(c.isalpha() for c in value)


def current_date(timezone):
    try:
        return datetime.now(ZoneInfo(timezone)).date()
    except ZoneInfoNotFoundError:
        raise ValueError("Timezone database unavailable; install tzdata (Windows) or pass --as-of YYYY-MM-DD")


def parse_number(raw, locale="id_ID"):
    """Strict document-locale parsing; currency never determines separator convention."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("MISSING_NUMBER")
    # Allow explicit currency labels/symbols at edges only, never inside a number.
    s = raw.strip()
    s = re.sub(r"^(?:[A-Za-z]{3}|Rp\.?|[$€£¥])\s*", "", s)
    s = re.sub(r"\s*(?:[A-Za-z]{3}|Rp\.?|[$€£¥])$", "", s)
    group, dec = (".", ",") if locale == "id_ID" else (",", ".")
    pattern = rf"[+-]?(?:\d+|\d{{1,3}}(?:{re.escape(group)}\d{{3}})+)(?:{re.escape(dec)}\d+)?"
    if not re.fullmatch(pattern, s):
        raise ValueError("INVALID_OR_AMBIGUOUS_NUMBER")
    value = Decimal(s.replace(group, "").replace(dec, "."))
    if not value.is_finite() or value <= 0:
        raise ValueError("NUMBER_MUST_BE_POSITIVE")
    return value


MONTHS = dict(zip(
    "januari februari maret april mei juni juli agustus september oktober november desember jan feb mar apr jun jul agu ags sep okt nov des".split(),
    "January February March April May June July August September October November December Jan Feb Mar Apr Jun Jul Aug Aug Sep Oct Nov Dec".split()))


def parse_date(raw, day_first=True, pivot=49):
    s = clean(raw)
    if not isinstance(s, str) or not s:
        raise ValueError("MISSING_DATE")
    s = re.sub(r"\b[A-Za-z]+\b", lambda m: MONTHS.get(m[0].lower(), m[0]), s)
    s = re.sub(r"\s*([/.-])\s*", r"\1", s)
    # Require all components rather than letting dateutil fill from today's date.
    numeric = re.fullmatch(r"(\d{1,4})[/.-](\d{1,2})[/.-](\d{2}|\d{4})", s)
    if numeric:
        a, b, c = numeric.groups()
        if len(a) == 4:
            return date(int(a), int(b), int(c))
        y = int(c)
        if len(c) == 2:
            y += 2000 if y <= pivot else 1900
        d, m = (int(a), int(b)) if day_first else (int(b), int(a))
        return date(y, m, d)
    if not re.fullmatch(r"(?:\d{1,2}[\s-]+[A-Za-z]+[\s,-]+\d{4}|[A-Za-z]+[\s-]+\d{1,2}[\s,-]+\d{4})", s):
        raise ValueError("INVALID_OR_INCOMPLETE_DATE")
    return parse_datetime(s, dayfirst=day_first, fuzzy=False, default=datetime(1, 1, 1)).date()


def check_schema(value, schema=SCHEMA, path=""):
    """Validate exact types locally, including nullable objects/arrays, without coercion."""
    allowed = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    typ = ("null" if value is None else "boolean" if isinstance(value, bool) else
           "string" if isinstance(value, str) else "array" if isinstance(value, list) else
           "object" if isinstance(value, dict) else "number" if isinstance(value, (int, float, Decimal)) else "unknown")
    if typ not in allowed:
        raise ValueError(f"Schema mismatch at {path or '$'}: expected {allowed}, got {typ}")
    if typ == "object":
        missing = set(schema.get("required", [])) - value.keys()
        if missing:
            raise ValueError(f"Schema missing fields at {path or '$'}: {sorted(missing)}")
        extra = value.keys() - schema["properties"].keys()
        if extra:
            raise ValueError(f"Schema unexpected fields at {path or '$'}: {sorted(extra)}")
        for key, child in schema["properties"].items():
            if key in value:
                check_schema(value[key], child, f"{path}.{key}".strip("."))
    if typ == "array":
        for i, child in enumerate(value):
            check_schema(child, schema["items"], f"{path}[{i}]")


def confidence_values(node):
    """Read observed numeric confidence leaves; do not synthesize confidence."""
    result = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "confidence" and isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                result.append(float(value))
            elif isinstance(value, (dict, list)):
                result.extend(confidence_values(value))
    elif isinstance(node, list):
        for value in node:
            result.extend(confidence_values(value))
    return result


def text_key(s):
    return " ".join(re.findall(r"[^\W\d_]+", (s or "").casefold()))


CURRENCY_NAMES = {
    "IDR": ("rupiah", "rupiah"), "USD": ("dolar amerika serikat", "US dollars"),
    "EUR": ("euro", "euros"), "JPY": ("yen", "yen"), "CNY": ("yuan", "yuan"),
    "SGD": ("dolar singapura", "Singapore dollars"), "AUD": ("dolar australia", "Australian dollars"),
    "GBP": ("pound sterling", "pounds sterling"), "HKD": ("dolar hong kong", "Hong Kong dollars"),
    "CHF": ("franc swiss", "Swiss francs")}


def generated_words(total, code, lang):
    if lang not in {"id", "en"} or code not in CURRENCY_NAMES:
        return None
    minor_digits = 0 if code == "JPY" else 2
    if total != total.quantize(Decimal(10) ** -minor_digits):
        return None
    integer = int(total)
    fraction = int((total - integer) * 100)
    name = CURRENCY_NAMES[code][lang == "en"]
    words = f"{num2words(integer, lang=lang)} {name}"
    if fraction:
        unit = "sen" if lang == "id" else "cents"
        words += f" {'dan' if lang == 'id' else 'and'} {num2words(fraction, lang=lang)} {unit}"
    return words


def validate(raw, metadata, policy, as_of=None, directory=None, validation_context=None):
    check_schema(raw)
    directory = directory or {}
    check_directory(directory)
    context = validation_context or {}
    normalized = deepcopy(raw)
    corrections, suggestions, checkbox_resolutions = [], [], {}
    reports = {key: {"raw_value": deepcopy(raw[key]), "normalized_value": None,
                    "status": "PASS", "issues": [], "metadata": {}}
               for key, _ in COLUMNS}

    def issue(key, code, severity="FAIL"):
        report = reports[key]
        report["issues"].append({"code": code, "severity": severity})
        if report["status"] != "FAIL":
            report["status"] = severity

    def text(key, required=False, require_letters=True):
        normalized[key] = clean(raw[key])
        if not normalized[key]:
            if required:
                issue(key, "REQUIRED")
            else:
                reports[key]["status"] = "NOT_PRESENT"
        elif require_letters and not letters(normalized[key]):
            issue(key, "LETTERS_REQUIRED")

    def enum(key, allowed):
        selected = checkbox_resolutions[key]["selected"]
        if selected is None:
            normalized[key] = None
            issue(key, "CHECKBOX_UNCERTAIN", "REVIEW")
        elif len(selected) != 1:
            normalized[key] = selected
            issue(key, "EXACTLY_ONE_SELECTION_REQUIRED")
        else:
            value = clean(selected[0])
            value = policy["enum_aliases"].get(value.casefold(), value)
            canon = next((x for x in allowed if x.casefold() == value.casefold()), None)
            normalized[key] = canon or value
            if canon is None:
                issue(key, "INVALID_ENUM")

    text("branch", True)
    for key in ["source_of_funds", "transaction_purpose", "transaction_bank_name", "notes"]:
        text(key, require_letters=key == "transaction_bank_name")
    if normalized["transaction_bank_name"]:
        issue("transaction_bank_name", "BANK_NAME_COMPLETENESS_REQUIRES_REVIEW", "REVIEW")
    if raw["notes"] and any(unicodedata.category(c).startswith("C") and c not in "\n\r\t" for c in raw["notes"]):
        issue("notes", "UNSUPPORTED_CONTROL_SYMBOL")
    try:
        d = parse_date(raw["transaction_date"], policy["day_first"], policy["two_digit_year_pivot"])
        normalized["transaction_date"] = d.strftime("%d-%m-%Y")
        if d > (as_of or current_date(policy["timezone"])):
            issue("transaction_date", "FUTURE_DATE")
        if d.weekday() >= 5:
            issue("transaction_date", "WEEKEND")
        if policy["include_indonesian_public_holidays"]:
            categories = [holidays.PUBLIC]
            if policy["include_joint_leave"]:
                categories.append(holidays.GOVERNMENT)
            calendar = holidays.country_holidays("ID", years=[d.year], categories=categories)
            if d in calendar:
                issue("transaction_date", "INDONESIAN_HOLIDAY_OR_JOINT_LEAVE")
        if d.isoformat() in policy["additional_closed_dates"]:
            issue("transaction_date", "BANK_CLOSED_DATE")
    except (ValueError, TypeError, OverflowError) as e:
        normalized["transaction_date"] = None
        issue("transaction_date", "INVALID_DATE: " + str(e))

    for key in ["payment_type", "transaction_type", "charges"]:
        resolution = resolve_checkbox(raw[key], policy)
        checkbox_resolutions[key] = resolution
        reports[key]["checkbox_resolution"] = resolution
        for code in resolution["issues"]:
            issue(key, code, "REVIEW")
        if resolution["reconciled"]:
            corrections.append({"field": key + ".selected", "before": raw[key]["selected"],
                                "after": resolution["selected"], "method": "local_checkbox_evidence",
                                "review_required": True})
    enum("payment_type", policy["payment_types"])
    enum("transaction_type", policy["transaction_types"])
    if normalized["transaction_type"] == "Lainnya" and not normalized["notes"]:
        issue("transaction_type", "LAINNYA_REQUIRES_NOTES")

    for key in ["beneficiary", "remitter"]:
        normalized[key] = {k: clean(v) for k, v in raw[key].items()}
        for field in ["name", "address"]:
            if not normalized[key][field]:
                issue(key, f"{field.upper()}_REQUIRED")
            elif not letters(normalized[key][field]):
                issue(key, f"{field.upper()}_LETTERS_REQUIRED")
    normalized["beneficiary_bank"] = {k: clean(v) for k, v in raw["beneficiary_bank"].items()}
    if not normalized["beneficiary_bank"]["name"] or not letters(normalized["beneficiary_bank"]["name"]):
        issue("beneficiary_bank", "BANK_NAME_REQUIRED_WITH_LETTERS")

    # Names are corrected only after extraction, retaining the untouched raw evidence.
    def name_correction(field, bucket, subkey=None, swift=None, bank_context=None):
        before = normalized[field][subkey] if subkey else normalized[field]
        result = correct_name(before, directory, bucket, policy, swift, bank_context)
        path = field + ("." + subkey if subkey else "")
        if result["applied"]:
            if subkey:
                normalized[field][subkey] = result["value"]
            else:
                normalized[field] = result["value"]
            entry = {"field": path, "before": before, "after": result["value"],
                     "method": result["method"], "review_required": policy.get("corrections_require_review", True)}
            corrections.append(entry)
            reports[field].setdefault("corrections", []).append(entry)
            if entry["review_required"]:
                issue(field, "APPROVED_OCR_ALIAS_APPLIED", "REVIEW")
        elif result["candidates"]:
            suggestions.append({"field": path, "observed": before, "candidates": result["candidates"],
                                "method": result["method"], "applied": False})
        for code in result["issues"]:
            issue(field, code, "REVIEW")

    name_correction("branch", "branch_names")
    name_correction("beneficiary_bank", "bank_names", "name", swift=(clean(raw["swift_code"]) or "").upper())
    name_correction("beneficiary_bank", "bank_branch_names", "branch", bank_context=normalized["beneficiary_bank"]["name"])
    name_correction("transaction_bank_name", "bank_names")
    for key in ["beneficiary_account_number", "remitter_account_number", "transaction_account_number"]:
        normalized[key] = clean(raw[key])
        if normalized[key] and not re.fullmatch(r"[A-Za-z0-9-]+", normalized[key]):
            issue(key, "ACCOUNT_ALPHANUMERIC_HYPHEN_ONLY")
        elif not normalized[key]:
            reports[key]["status"] = "NOT_PRESENT"
    normalized["swift_code"] = clean(raw["swift_code"])
    if normalized["swift_code"]:
        normalized["swift_code"] = normalized["swift_code"].upper()
        if not re.fullmatch(r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?", normalized["swift_code"]):
            issue("swift_code", "INVALID_BIC_STRUCTURE")
        # A syntactically plausible code is not verified against the bank's BIC directory.
    else:
        reports["swift_code"]["status"] = "NOT_PRESENT"
    normalized["currency"] = (clean(raw["currency"]) or "").upper() or None
    code = normalized["currency"]
    if not code or pycountry.currencies.get(alpha_3=code) is None:
        issue("currency", "INVALID_ISO_4217")
    elif code not in policy["supported_currencies"]:
        issue("currency", "CURRENCY_NOT_SUPPORTED")

    for key in ["exchange_rate", "amount", "charges", "total_amount"]:
        value = raw[key] if key == "exchange_rate" else raw[key]["raw"]
        try:
            normalized[key] = parse_number(value, policy["number_locale"])
        except ValueError as e:
            normalized[key] = None
            if key == "exchange_rate" and not value and code == "IDR":
                reports[key]["status"] = "NOT_PRESENT"
            else:
                issue(key, str(e))
    selected = checkbox_resolutions["charges"]["selected"]
    charge_method = None
    if selected is None:
        issue("charges", "CHECKBOX_UNCERTAIN", "REVIEW")
    elif len(selected) != 1:
        issue("charges", "EXACTLY_ONE_CHARGE_METHOD_REQUIRED")
    else:
        charge_method = policy["enum_aliases"].get(clean(selected[0]).casefold(), clean(selected[0]))
        if charge_method.casefold() not in {"tunai", "debet rekening"}:
            issue("charges", "INVALID_CHARGE_PAYMENT_METHOD")
        else:
            charge_method = "Tunai" if charge_method.casefold() == "tunai" else "Debet Rekening"

    values = [normalized[k] for k in ["amount", "charges", "total_amount"]]
    currencies = [(clean(raw[k]["currency"]) or "").upper() for k in ["amount", "charges", "total_amount"]]
    # Rp is an explicit, unambiguous label; '$' is deliberately not treated as USD.
    currencies = ["IDR" if c in {"RP", "RP.", "RUPIAH"} else c for c in currencies]
    if currencies[0] and currencies[0] != code:
        issue("amount", "AMOUNT_CURRENCY_DIFFERS_FROM_TRANSACTION_CURRENCY")
    if policy["assume_unlabelled_money_currency"]:
        currencies = [c or code for c in currencies]
    if not all(v is not None for v in values):
        issue("total_amount", "TOTAL_CHECK_MISSING_OPERANDS", "REVIEW")
    elif not all(currencies) or len(set(currencies)) != 1:
        issue("total_amount", "TOTAL_CHECK_CURRENCY_UNCERTAIN_OR_DIFFERENT", "REVIEW")
    elif abs(values[0] + values[1] - values[2]) > Decimal(policy["total_tolerance"]):
        issue("total_amount", "AMOUNT_PLUS_CHARGES_MISMATCH")
    normalized["charges"] = {"payment_method": charge_method, "amount": normalized["charges"], "currency": currencies[1] or None}

    words = raw["amount_in_words"]
    normalized["amount_in_words"] = clean(words["raw"])
    generated = generated_words(normalized["total_amount"], currencies[2], words["language"]) if normalized["total_amount"] is not None else None
    if not normalized["amount_in_words"] or words["complete"] is False:
        issue("amount_in_words", "WORDS_MISSING_OR_INCOMPLETE")
    elif words["complete"] is not True:
        issue("amount_in_words", "WORDS_READABILITY_UNCERTAIN", "REVIEW")
    if generated is None:
        issue("amount_in_words", "WORDS_TOTAL_OR_CURRENCY_UNAVAILABLE", "REVIEW")
    elif text_key(generated) != text_key(words["raw"]):
        # Wording has valid variants. Do not falsely reject or assert semantic agreement.
        issue("amount_in_words", "WORDS_SEMANTIC_CHECK_REQUIRES_REVIEW", "REVIEW")

    for key, required in [("customer_signature", ["present", "handwritten"]), ("bank_approval", ["present", "stamp_present"])]:
        for field in required:
            if raw[key][field] is False:
                issue(key, field.upper() + "_REQUIRED")
            elif raw[key][field] is None:
                issue(key, field.upper() + "_UNCERTAIN", "REVIEW")
    if not policy["bank_stamp_rule_confirmed"]:
        issue("bank_approval", "STAMP_REQUIREMENT_NUMBER_3_NOT_CONFIGURED", "REVIEW")
    else:
        for fragment in policy["required_stamp_text_fragments"]:
            if fragment.casefold() not in (raw["bank_approval"]["stamp_text"] or "").casefold():
                issue("bank_approval", "REQUIRED_STAMP_TEXT_MISSING: " + fragment)

    field_meta = (metadata or {}).get("field_metadata", {}).get("document_metadata", {}) or {}
    for key, report in reports.items():
        report["normalized_value"] = normalized[key]
        report["metadata"] = field_meta.get(key, {})
        scores = confidence_values(report["metadata"])
        report["confidence"] = min(scores) if scores else None
        if report["status"] != "NOT_PRESENT":
            if scores and min(scores) < policy["minimum_confidence"]:
                issue(key, "LOW_EXTRACTION_CONFIDENCE", "REVIEW")
            elif not scores and policy["require_confidence"]:
                issue(key, "CONFIDENCE_UNAVAILABLE", "REVIEW")

    # Cross-document correction: a bad remitter value (missing or low-confidence) is
    # replaced with an authoritative value from a trusted cross-source such as eKTP.
    # The original evidence is retained in the correction record and the field is
    # marked REVIEW because the value was not read from this document. No silent
    # overwrite: provenance (before/after/method) is always recorded.
    authoritative = context.get("authoritative") or {}

    def cross_correct(key, subkey, source_key):
        before = normalized[key].get(subkey)
        low_confidence = any(
            i.get("code") in {"LOW_EXTRACTION_CONFIDENCE", "CONFIDENCE_UNAVAILABLE"}
            for i in reports[key]["issues"]
        )
        if before and not low_confidence:
            return
        replacement = authoritative.get(source_key)
        if not replacement or replacement == before:
            return
        normalized[key][subkey] = replacement
        entry = {
            "field": f"{key}.{subkey}",
            "before": before,
            "after": replacement,
            "method": "cross_document_ektp_authoritative",
            "review_required": True,
        }
        corrections.append(entry)
        reports[key].setdefault("corrections", []).append(entry)
        # The missing-value FAIL that the correction resolves is removed; any other
        # FAIL issue (e.g. LETTERS_REQUIRED) is retained. Status is recomputed so the
        # case is not hard-failed on a value a trusted cross-source supplied.
        reports[key]["issues"] = [
            i for i in reports[key]["issues"]
            if i.get("code") != f"{subkey.upper()}_REQUIRED"
        ]
        severities = [i.get("severity", "FAIL") for i in reports[key]["issues"]]
        reports[key]["status"] = (
            "FAIL" if "FAIL" in severities
            else "REVIEW" if "REVIEW" in severities
            else "PASS"
        )
        issue(key, "CROSS_DOCUMENT_CORRECTION_APPLIED", "REVIEW")

    cross_correct("remitter", "address", "address")
    cross_correct("remitter", "name", "name")

    status = "FAIL" if any(r["status"] == "FAIL" for r in reports.values()) else "REVIEW" if any(r["status"] == "REVIEW" for r in reports.values()) else "PASS"
    return {"status": status, "raw": raw, "normalized": normalized,
            "fields": reports, "generated_amount_in_words": generated,
            "corrections": corrections, "correction_suggestions": suggestions,
            "checkbox_resolutions": checkbox_resolutions, "name_directory": directory,
            "transaction_other_description": raw["transaction_type"]["other_description"],
            "money_currencies": dict(zip(["amount", "charges", "total_amount"], currencies)),
            "as_of": (as_of or current_date(policy["timezone"])).isoformat(), "policy": policy}
