"""Invoice evidence validation and independent Decimal calculations."""
from copy import deepcopy
from decimal import Decimal, localcontext, ROUND_HALF_UP, ROUND_HALF_EVEN
import re
import unicodedata

import holidays
import pycountry

from context import correct_name, identity
from validation import check_schema, clean, parse_date, current_date, confidence_values
from invoice.schema import SCHEMA, COLUMNS


def decimal_literal(raw, locale):
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("MISSING_NUMBER")
    group, decimal = (".", ",") if locale == "id_ID" else (",", ".")
    pattern = rf"[+-]?(?:[0-9]+|[0-9]{{1,3}}(?:{re.escape(group)}[0-9]{{3}})+)(?:{re.escape(decimal)}[0-9]+)?"
    if not re.fullmatch(pattern, raw.strip()):
        raise ValueError("INVALID_NUMBER_FORMAT")
    return Decimal(raw.strip().replace(group, "").replace(decimal, "."))


def multiply(a, b):
    with localcontext() as ctx:
        ctx.prec = max(50, len(a.as_tuple().digits) + len(b.as_tuple().digits) + 10)
        return a * b


def sum_decimals(values):
    with localcontext() as ctx:
        ctx.prec = max(50, max((len(x.as_tuple().digits) + abs(x.adjusted()) for x in values), default=1) + len(values) + 10)
        return sum(values, Decimal(0))


def validate(raw, metadata, policy, as_of=None, directory=None, validation_context=None):
    check_schema(raw, SCHEMA)
    context = validation_context or {}
    if not isinstance(context, dict) or not isinstance(context.get("invoice_numbers", []), list):
        raise ValueError("Invoice validation context must contain an invoice_numbers array")
    if any(not isinstance(x, str) for x in context.get("invoice_numbers", [])):
        raise ValueError("Known invoice numbers must be strings")
    locales = policy.get("field_number_locales", {})
    if not isinstance(locales, dict) or any(x not in {"en_US", "id_ID"} for x in locales.values()):
        raise ValueError("field_number_locales must map field paths to en_US or id_ID")
    if policy["ambiguous_number_action"] not in {"REVIEW", "USE_CONFIGURED_LOCALE"}:
        raise ValueError("ambiguous_number_action must be REVIEW or USE_CONFIGURED_LOCALE")
    tolerance = Decimal(str(policy["amount_tolerance"]))
    if not tolerance.is_finite() or tolerance < 0:
        raise ValueError("amount_tolerance must be finite and nonnegative")
    rounding = {"ROUND_HALF_UP": ROUND_HALF_UP, "ROUND_HALF_EVEN": ROUND_HALF_EVEN}.get(policy["rounding"])
    if rounding is None:
        raise ValueError("rounding must be ROUND_HALF_UP or ROUND_HALF_EVEN")
    if policy["account_storage_mode"] not in {"numeric_only", "alphanumeric", "alphanumeric_with_numeric_conflict_review"}:
        raise ValueError("Unknown account_storage_mode")
    normalized = {key: None for key, _ in COLUMNS}
    fields = {key: {"raw_value": deepcopy(raw[key]), "normalized_value": None, "status": "PASS", "issues": []} for key, _ in COLUMNS}
    corrections, suggestions, numeric_candidates, line_checks = [], [], {}, []
    reference = as_of or current_date(policy["timezone"])

    def issue(key, code, severity="FAIL", **detail):
        fields[key]["issues"].append({"code": code, "severity": severity, **detail})
        if fields[key]["status"] != "FAIL":
            fields[key]["status"] = severity

    def number(key, value, path=None, allow_zero=False, absolute=False):
        path = path or key
        override = locales.get(path, locales.get(key))
        candidates = {}
        for locale in ["en_US", "id_ID"]:
            try:
                candidates[locale] = decimal_literal(value, locale)
            except ValueError:
                pass
        if not candidates:
            issue(key, "MISSING_NUMBER" if not value else "INVALID_NUMBER_FORMAT", path=path)
            return None
        numeric_candidates[path] = candidates
        if override or policy["ambiguous_number_action"] == "USE_CONFIGURED_LOCALE":
            result = candidates.get(override or policy["number_locale"])
            if result is None:
                issue(key, "NUMBER_DOES_NOT_MATCH_CONFIGURED_LOCALE", path=path)
                return None
        elif len(set(candidates.values())) > 1:
            issue(key, "AMBIGUOUS_NUMBER_SEPARATORS", "REVIEW", path=path, candidates=candidates)
            return None
        else:
            result = next(iter(candidates.values()))
        if absolute:
            result = result.copy_abs()
        if result < 0 or (result == 0 and not allow_zero):
            issue(key, "NUMBER_MUST_BE_NONNEGATIVE" if allow_zero else "NUMBER_MUST_BE_POSITIVE", path=path)
            return None
        return result

    def currency(key, value, path=None):
        value = clean(value)
        aliases = {k.casefold(): v for k, v in policy["currency_aliases"].items()}
        code = aliases.get((value or "").casefold(), (value or "").upper())
        if pycountry.currencies.get(alpha_3=code) is not None:
            return code
        issue(key, "CURRENCY_REQUIRED" if not value else "AMBIGUOUS_CURRENCY_SYMBOL" if value in {"$", "¥"} else "INVALID_ISO_CURRENCY",
              "REVIEW" if value in {"$", "¥"} else "FAIL", path=path or key)
        return None

    def money(key, entry, path=None, allow_zero=False, absolute=False):
        return {"currency": currency(key, entry["currency_raw"], path),
                "amount": number(key, entry["amount_raw"], path, allow_zero, absolute)}

    def rounded(value, code):
        places = policy["currency_decimal_places"].get(code, policy["calculation_decimal_places"])
        if isinstance(places, bool) or not isinstance(places, int) or not 0 <= places <= 8:
            raise ValueError("Calculation decimal places must be an integer from 0 to 8")
        with localcontext() as ctx:
            ctx.prec = max(50, len(value.as_tuple().digits) + abs(value.adjusted()) + places + 10)
            return value.quantize(Decimal(1).scaleb(-places), rounding=rounding)

    def compare(key, printed, calculated, path=None):
        if calculated is None or printed is None:
            issue(key, "ARITHMETIC_CHECK_UNAVAILABLE", "REVIEW", path=path or key)
            return None
        difference = sum_decimals([printed, calculated.copy_negate()])
        if difference.copy_abs() > tolerance:
            issue(key, "PRINTED_AMOUNT_MISMATCH", path=path or key, printed=printed, calculated=calculated, difference=difference)
        return difference

    def text_field(key, require_letters=False):
        entry = raw[key]
        value = clean(entry["raw"])
        if value and key in {"to_address", "from_address"}:
            normalized_punctuation = re.sub(r"\s+([,;:])", r"\1", value)
            if normalized_punctuation != value:
                corrections.append({"field": key, "before": value, "after": normalized_punctuation,
                                    "method": "address_punctuation_spacing", "review_required": False})
            value = normalized_punctuation
        normalized[key] = value
        if not value:
            issue(key, "REQUIRED_TEXT")
        elif require_letters and not any(c.isalpha() for c in value):
            issue(key, "NAME_MUST_CONTAIN_LETTERS")
        elif not any(c.isalnum() for c in value):
            issue(key, "SYMBOL_ONLY_TEXT")
        if value:
            if entry["complete"] is False:
                issue(key, "TEXT_INCOMPLETE_OR_UNREADABLE")
            elif entry["complete"] is not True:
                issue(key, "TEXT_COMPLETENESS_UNCERTAIN", "REVIEW")
            if any(unicodedata.category(c).startswith("C") and c not in "\n\r\t" for c in entry["raw"]):
                issue(key, "UNSUPPORTED_CONTROL_SYMBOL")

    for key in ["to_name", "from_name", "bank_name", "to_address", "from_address"]:
        text_field(key, key in {"to_name", "from_name", "bank_name"})
    for key, required in [("to_phone", True), ("from_phone", False)]:
        value = clean(raw[key])
        normalized[key] = value
        if not value:
            if required:
                issue(key, "PHONE_REQUIRED")
            else:
                fields[key]["status"] = "NOT_PRESENT"
            continue
        prefix = value[:value.index("+")].strip() if "+" in value else ""
        if (not re.fullmatch(r"[0-9+()\- ]+", value) or not any(c.isdigit() for c in value)
                or value.count("+") > 1 or prefix not in {"", "("}):
            issue(key, "INVALID_PHONE_CHARACTERS_OR_FORMAT")
        balance = 0
        for character in value:
            balance += (1 if character == "(" else -1 if character == ")" else 0)
            if balance < 0:
                break
        if balance != 0:
            issue(key, "UNBALANCED_PHONE_PARENTHESES")

    swift = clean(raw["swift_code"])
    normalized["swift_code"] = swift.upper() if swift else None
    if swift and any(c.islower() for c in swift):
        issue("swift_code", "LOWERCASE_BIC_INPUT")
    bic = normalized["swift_code"]
    if not bic or not re.fullmatch(r"[A-Z0-9]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?", bic):
        issue("swift_code", "INVALID_BIC_STRUCTURE")
    elif pycountry.countries.get(alpha_2=bic[4:6]) is None and bic[4:6] != "XK":
        issue("swift_code", "INVALID_BIC_COUNTRY_CODE")
    account = raw["bank_account_number"]
    account = re.sub(r"[\s-]+", "", account) if account else None
    normalized["bank_account_number"] = account
    if not account or not re.fullmatch(r"[A-Za-z0-9]+", account):
        issue("bank_account_number", "INVALID_OR_MISSING_BANK_ACCOUNT")
    elif not account.isdigit() and policy["account_storage_mode"] != "alphanumeric":
        issue("bank_account_number", "ALPHANUMERIC_ACCOUNT_CONFLICTS_WITH_NUMERIC_STORAGE_RULE",
              "FAIL" if policy["account_storage_mode"] == "numeric_only" else "REVIEW")
    if account != raw["bank_account_number"]:
        corrections.append({"field": "bank_account_number", "before": raw["bank_account_number"], "after": account,
                            "method": "account_format_separators", "review_required": False})
    corrected = correct_name(normalized["bank_name"], directory or {}, "bank_names", policy, swift=bic)
    normalized["bank_name"] = corrected["value"]
    if corrected["applied"]:
        corrections.append({"field": "bank_name", "before": clean(raw["bank_name"]["raw"]), "after": corrected["value"],
                            "method": corrected["method"], "review_required": policy["corrections_require_review"]})
        if policy["corrections_require_review"]:
            issue("bank_name", "APPROVED_OCR_ALIAS_APPLIED", "REVIEW")
    if corrected["candidates"] and not corrected["applied"]:
        suggestions.append({"field": "bank_name", **corrected})
    for code in corrected["issues"]:
        issue("bank_name", code, "REVIEW")
    master = policy["bank_master"]
    if master is not None:
        if not isinstance(master, list) or any(not isinstance(x, str) for x in master):
            raise ValueError("bank_master must be null or a string list")
        if normalized["bank_name"] and identity(normalized["bank_name"]) not in {identity(x) for x in master}:
            issue("bank_name", "BANK_NOT_IN_CONFIGURED_MASTER", "FAIL" if policy["bank_master_required"] else "REVIEW")
    elif policy["bank_master_required"]:
        issue("bank_name", "BANK_MASTER_NOT_CONFIGURED", "REVIEW")

    dates = {}
    for key in ["invoice_date", "due_date"]:
        try:
            date = parse_date(raw[key], policy["day_first"], policy["two_digit_year_pivot"])
            dates[key] = date
            normalized[key] = date.strftime("%d-%m-%Y")
            if date > reference and not (key == "due_date" and policy["due_date_allow_future"]):
                issue(key, "FUTURE_DATE")
            if date.weekday() >= 5:
                issue(key, "WEEKEND")
            if policy["include_indonesian_public_holidays"]:
                categories = [holidays.PUBLIC] + ([holidays.GOVERNMENT] if policy["include_joint_leave"] else [])
                if date in holidays.country_holidays("ID", years=[date.year], categories=categories):
                    issue(key, "INDONESIAN_HOLIDAY_OR_JOINT_LEAVE")
            if date.isoformat() in policy["additional_closed_dates"]:
                issue(key, "BANK_CLOSED_DATE")
        except (ValueError, TypeError, OverflowError):
            issue(key, "INVALID_OR_MISSING_DATE")
    if len(dates) == 2 and dates["due_date"] < dates["invoice_date"]:
        issue("due_date", "DUE_DATE_BEFORE_INVOICE_DATE")
    invoice_number = clean(raw["invoice_number"])
    normalized["invoice_number"] = invoice_number
    if not invoice_number or not re.fullmatch(r"[A-Za-z0-9_/-]+", invoice_number) or not any(c.isalnum() for c in invoice_number):
        issue("invoice_number", "INVALID_OR_MISSING_INVOICE_NUMBER")
    else:
        comparable = (lambda x: clean(x)) if policy["invoice_number_case_sensitive"] else (lambda x: clean(x).casefold())
        if comparable(invoice_number) in {comparable(x) for x in context.get("invoice_numbers", [])}:
            issue("invoice_number", "DUPLICATE_INVOICE_NUMBER_IN_HISTORY")
        elif context.get("invoice_history_complete") is not True:
            issue("invoice_number", "INVOICE_UNIQUENESS_NOT_CHECKED", "REVIEW")

    items = raw["item_name"]["items"] or []
    arrays = {"item_name": items, **{key: raw[key] or [] for key in ["quantity", "unit_price", "subtotal"]}}
    ids = [item["row_id"] for item in items]
    aligned = bool(ids) and ids == [str(i) for i in range(1, len(ids) + 1)]
    for key, entries in arrays.items():
        if not ids:
            issue(key, "LINE_ITEMS_REQUIRED")
        elif [entry["row_id"] for entry in entries] != ids or not aligned:
            aligned = False
            issue(key, "LINE_ITEM_ROW_IDS_MISSING_DUPLICATED_OR_MISALIGNED")
    if not aligned and ids:
        for key in arrays:
            if not any(x["code"] == "LINE_ITEM_ROW_IDS_MISSING_DUPLICATED_OR_MISALIGNED" for x in fields[key]["issues"]):
                issue(key, "LINE_ITEM_ROW_IDS_MISSING_DUPLICATED_OR_MISALIGNED")
    complete = raw["item_name"]["table_complete"] is True and aligned
    if raw["item_name"]["table_complete"] is not True:
        issue("item_name", "LINE_ITEM_TABLE_INCOMPLETE_OR_UNCERTAIN", "REVIEW")
    normalized["item_name"] = []
    for item in items:
        value = clean(item["raw"])
        normalized["item_name"].append({"row_id": item["row_id"], "text": value})
        if not value or not any(c.isalnum() for c in value):
            issue("item_name", "INVALID_OR_MISSING_ITEM_NAME", row_id=item["row_id"])
        if item["complete"] is False:
            issue("item_name", "ITEM_NAME_INCOMPLETE", row_id=item["row_id"])
        elif item["complete"] is not True:
            issue("item_name", "ITEM_NAME_COMPLETENESS_UNCERTAIN", "REVIEW", row_id=item["row_id"])
    for key in ["quantity", "unit_price", "subtotal"]:
        normalized[key] = []
    units = {key.casefold(): value for key, value in policy["unit_aliases"].items()}
    def unit(value):
        value = clean(value)
        return units.get(value.casefold(), value.upper()) if value else None
    if aligned:
        for item, quantity, price, printed in zip(items, arrays["quantity"], arrays["unit_price"], arrays["subtotal"]):
            row_id = item["row_id"]
            quantity_value = number("quantity", quantity["value_raw"], f"quantity[{row_id}]")
            if quantity_value is not None and quantity_value != quantity_value.to_integral_value():
                issue("quantity", "QUANTITY_MUST_BE_INTEGER", row_id=row_id)
                quantity_value = None
            visible = re.match(r"\s*([+-]?[0-9][0-9.,]*)", quantity["raw"] or "")
            if not visible or visible[1] != clean(quantity["value_raw"]):
                issue("quantity", "QUANTITY_COMPONENT_CONFLICTS_WITH_RAW_CELL", row_id=row_id)
                quantity_value = None
            quantity_unit, price_unit = unit(quantity["unit_raw"]), unit(price["unit_raw"])
            same_basis = True
            if price_unit and quantity_unit and price_unit != quantity_unit:
                issue("quantity", "QUANTITY_PRICE_UNIT_MISMATCH", row_id=row_id)
                same_basis = False
            elif price_unit and not quantity_unit:
                issue("quantity", "QUANTITY_PRICE_UNIT_BASIS_UNCERTAIN", "REVIEW", row_id=row_id)
                same_basis = False
            parsed_price = money("unit_price", price, f"unit_price[{row_id}]")
            parsed_printed = money("subtotal", printed, f"subtotal[{row_id}]")
            calculated = None
            if quantity_value is not None and parsed_price["amount"] is not None and parsed_price["currency"] and same_basis:
                calculated = rounded(multiply(quantity_value, parsed_price["amount"]), parsed_price["currency"])
            currency_matches = parsed_price["currency"] is not None and parsed_price["currency"] == parsed_printed["currency"]
            if not currency_matches:
                issue("subtotal", "LINE_ITEM_CURRENCY_MISMATCH_OR_MISSING",
                      "FAIL" if parsed_price["currency"] and parsed_printed["currency"] else "REVIEW", row_id=row_id)
            difference = compare("subtotal", parsed_printed["amount"], calculated, f"subtotal[{row_id}]") if currency_matches else None
            normalized["quantity"].append({"row_id": row_id, "value": int(quantity_value) if quantity_value is not None else None,
                                           "unit": quantity_unit, "other_quantity_note": quantity["other_quantity_note"]})
            normalized["unit_price"].append({"row_id": row_id, **parsed_price, "unit": price_unit})
            normalized["subtotal"].append({"row_id": row_id, "currency": parsed_price["currency"], "amount": calculated})
            status = "REVIEW" if calculated is None or difference is None else "FAIL" if difference.copy_abs() > tolerance else "PASS"
            if any(problem["severity"] == "FAIL" and (problem.get("row_id") == row_id or problem.get("path") == f"{key}[{row_id}]")
                   for key in arrays for problem in fields[key]["issues"]):
                status = "FAIL"
            line_checks.append({"row_id": row_id, "item_name": clean(item["raw"]), "quantity": int(quantity_value) if quantity_value is not None else None,
                                "quantity_unit": quantity_unit, "unit_price": parsed_price["amount"], "price_unit": price_unit,
                                "currency": parsed_price["currency"], "printed_subtotal": parsed_printed["amount"], "computed_subtotal": calculated,
                                "difference": difference, "check_status": status, "other_quantity_note": quantity["other_quantity_note"]})
    computed_currency, computed_sum = None, None
    amounts = normalized["subtotal"]
    if complete and amounts and all(x["amount"] is not None and x["currency"] for x in amounts):
        currencies = {x["currency"] for x in amounts}
        if len(currencies) == 1:
            computed_currency = next(iter(currencies))
            computed_sum = rounded(sum_decimals([x["amount"] for x in amounts]), computed_currency)
        else:
            issue("subtotal_all_items", "MIXED_LINE_ITEM_CURRENCIES")
    printed_sum = money("subtotal_all_items", raw["subtotal_all_items"])
    if computed_currency and printed_sum["currency"] != computed_currency:
        issue("subtotal_all_items", "SUBTOTAL_CURRENCY_MISMATCH")
    sum_difference = compare("subtotal_all_items", printed_sum["amount"], computed_sum if printed_sum["currency"] == computed_currency else None)
    normalized["subtotal_all_items"] = {"currency": computed_currency, "amount": computed_sum}

    claim = raw["claim_note"]
    claim_amount, claim_currency, claim_expected, claim_base = None, None, None, None
    if claim["present"] is not True and not any(claim[x] for x in ["note_raw", "amount_raw", "percentage_raw", "claim_number_raw", "base_amount_raw"]):
        if claim["present"] is None:
            issue("claim_note", "CLAIM_PRESENCE_UNCERTAIN_OR_CONFLICTING", "REVIEW")
        elif policy["claim_required"]:
            issue("claim_note", "CLAIM_REQUIRED")
        else:
            fields["claim_note"]["status"] = "NOT_APPLICABLE"
    else:
        if claim["present"] is not True:
            issue("claim_note", "CLAIM_PRESENCE_UNCERTAIN_OR_CONFLICTING", "REVIEW")
        if not claim["note_raw"]:
            issue("claim_note", "CLAIM_NOTE_REQUIRED")
        if clean(claim["claim_number_raw"]) != policy["expected_claim_number"]:
            issue("claim_note", "UNEXPECTED_CLAIM_NUMBER")
        percentage = number("claim_note", claim["percentage_raw"], "claim_note.percentage")
        if percentage is not None and percentage > 100:
            issue("claim_note", "CLAIM_PERCENTAGE_EXCEEDS_100")
        if percentage is not None and percentage != Decimal(policy["expected_claim_percentage"]):
            issue("claim_note", "UNEXPECTED_CLAIM_PERCENTAGE")
        parsed_claim = money("claim_note", claim, "claim_note.amount")
        claim_amount, claim_currency = parsed_claim["amount"], parsed_claim["currency"]
        base_currency = None
        if claim["base_kind"] == "all_items" and claim["basis_evidence"]:
            claim_base, base_currency = computed_sum, computed_currency
        elif claim["base_kind"] == "explicit_base" and claim["basis_evidence"]:
            base = money("claim_note", {"amount_raw": claim["base_amount_raw"], "currency_raw": claim["base_currency_raw"]}, "claim_note.base")
            claim_base, base_currency = base["amount"], base["currency"]
        else:
            issue("claim_note", "CLAIM_ELIGIBLE_BASE_UNRESOLVED", "REVIEW")
        if base_currency and claim_currency and base_currency != claim_currency:
            issue("claim_note", "CLAIM_BASE_CURRENCY_MISMATCH")
        if claim_base is not None and percentage is not None and claim_currency and base_currency == claim_currency:
            with localcontext() as ctx:
                ctx.prec = max(50, len(claim_base.as_tuple().digits) + len(percentage.as_tuple().digits) + 10)
                claim_expected = rounded(claim_base * percentage / Decimal(100), claim_currency)
            compare("claim_note", claim_amount, claim_expected, "claim_note.amount")
        else:
            issue("claim_note", "CLAIM_PERCENTAGE_CHECK_UNAVAILABLE", "REVIEW")
        normalized["claim_note"] = {"present": claim["present"], "note": clean(claim["note_raw"]), "claim_number": clean(claim["claim_number_raw"]),
                                    "percentage": percentage, "currency": claim_currency, "amount": claim_amount,
                                    "expected_amount": claim_expected, "eligible_base": claim_base}

    final = raw["final_total_amount"]
    printed_final = money("final_total_amount", final)
    final_base = computed_sum if final["calculation_basis"] == "full_invoice" else claim_expected if final["calculation_basis"] == "claim_only" else None
    base_currency = computed_currency if final["calculation_basis"] == "full_invoice" else claim_currency
    if final["calculation_basis"] not in {"full_invoice", "claim_only"}:
        issue("final_total_amount", "FINAL_TOTAL_BASIS_UNCERTAIN", "REVIEW")
    adjustments = []
    adjustments_valid = final["adjustments_complete"] is True and final["adjustments"] is not None
    if not adjustments_valid:
        issue("final_total_amount", "FINAL_TOTAL_ADJUSTMENTS_INCOMPLETE_OR_UNCERTAIN", "REVIEW")
    for index, adjustment in enumerate(final["adjustments"] or [], 1):
        deduction = adjustment["kind"] in {"discount", "other_deduction"}
        addition = adjustment["kind"] in {"tax", "fee", "shipping", "other_addition"}
        value = money("final_total_amount", adjustment, f"final_total_amount.adjustments[{index}]", allow_zero=True, absolute=deduction)
        if not deduction and not addition:
            issue("final_total_amount", "ADJUSTMENT_SIGN_UNCERTAIN", "REVIEW", adjustment=index)
            adjustments_valid = False
        if adjustment["included_in_base"] is None:
            issue("final_total_amount", "ADJUSTMENT_INCLUSION_UNCERTAIN", "REVIEW", adjustment=index)
            adjustments_valid = False
        if value["amount"] is None or not value["currency"]:
            issue("final_total_amount", "ADJUSTMENT_CHECK_UNAVAILABLE", "REVIEW", adjustment=index)
            adjustments_valid = False
        elif not base_currency:
            issue("final_total_amount", "ADJUSTMENT_CURRENCY_BASIS_UNAVAILABLE", "REVIEW", adjustment=index)
            adjustments_valid = False
        elif value["currency"] != base_currency:
            issue("final_total_amount", "ADJUSTMENT_CURRENCY_MISMATCH", adjustment=index)
            adjustments_valid = False
        adjustments.append({"label": clean(adjustment["label"]), "kind": adjustment["kind"],
                            "included_in_base": adjustment["included_in_base"], **value})
    calculated_final = None
    if final_base is not None and base_currency and adjustments_valid:
        signed = [x["amount"].copy_negate() if x["kind"] in {"discount", "other_deduction"} else x["amount"]
                  for x in adjustments if x["included_in_base"] is not True]
        calculated_final = rounded(sum_decimals([final_base, *signed]), base_currency)
        if calculated_final <= 0:
            issue("final_total_amount", "COMPUTED_FINAL_TOTAL_MUST_BE_POSITIVE")
    if base_currency and printed_final["currency"] != base_currency:
        issue("final_total_amount", "FINAL_TOTAL_CURRENCY_MISMATCH")
    final_difference = compare("final_total_amount", printed_final["amount"], calculated_final if printed_final["currency"] == base_currency else None)
    normalized["final_total_amount"] = {"currency": base_currency, "amount": calculated_final,
                                        "calculation_basis": final["calculation_basis"], "adjustments": adjustments}

    root_meta = ((metadata or {}).get("field_metadata") or {}).get("document_metadata") or {}
    for key, field in fields.items():
        field["normalized_value"] = normalized[key]
        field["metadata"] = root_meta.get(key, {})
        scores = confidence_values(field["metadata"])
        field["confidence"] = min(scores) if scores else None
        if field["status"] not in {"NOT_PRESENT", "NOT_APPLICABLE"}:
            if scores and min(scores) < policy["minimum_confidence"]:
                issue(key, "LOW_EXTRACTION_CONFIDENCE", "REVIEW")
            elif not scores and policy["require_confidence"]:
                issue(key, "CONFIDENCE_UNAVAILABLE", "REVIEW")
    status = "FAIL" if any(x["status"] == "FAIL" for x in fields.values()) else "REVIEW" if any(x["status"] == "REVIEW" for x in fields.values()) else "PASS"
    return {"document_type": "invoice", "document_name": "Underlying Invoice", "status": status,
            "raw": raw, "normalized": normalized, "fields": fields, "corrections": corrections,
            "correction_suggestions": suggestions, "checkbox_resolutions": {}, "line_items": line_checks,
            "calculations": {"subtotal_all_items": {"computed": computed_sum, "printed": printed_sum["amount"], "difference": sum_difference},
                             "claim": {"eligible_base": claim_base, "computed": claim_expected, "printed": claim_amount},
                             "final_total": {"computed": calculated_final, "printed": printed_final["amount"], "difference": final_difference}},
            "numeric_candidates": numeric_candidates, "as_of": reference.isoformat(), "policy": policy, "validation_context": context}
