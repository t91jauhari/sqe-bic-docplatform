"""Independent reference comparisons; never modify extraction or SOP decisions."""
from .configuration.repository import get_revision


import hashlib
import json
import re
import unicodedata
from collections import Counter
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path

def __getattr__(name):
    # Compatibility imports remain lazy. Registry mode never needs these files.
    if name in {"DATASET", "ACCOUNT_DATASET"}:
        from .configuration.dataset_sources import bundled_datasets
        return bundled_datasets()["forex-sample-v1" if name == "DATASET" else "account-opening-sample-v1"]
    raise AttributeError(name)


def dataset_for_case(db, case, *, payload=None):
    from .configuration.dataset_sources import resolve_dataset
    cfg_payload = (
        payload
        if payload is not None
        else get_revision(db, case.config_id, copy_payload=False).payload
    )
    flow = cfg_payload["templates"][case.template]
    return resolve_dataset(db, case.org, flow.get("dataset_id", "forex-sample-v1"))


MISSING = object()


def fuzzy_text(expected, actual, kind, field, policy=None):
    from .configuration.dataset_policy import comparison_policy
    policy = policy or comparison_policy()
    if not policy.enabled or field in policy.excluded_fields or (field or "").endswith(tuple(policy.excluded_suffixes)):
        return None
    if kind != "text" or not isinstance(expected, str) or not isinstance(actual, str):
        return None
    a, b = key(expected), key(actual)
    if not a or not b or a.startswith(("{", "[")) or b.startswith(("{", "[")):
        return None
    if re.findall(r"\d+", a) != re.findall(r"\d+", b):
        return None
    tokens_a, tokens_b = re.findall(r"\w+", a), re.findall(r"\w+", b)
    if tokens_a == tokens_b:
        return {
            "status": "FUZZY_MATCH",
            "similarity": 100.0,
            "method": "punctuation_only",
            "message": "Same complete tokens and numbers; punctuation differs.",
        }
    if (
        len(tokens_a) != len(tokens_b)
        or min(len(a), len(b)) < policy.minimum_length
        or max(len(a), len(b)) > policy.maximum_length
    ):
        return None
    limit = policy.long_edit_limit if min(len(a), len(b)) >= policy.long_text_length else policy.short_edit_limit
    if abs(len(a) - len(b)) > limit:
        return None
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [limit + 1] * (len(b) + 1)
        current[0] = i
        for j in range(max(1, i - limit), min(len(b), i + limit) + 1):
            current[j] = min(
                current[j - 1] + 1,
                previous[j] + 1,
                previous[j - 1] + (left != b[j - 1]),
            )
        if min(current) > limit:
            return None
        previous = current
    distance = previous[-1]
    score = SequenceMatcher(None, a, b, autojunk=False).ratio()
    if score < policy.minimum_similarity or distance > limit:
        return None
    accepted = field in policy.descriptive_fields and score >= policy.acceptance_similarity and min(len(a), len(b)) >= policy.acceptance_minimum_length
    return {
        "status": "FUZZY_MATCH" if accepted else "REVIEW",
        "similarity": round(score * 100, 2),
        "method": "bounded_character_similarity",
        "message": "Minor text difference accepted by conservative fuzzy policy."
        if accepted
        else "Near text match; confirm the reference or effective value before accepting.",
    }


def summarize(rows):
    counts = dict(Counter(r["status"] for r in rows))
    accepted = counts.get("MATCH", 0) + counts.get("FUZZY_MATCH", 0)
    compared = accepted + counts.get("MISMATCH", 0) + counts.get("VALUE_MISSING", 0)
    applicable = len(rows) - counts.get("NOT_APPLICABLE", 0)
    complete = not any(
        counts.get(k, 0) for k in ("REVIEW", "UNMAPPED", "DOCUMENT_MISSING", "PENDING")
    )
    result = (
        "MISMATCH"
        if counts.get("MISMATCH", 0) or counts.get("VALUE_MISSING", 0)
        else "REVIEW"
        if not complete
        else "MATCH"
        if compared
        else "NOT_APPLICABLE"
    )
    return {
        "counts": counts,
        "compared_fields": compared,
        "applicable_fields": applicable,
        "match_rate": round(100 * accepted / compared, 2) if compared else None,
        "exact_match_rate": round(100 * counts.get("MATCH", 0) / compared, 2)
        if compared
        else None,
        "coverage_rate": round(100 * compared / applicable, 2) if applicable else None,
        "complete": complete,
        "result": result,
    }


def key(value):
    return " ".join(unicodedata.normalize("NFC", str(value)).split()).casefold()


def blank(value):
    return value is None or isinstance(value, str) and key(value) in {"", "[blank]"}


def number(value):
    """Explicit decimals only; ambiguous separators/symbols require review."""
    if isinstance(value, bool):
        raise ValueError("A boolean is not a number.")
    if isinstance(value, (int, float, Decimal)):
        return None, str(Decimal(str(value)).normalize())
    text = str(value).strip()
    currency = None
    match = re.fullmatch(
        r"(?:(USD|EUR|IDR|CNY|MYR|SGD|GBP|JPY|AUD|HKD|Rp\.?)\s*)?(-?\d[\d., ]*)",
        text,
        re.I,
    )
    if not match:
        raise ValueError(
            "Amount needs an explicit code and numeric value; symbols, units and prose need review."
        )
    currency, text = match.groups()
    currency = (
        "IDR"
        if currency and currency.lower().startswith("rp")
        else currency.upper()
        if currency
        else None
    )
    text = text.replace(" ", "")
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        if not re.fullmatch(
            r"-?\d{1,3}(?:"
            + re.escape(thousands)
            + r"\d{3})*"
            + re.escape(decimal)
            + r"\d+",
            text,
        ):
            raise ValueError("Invalid grouped amount.")
        text = text.replace(thousands, "").replace(decimal, ".")
    elif "," in text or "." in text:
        sep = "," if "," in text else "."
        if text.count(sep) > 1:
            if not re.fullmatch(r"-?\d{1,3}(?:" + re.escape(sep) + r"\d{3})+", text):
                raise ValueError("Invalid numeric separators.")
            text = text.replace(sep, "")
        elif len(text.rsplit(sep, 1)[1]) == 3:
            raise ValueError(
                "Ambiguous thousands/decimal separator. Edit using an ungrouped number."
            )
        else:
            text = text.replace(sep, ".")
    try:
        result = Decimal(text)
        if not result.is_finite():
            raise ValueError("Non-finite number.")
        return currency, str(result.normalize())
    except InvalidOperation as exc:
        raise ValueError("Invalid numeric value.") from exc


def canonical(value, kind, field=None):
    if blank(value):
        return False if kind in {"presence", "initials"} else None
    if (
        isinstance(value, str)
        and value.strip().startswith(("{", "["))
        and key(value) != "[blank]"
    ):
        try:
            value = json.loads(value)
        except ValueError:
            pass
    if isinstance(value, (dict, list)):
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    if isinstance(value, str) and key(value) in {"n/a", "not applicable"}:
        raise ValueError(
            "N/A is an applicability annotation; confirm the intended reference value."
        )
    if kind in {"presence", "initials"}:
        if isinstance(value, bool):
            return value
        if key(value) == "available":
            return True
        if key(value) == "not available":
            return False
        raise ValueError("Use Available, Not Available, true or false for presence.")
    if kind == "date":
        if key(value) == "seumur hidup":
            return "SEUMUR HIDUP"
        import calendar
        from .value_display import MONTHS
        month_only = re.fullmatch(r"([A-Za-z]+)[\s/-]+([0-9]{4})", str(value).strip())
        if month_only and int(month_only[2]) > 0:
            names = {key(name): n for n, name in enumerate(MONTHS, 1)}
            names.update({key(name): n for n, name in enumerate(calendar.month_name) if name})
            names.update({key(name): n for n, name in enumerate(calendar.month_abbr) if name})
            if key(month_only[1]) in names:
                return "month", f"{int(month_only[2]):04}-{names[key(month_only[1])]:02}"
        from validation import parse_date

        try:
            return parse_date(str(value)).isoformat()
        except (ValueError, OverflowError) as exc:
            raise ValueError("Invalid or incomplete date.") from exc
    if field == "issuance" and isinstance(value, str) and "," in value:
        place, date = value.rsplit(",", 1)
        return key(place), canonical(date.strip(), "date")
    if kind == "identifier":
        # Compare formatting separators only; preserve every digit/letter and leading zero.
        result = re.sub(r'[\s-]+','',str(value).strip())
        if field in {"rt", "rw"} and result.isdigit() and len(result) <= 3:
            result = result.zfill(3)
        return result.upper() if field == "swift_code" else result
    if kind == "number":
        return number(value)
    return key(value)


def effective_canonical(doc, field, value, kind):
    if kind != "number" or blank(value) or isinstance(value, (list, dict)):
        return canonical(value, kind, field)
    original = doc.normalized.get(field)
    if isinstance(original,dict) and ('raw' in original or 'amount_raw' in original):
        return canonical(value,kind,field)
    currency = None
    if isinstance(original, dict):
        currency = original.get("currency")
        original = original.get("amount")
    try:
        amount = Decimal(str(original))
        if not amount.is_finite():
            raise ValueError("Non-finite normalized value.")
        return currency, str(amount.normalize())
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Effective normalized numeric value is invalid.") from exc


def project(doc, field, kind, *, policy=None):
    """Only the effective normalized result, including already validated overrides."""
    value = doc.normalized.get(field, MISSING)
    if value is MISSING:
        return MISSING
    if kind == "presence":
        return (
            value.get("stamp_present" if field == "bank_approval" else "present")
            if isinstance(value, dict)
            else value
        )
    if kind == "initials":
        from page_policy import initial_page_records
        pages = value.get("pages", []) if isinstance(value, dict) else []
        count=value.get('page_count',3) if isinstance(value,dict) else 3
        if policy and policy.exclude_final_page:
            count = value.get('page_count') if isinstance(value, dict) else None
        if not isinstance(count,int) or isinstance(count,bool) or not 1<=count<=200:return None
        try:
            required = initial_page_records(count, pages, exclude_final_page=bool(policy and policy.exclude_final_page))
        except ValueError:
            return None
        marks = [p.get("footer_present") for p in required]
        return (
            False if False in marks else True if all(v is True for v in marks) else None
        )
    if field == "charges" and isinstance(value, dict):
        return value.get("amount")
    if kind == "number" and isinstance(value, dict) and "amount" in value:
        amount = value["amount"]
        return (
            f"{value['currency']} {amount}"
            if value.get("currency") and amount is not None
            else amount
        )
    if field == "issuance" and isinstance(value, dict):
        place = value.get("place", value.get("place_raw"))
        date = value.get("date", value.get("date_raw"))
        if place or date:
            return ", ".join(str(part) for part in (place, date) if part)
    if isinstance(value,dict) and ('raw' in value or 'amount_raw' in value or 'formatted_date' in value):
        from .value_display import display_value
        projected=display_value(value)
        return None if projected=='Missing' else projected
    if isinstance(value,dict) and 'selected' in value:
        selected=value['selected']
        return selected[0] if isinstance(selected,list) and len(selected)==1 else None if selected==[] else selected
    # Composite party/bank fields remain structured. Reviewers may use JSON references.
    return value


def compare(case, docs, state, dataset=None, *, policy=None):
    from .configuration.dataset_policy import comparison_policy
    policy = policy or comparison_policy()
    DATASET = dataset if dataset is not None else __getattr__("DATASET")
    sample = state.get("sample_id")
    if sample not in {s["id"] for s in DATASET["samples"]}:
        return {
            "revision": state.get("revision", 0),
            "sample_id": None,
            "rows": [],
            "summary": {},
            "result": "NOT_CONFIGURED",
            "documents": [
                {
                    "id": d.id,
                    "filename": d.filename,
                    "doc_type": d.doc_type,
                    "status": d.status,
                }
                for d in docs
            ],
        }
    rows = []
    for source in DATASET["rows"]:
        row = {
            k: v for k, v in source.items() if k not in {"values", "document_available"}
        }
        row["original_value"] = source["values"][sample]
        edit = state.get("edits", {}).get(source["id"], {})
        expected = edit.get("value", row["original_value"])
        row.update(
            dataset_value=expected,
            edited=bool(edit),
            edit=edit or None,
            effective_value=None,
            status="REVIEW",
            message="",
            source="effective_normalized",
        )
        options = [d for d in docs if d.doc_type == source["document_type"]]
        selected = state.get("documents", {}).get(str(source["section"]))
        doc = (
            next((d for d in options if d.id == selected), None)
            if selected
            else options[0]
            if len(options) == 1
            else None
        )
        row["document_id"] = doc.id if doc else None
        row["filename"] = doc.filename if doc else None
        field = source["field"]
        if not source["document_available"][sample]:
            row.update(
                status="NOT_APPLICABLE",
                message="Dataset marks this document section unavailable; no field comparison.",
            )
        elif not field:
            row.update(
                status="UNMAPPED",
                message="No equivalent field in the current extraction schema.",
            )
        elif not doc:
            row.update(
                status="REVIEW" if options else "DOCUMENT_MISSING",
                message="Select one source document for this section."
                if options
                else "Expected document is missing from the case.",
            )
        elif doc.status != "COMPLETED":
            row.update(
                status="PENDING", message="Extraction/revalidation has not completed."
            )
        else:
            observed = doc.normalized.get(field)
            if (source["kind"] == "initials" and policy.exclude_final_page
                    and isinstance(observed, dict) and observed.get("page_count") == 1):
                row.update(status="NOT_APPLICABLE", message="The only page is the exempt final page; no paraf check is required.")
                rows.append(row)
                continue
            value = project(doc, field, source["kind"], policy=policy)
            row["effective_value"] = None if value is MISSING else value
            row["effective_original_value"] = doc.normalized.get(field)
            row["effective_edit_value"] = (
                (None if value is MISSING else value)
                if source["kind"] == "presence"
                else doc.normalized.get(field)
            )
            row["extraction_id"] = doc.provider_state.get("extract_job_id")
            if value is MISSING:
                row.update(
                    status="UNMAPPED",
                    message="Field is absent from this document's normalized result.",
                )
            elif source["kind"] in {"presence", "initials"} and (
                value is None
                or doc.validation.get("fields", {}).get(field, {}).get("status")
                == "REVIEW"
            ):
                row.update(
                    status="REVIEW",
                    message="Visual presence observation still requires review; this is not an image identity comparison.",
                )
            else:
                try:
                    a = canonical(expected, source["kind"], field)
                    b = effective_canonical(doc, field, value, source["kind"])
                    row.update(expected_normalized=a, actual_normalized=b)
                    if b is None and a is not None:
                        row.update(
                            status="VALUE_MISSING",
                            message="Effective extraction value is missing or uncertain.",
                        )
                    elif a == b:
                        row.update(
                            status="MATCH",
                            message="Values match under the stated comparison policy.",
                        )
                    elif source["kind"] == "date" and any(isinstance(v, tuple) and v[0] == "month" for v in (a, b)):
                        row.update(status="REVIEW", message="Month-only and full-date values have different precision; no day is assumed.")
                    elif (
                        isinstance(value, (dict, list))
                        and not isinstance(expected, (dict, list))
                        and not str(expected).strip().startswith(("{", "["))
                    ):
                        row.update(
                            status="REVIEW",
                            message="Structured effective value requires an explicit JSON reference; no flattened or partial match is assumed.",
                        )
                    elif (
                        source["kind"] == "number"
                        and isinstance(a, tuple)
                        and isinstance(b, tuple)
                        and a[0]
                        and not b[0]
                    ):
                        currency = doc.normalized.get("currency")
                        if currency and str(currency).upper() == a[0]:
                            row.update(
                                status="MATCH" if a[1] == b[1] else "MISMATCH",
                                message="Amount and normalized document currency compared.",
                            )
                        else:
                            row.update(
                                status="REVIEW",
                                message="Expected currency cannot be verified from the effective value.",
                            )
                    elif (
                        source["kind"] == "number"
                        and isinstance(a, tuple)
                        and isinstance(b, tuple)
                        and not a[0]
                        and b[0]
                    ):
                        row.update(
                            status="MATCH" if a[1] == b[1] else "MISMATCH",
                            message="Numeric value compared; reference currency is unspecified.",
                        )
                    else:
                        fuzzy = fuzzy_text(expected, value, source["kind"], field, policy)
                        row.update(
                            fuzzy
                            or {
                                "status": "MISMATCH",
                                "message": "Effective value differs from the dataset reference.",
                            }
                        )
                except ValueError as exc:
                    row.update(status="REVIEW", message=str(exc))
        rows.append(row)
    summary = summarize(rows)
    result = summary["result"]
    groups = {}
    for row in rows:
        group_id = f"{row['section']}:{row.get('document_id') or 'unselected'}"
        groups.setdefault(group_id, []).append(row)
    document_groups = [
        {
            "id": group_id,
            "section": group[0]["section"],
            "document_type": group[0]["document_type"],
            "document_label": group[0]["document_label"],
            "document_id": group[0].get("document_id"),
            "filename": group[0].get("filename"),
            **summarize(group),
        }
        for group_id, group in groups.items()
    ]
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "dataset_sha256": DATASET["sha256"],
                "comparison_policy": policy.model_dump(mode="json"),
                "sample": sample,
                "state": state,
                "rows": rows,
                "documents": [
                    {"id": d.id, "status": d.status, "normalized": d.normalized}
                    for d in docs
                ],
            },
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()
    return {
        "case_id": case.id,
        "comparison_policy": policy.model_dump(mode="json"),
        "customer": case.customer,
        "dataset_id": DATASET["id"],
        "dataset_sha256": DATASET["sha256"],
        "sample_id": sample,
        "sample_name": next(s["name"] for s in DATASET["samples"] if s["id"] == sample),
        "revision": state.get("revision", 0),
        "fingerprint": fingerprint,
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "doc_type": d.doc_type,
                "status": d.status,
            }
            for d in docs
        ],
        "document_selection": state.get("documents", {}),
        "rows": rows,
        "summary": summary,
        "document_groups": document_groups,
        "result": result,
        "policy": "Effective normalized values only. Text: exact case/whitespace normalization, punctuation-only fuzzy matches and bounded descriptive text similarity (96% minimum); near names/addresses require review; identifiers: exact; dates: calendar date; numbers: exact decimals, ambiguous separators require review. Visual fields compare presence, not image/signature identity. Unmapped and pending fields excluded from match rate; completeness reported separately.",
    }
