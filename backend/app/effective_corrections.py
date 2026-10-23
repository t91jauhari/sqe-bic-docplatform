"""Translate reviewer edits to validated extraction overrides, never bypass normalization."""
import copy
from decimal import Decimal, InvalidOperation

NUMERIC = {"exchange_rate", "amount", "total_amount", "charges", "transaction_value", "usage_amount", "receipt_amount", "subtotal_all_items", "final_total_amount"}


def numeric_text(value, locale):
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError("Use a finite decimal value.")
        text = format(number, "f")
        return text.replace(".", ",") if locale == "id_ID" else text
    except InvalidOperation as exc:
        raise ValueError("Use an ungrouped decimal number, e.g. 1234.50.") from exc


def extraction_value(field, value, original, policy):
    locale = policy.get("field_number_locales", {}).get(field, policy.get("number_locale", "id_ID"))
    base = copy.deepcopy(original)
    if isinstance(base, dict):
        if isinstance(value, bool) and ("present" in base or "stamp_present" in base):
            base["stamp_present" if field == "bank_approval" else "present"] = value
            return base
        if "raw" in base and not isinstance(value, (dict, list)):
            base["raw"] = numeric_text(value, locale) if field in NUMERIC and value is not None else value
            return base
        if "selected" in base and isinstance(value, (str, list)):
            base["selected"] = [value] if isinstance(value, str) else value
            # Conflicting local checkbox observations remain visible to validation.
            return base
        if not isinstance(value, dict):
            raise ValueError("This field needs a structured value. Edit its object values or use the case's source-field editor.")
        aliases = {"place": "place_raw", "date": "date_raw"} if field == "issuance" else {"name": "name_raw", "position": "role_raw"} if field == "signatory" else {"payment_method": "selected"} if field == "charges" else {}
        for name, item in value.items():
            target = aliases.get(name, name)
            if name == "amount" and "raw" in base:
                base["raw"] = numeric_text(item, locale) if item is not None else None
            elif target in base:
                base[target] = [item] if target == "selected" and isinstance(item, str) else item
            elif name not in {"comparison_status", "signature_match", "reference_id", "verified_by"}:
                raise ValueError(f"'{name}' is computed metadata; edit the underlying source fields instead.")
        return base
    if isinstance(base, list):
        raise ValueError("Item tables are recomputed from source rows. Use the case source-field editor to correct the table.")
    if field in NUMERIC and value is not None:
        return numeric_text(value, locale)
    return value
