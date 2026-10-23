"""Readable presentation only; effective values and machine exports remain structured."""

import re

MONTHS = [
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
]
HIDDEN = {
    "evidence",
    "citation",
    "confidence",
    "extraction_confidence",
    "bounding_boxes",
    "page_dimensions",
}


def date_text(value):
    if not isinstance(value, str):
        return display_value(value)
    match = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", value)
    if match and 1 <= int(match[2]) <= 12:
        return f"{int(match[1])} {MONTHS[int(match[2]) - 1]} {match[3]}"
    return value


def display_value(value):
    if value is None or value == "":
        return "Missing"
    if isinstance(value, bool):
        return "Present" if value else "Absent"
    if isinstance(value, list):
        return "; ".join(display_value(v) for v in value) if value else "None selected"
    if not isinstance(value, dict):
        return str(value)
    if "selected" in value:
        parts=[]
        if value.get('selected'):parts.append(display_value(value['selected']))
        if value.get('other_description'):parts.append(display_value(value['other_description']))
        if value.get('raw') not in (None,''):
            raw=display_value(value['raw'])
            currency=str(value.get('currency') or '')
            parts.append((currency+' '+raw).strip() if currency and currency.casefold() not in raw.casefold() else raw)
        return ' · '.join(parts) if parts else display_value(value['selected'])
    if "currency_raw" in value and "amount_raw" in value:
        amount = (
            " ".join(
                display_value(value[k])
                for k in ("currency_raw", "amount_raw")
                if value[k] is not None and value[k] != ""
            )
            or "Missing"
        )
        return amount+'/'+str(value['unit_raw']) if amount!='Missing' and value.get('unit_raw') else amount
    if "formatted_date" in value:
        return display_value(value["formatted_date"])
    if 'table_complete' in value and isinstance(value.get('items'),list):
        items='; '.join(display_value(item) for item in value['items']) or 'Missing'
        return ('Incomplete table · ' if value['table_complete'] is False else '')+items
    if any(k in value for k in ("name", "address", "phone")):
        parts = [
            value.get(k)
            for k in ("name", "branch", "address", "phone")
            if value.get(k) is not None and value.get(k) != ""
        ]
        if parts:
            return " · ".join(display_value(part) for part in parts)
        if "full_text" in value:
            return display_value(value["full_text"])
    if "full_text" in value:
        return display_value(value["full_text"])
    if "page_count" in value and isinstance(value.get("pages"), list):
        return (
            " · ".join(
                f"Page {item.get('page_number', '?')}: {display_value(item.get('footer_present'))}"
                for item in value["pages"]
                if isinstance(item, dict)
            )
            or "Missing"
        )
    if "place" in value and "date" in value:
        return f"{display_value(value['place'])} — {date_text(value['date'])}"
    presence = (
        "present"
        if "present" in value
        else "stamp_present"
        if "stamp_present" in value
        else None
    )
    if presence:
        parts = [
            "Needs review"
            if value[presence] is None
            else display_value(value[presence])
        ]
        if "complete" in value:
            parts.append(
                "Complete"
                if value["complete"] is True
                else "Incomplete"
                if value["complete"] is False
                else "Completeness needs review"
            )
        if value.get("text"):
            parts.append(str(value["text"]))
        for key in ("comparison_status", "signature_match"):
            if value.get(key) is not None:
                parts.append(
                    f"{key.replace('_', ' ').capitalize()}: {display_value(value[key])}"
                )
        return " · ".join(parts)
    if "raw" in value:
        if value.get("currency") not in (None, "") and value["raw"] not in (None, ""):
            return f"{display_value(value['currency'])} {display_value(value['raw'])}"
        return display_value(value["raw"])
    return (
        " · ".join(
            f"{key.replace('_', ' ').capitalize()}: {display_value(v)}"
            for key, v in value.items()
            if key not in HIDDEN
        )
        or "Missing"
    )


def display_effective(value, field_result=None):
    codes = {i.get("code") for i in (field_result or {}).get("issues", [])}
    if value is None and codes & {"UNRECOGNIZED_ENUM", "INVALID_OR_MISSING_ENUM"}:
        return "Unrecognized value · needs review"
    return display_value(value)
