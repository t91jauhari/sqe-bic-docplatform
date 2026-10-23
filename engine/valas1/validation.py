"""Valas 1 section-specific rules on top of shared declaration checks."""
from decimal import Decimal
import re
import unicodedata

import holidays
import pycountry

from validation import clean, parse_date
from valas_common import validate_declaration
from valas1.schema import SCHEMA, COLUMNS, DOCUMENT_NAME


def validate_extra(raw, normalized, reports, issue, structural, policy, reference_date):
    def text(key, required=True):
        observation = raw[key]
        value = clean(observation["raw"]) or None
        normalized[key] = value
        structural(key, observation["raw"], value)
        if not value:
            if required:
                issue(key, "REQUIRED")
            return value
        if not any(c.isalnum() for c in value):
            issue(key, "SYMBOL_ONLY_TEXT")
        if any(unicodedata.category(c).startswith("C") and c not in "\n\r\t" for c in observation["raw"]):
            issue(key, "UNSUPPORTED_CONTROL_SYMBOL")
        if observation["complete"] is False:
            issue(key, "TEXT_INCOMPLETE_OR_UNREADABLE")
        elif observation["complete"] is not True:
            issue(key, "TEXT_COMPLETENESS_UNCERTAIN", "REVIEW")
        return value

    text("usage_purpose")
    text("receipt_source")

    if not isinstance(policy.get("identity_rule_confirmed"), bool):
        raise ValueError("identity_rule_confirmed must be boolean")
    if policy.get("identity_required") is not None and not isinstance(policy["identity_required"], bool):
        raise ValueError("identity_required must be boolean/null")
    pattern = policy.get("identity_pattern")
    if pattern is not None and (not isinstance(pattern, str) or not pattern):
        raise ValueError("identity_pattern must be a nonempty regex string or null")
    try:
        compiled = re.compile(pattern) if pattern else None
    except re.error as exc:
        raise ValueError("Invalid identity_pattern regex") from exc
    configured = policy["identity_rule_confirmed"] and policy.get("identity_required") is not None
    identity = text("identity_number", required=configured and policy["identity_required"])
    if not configured:
        issue("identity_number", "IDENTITY_RULE_NOT_CONFIGURED", "REVIEW")
    elif not identity and not policy["identity_required"]:
        reports["identity_number"]["status"] = "NOT_PRESENT"
    elif identity:
        if compiled is None:
            issue("identity_number", "IDENTITY_FORMAT_RULE_NOT_CONFIGURED", "REVIEW")
        elif not compiled.fullmatch(identity):
            issue("identity_number", "INVALID_IDENTITY_FORMAT")

    npwp_value = text("npwp", required=raw["npwp"]["available"] is True)
    if not npwp_value:
        if raw["npwp"]["available"] is not True:
            reports["npwp"]["status"] = "NOT_PRESENT"
            if raw["npwp"]["available"] is None and raw["npwp"]["complete"] is False:
                issue("npwp", "NPWP_REGION_UNREADABLE", "REVIEW")
    else:
        # Accept a correctly formatted legacy 15-digit NPWP or its compact form,
        # or a 16-digit NIK-style identifier. Separators never repair bad digits.
        if re.fullmatch(r"[0-9]{2}\.[0-9]{3}\.[0-9]{3}\.[0-9]-[0-9]{3}\.[0-9]{3}|[0-9]{15,16}", npwp_value):
            normalized["npwp"] = npwp_value.replace(".", "").replace("-", "")
            structural("npwp", npwp_value, normalized["npwp"], "remove_allowed_npwp_format_separators")
        else:
            issue("npwp", "INVALID_NPWP_STRUCTURE")
        if raw["npwp"]["available"] is False:
            issue("npwp", "NPWP_AVAILABILITY_CONFLICT", "REVIEW")

    if not isinstance(policy.get("additional_closed_dates"), list):
        raise ValueError("additional_closed_dates must be an array of YYYY-MM-DD strings")
    for entry in policy["additional_closed_dates"]:
        try:
            if not isinstance(entry, str) or parse_date(entry).isoformat() != entry:
                raise ValueError()
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("additional_closed_dates must contain valid YYYY-MM-DD strings") from exc
    for key in ["usage_date", "receipt_date"]:
        try:
            parsed = parse_date(raw[key], policy["day_first"], policy["two_digit_year_pivot"])
            normalized[key] = parsed.strftime("%d-%m-%Y")
            structural(key, raw[key], normalized[key], "standardize_date")
            if key == "usage_date":
                if parsed > reference_date:
                    issue(key, "FUTURE_DATE")
                if parsed.weekday() >= 5:
                    issue(key, "WEEKEND")
                if policy["include_indonesian_public_holidays"]:
                    categories = [holidays.PUBLIC] + ([holidays.GOVERNMENT] if policy["include_joint_leave"] else [])
                    if parsed in holidays.country_holidays("ID", years=[parsed.year], categories=categories):
                        issue(key, "INDONESIAN_HOLIDAY_OR_JOINT_LEAVE")
                if parsed.isoformat() in policy["additional_closed_dates"]:
                    issue(key, "BANK_CLOSED_DATE")
        except (ValueError, TypeError, OverflowError):
            normalized[key] = None
            issue(key, "INVALID_OR_MISSING_DATE")

    locale = policy["number_locale"]
    if locale not in {"id_ID", "en_US"}:
        raise ValueError("number_locale must be id_ID or en_US")
    group, decimal = (".", ",") if locale == "id_ID" else (",", ".")
    numeric_pattern = rf"[+-]?(?:[0-9]+|[0-9]{{1,3}}(?:{re.escape(group)}[0-9]{{3}})+)(?:{re.escape(decimal)}[0-9]+)?"
    aliases = policy.get("currency_aliases", {})
    if not isinstance(aliases, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in aliases.items()):
        raise ValueError("currency_aliases must map explicit currency names to ISO codes")
    aliases = {k.upper(): v.upper() for k, v in aliases.items()}
    for key in ["usage_amount", "receipt_amount"]:
        observation = raw[key]
        amount_text = clean(observation["amount_raw"])
        amount = None
        if not amount_text:
            issue(key, "MISSING_NUMBER")
        elif not re.fullmatch(numeric_pattern, amount_text):
            issue(key, "INVALID_NUMBER_FORMAT")
        else:
            amount = Decimal(amount_text.replace(group, "").replace(decimal, "."))
            if amount <= 0:
                issue(key, "NUMBER_MUST_BE_POSITIVE")
        currency_raw = clean(observation["currency_raw"])
        currency = (currency_raw or "").upper()
        currency = aliases.get(currency, currency)
        if currency in {"$", "¥", "DOLLAR", "DOLAR", "YEN", "YUAN"}:
            currency = None
            issue(key, "CURRENCY_AMBIGUOUS", "REVIEW")
        elif not re.fullmatch(r"[A-Z]{3}", currency) or pycountry.currencies.get(alpha_3=currency) is None:
            issue(key, "INVALID_OR_MISSING_ISO_4217_CODE")
            currency = None
        normalized[key] = {"amount": amount, "currency": currency}
        structural(key + ".currency", observation["currency_raw"], currency, "uppercase_code_or_explicit_currency_alias")


def validate(raw, metadata, policy, as_of=None, directory=None, validation_context=None, extract_job_id=None):
    return validate_declaration(raw, metadata, policy, as_of, directory, validation_context, extract_job_id,
                                schema=SCHEMA, columns=COLUMNS, document_type="valas_declaration_1",
                                document_name=DOCUMENT_NAME, extra_validator=validate_extra)
