"""Account Opening controls based on uploaded documents; external verification excluded."""

import json
import re
from pathlib import Path
from .sop import value_at, normalize

CATEGORIES = (
    "DATA_COMPLETION",
    "CUSTOMER_SIGNATURE",
    "OFFICER_REVIEW_APPROVAL",
    "DOCUMENT_COMPLETION",
    "DOCUMENT_VERIFICATION",
    "OBSERVATIONS",
)


def _name_abbreviation(left, right):
    """Ordered initials or explicit dotted prefixes only nominate picture review."""
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    a, b = normalize(left).split(), normalize(right).split()
    if len(a) != len(b) or not a:
        return False
    abbreviated = False
    for x, y in zip(a, b):
        if x == y:
            continue
        elif (
            re.fullmatch(r"[^\W\d_]\.?", x, re.UNICODE) and len(y) > 1 and x[0] == y[0]
        ) or (
            re.fullmatch(r"[^\W\d_]\.?", y, re.UNICODE) and len(x) > 1 and y[0] == x[0]
        ):
            abbreviated = True
        elif (
            x.endswith(".")
            and len(x) > 2
            and y.startswith(x[:-1])
            and len(y) > len(x[:-1])
        ) or (
            y.endswith(".")
            and len(y) > 2
            and x.startswith(y[:-1])
            and len(x) > len(y[:-1])
        ):
            abbreviated = True
        else:
            return False
    return abbreviated


def _birth_parts(value):
    """Parse an explicit full trailing date; never infer a missing component."""
    from validation import parse_date

    if not isinstance(value, str):
        raise ValueError("Combined birth place/date must be explicit text.")
    match = re.search(
        r"(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|"
        r"\d{1,2}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{4}|"
        r"\d{1,2}[\s-]+[A-Za-z]+[\s,-]+\d{4})\s*$",
        value,
    )
    if not match:
        raise ValueError("Complete birth date is missing.")
    place = value[: match.start()].strip(" ,/;-")
    if not place:
        raise ValueError("Birth place is missing.")
    return normalize(place), parse_date(match.group(1)).isoformat()


def sources():
    records = json.loads(
        (Path(__file__).parent / "config_data/account_opening_sources.json").read_text(
            encoding="utf-8"
        )
    )
    return [
        {
            "source_ref": r["source_ref"],
            "scope_basis": (
                "ACCOUNT_DOCUMENT_SYSTEM"
                if r["sheet"] == "SOP System"
                else "YES_SELECTED"
            ),
            "instruction": r["values"][1],
            "guidance": r["values"][2] if len(r["values"]) > 2 else "",
            "original_flag": "Yes" if r["included"] else "No",
        }
        for r in records
        if r["included"] and r["source_ref"] != "AO:SOP System:12"
    ]


def fields():
    from account_opening.profiles import REFERENCE

    return [
        {
            "document": name,
            "field": f["key"],
            "path": name + "." + f["key"],
            "label": f["label"],
            "type": (
                "signature_region"
                if f["type"] == "visual" and "signature" in f["key"]
                else (
                    "stamp_region"
                    if f["type"] == "visual"
                    else (
                        "identifier"
                        if f["type"] == "identifier"
                        else "date" if f["type"] == "date" else "text"
                    )
                )
            ),
        }
        for name, p in REFERENCE["profiles"].items()
        for f in p["fields"]
    ]


def evaluate_rule(rule, documents, cfg, context):
    from .configuration.account_policies import parse_policy

    settings = parse_policy(rule["comparison_policy"])
    kind = settings["kind"]
    actual, left = value_at(documents, rule["path"])
    expected, right = value_at(documents, rule.get("other_path") or rule["path"])
    result = "REVIEW"
    message = rule["label"]
    visible = {d["doc_type"] for d in documents}
    signature_review_required = False
    component_checks = []
    templates = cfg.get("sop_message_templates", {})

    def tpl(key):
        """Look up a message template with graceful fallback to the hardcoded default."""
        from app.native_profiles import SOP_MESSAGE_TEMPLATES

        return templates.get(key, SOP_MESSAGE_TEMPLATES.get(key, ""))

    if kind == "document":
        result = (
            "PASS"
            if any(
                d["doc_type"] == rule["path"].split(".")[0]
                and d["status"] == "COMPLETED"
                for d in documents
            )
            else "FAIL"
        )
    elif settings.get("trigger"):
        from .configuration.account_policies import condition_result

        trigger = condition_result(documents, settings["trigger"])
        if trigger is False:
            result = "NOT_APPLICABLE"
        elif trigger is True:
            result = (
                "PASS"
                if any(
                    document["doc_type"] == settings["target"]
                    and document["status"] == "COMPLETED"
                    for document in documents
                )
                else "FAIL"
            )
        else:
            message += " " + tpl("ao.conditional_unresolved")
    elif kind in {
        "conditional_edd",
        "conditional_bo",
        "conditional_visit",
        "conditional_signature",
        "conditional_survey",
    }:
        form, refs = value_at(documents, "account_opening_form.customer_name")
        if len(refs) != 1:
            message += " " + tpl("ao.opening_form_missing")
        else:
            values = refs[0]["normalized"]
            trigger = None
            target = settings.get("target")
            if kind == "conditional_edd":
                risk = values.get("risk_category")
                trigger = (
                    True
                    if normalize(risk) == "risiko tinggi"
                    else (
                        False
                        if normalize(risk) in {"risiko rendah", "risiko sedang"}
                        else None
                    )
                )
            elif kind == "conditional_bo":
                acting = values.get("acting_for")
                trigger = (
                    True
                    if normalize(acting) == "beneficial owner"
                    else False if normalize(acting) == "diri sendiri" else None
                )
            elif kind == "conditional_visit":
                referral = values.get("referral_source")
                trigger = (
                    True
                    if normalize(referral) == "marketing"
                    else (
                        False
                        if normalize(referral) in {"walk in customer", "lainnya"}
                        else None
                    )
                )
            elif kind == "conditional_signature":
                # A declared difference or audited visual comparison may establish applicability; presence alone never does.
                observation = context.get("account_signature_difference", "UNKNOWN")
                trigger = (
                    True
                    if observation == "YES"
                    else False if observation == "NO" else None
                )
                if "signature_difference" in visible:
                    trigger = True
            else:
                # Workbook specifies WIC plus additional criteria; those criteria are not fully defined.
                message += " " + tpl("ao.wic_survey_applicability")
            control = {
                "conditional_edd": "risk_category",
                "conditional_bo": "acting_for",
                "conditional_visit": "referral_source",
            }.get(kind)
            if control and any(
                i.get("severity") == "REVIEW"
                for i in refs[0]
                .get("validation", {})
                .get("fields", {})
                .get(control, {})
                .get("issues", [])
            ):
                trigger = None
            if trigger is False:
                result = "NOT_APPLICABLE"
            elif trigger is True:
                result = (
                    "PASS"
                    if any(
                        d["doc_type"] == target and d["status"] == "COMPLETED"
                        for d in documents
                    )
                    else "FAIL" if target in cfg["profiles"] else "REVIEW"
                )
            else:
                message += " " + tpl("ao.conditional_unresolved")
    elif kind == "nik_birth":
        nik, left = value_at(documents, "ektp.nik")
        birth, right = value_at(documents, "ektp.birth_date")
        gender, _ = value_at(documents, "ektp.gender")
        if (
            isinstance(nik, str)
            and re.fullmatch(r"[0-9]{16}", nik)
            and birth
            and normalize(gender) in {"laki-laki", "perempuan"}
        ):
            try:
                day, month, year = [int(v) for v in birth.split("-")]
                encoded = day + (40 if normalize(gender) == "perempuan" else 0)
                result = (
                    "PASS"
                    if nik[6:12] == f"{encoded:02}{month:02}{year % 100:02}"
                    else "FAIL"
                )
            except (ValueError, TypeError):
                pass
    elif kind == "identity_name":
        if (
            len(left) == len(right) == 1
            and isinstance(actual, str)
            and isinstance(expected, str)
            and actual.strip()
            and expected.strip()
        ):
            if normalize(actual) == normalize(expected):
                result = "PASS"
            elif _name_abbreviation(actual, expected):
                signature_review_required = True
                message += " Minor name abbreviation requires an audited visual comparison of the eKTP owner signature and opening-form customer signature. Name similarity or signature presence alone cannot pass this rule."
            else:
                result = "FAIL"
    elif kind == "gender":
        if len(left) == len(right) == 1 and actual and expected:
            mapped = {"laki-laki": "pria", "perempuan": "wanita"}.get(
                str(actual).casefold()
            )
            result = "PASS" if mapped and mapped == str(expected).casefold() else "FAIL"
    elif kind == "birth":
        place, places = value_at(documents, "ektp.birth_place")
        birth, dates = value_at(documents, "ektp.birth_date")
        if (
            len(places) == len(dates) == len(right) == 1
            and place
            and birth
            and expected
        ):
            from validation import parse_date

            try:
                form_place, form_date = _birth_parts(expected)
                result = (
                    "PASS"
                    if normalize(place) == form_place
                    and parse_date(birth).isoformat() == form_date
                    else "FAIL"
                )
            except (ValueError, TypeError, OverflowError):
                result = "FAIL"
                message += " Complete explicit birth place and date are required; a missing component is not inferred from NIK."
    elif kind == "field":
        if not left and settings.get("optional_document"):
            result = "NOT_APPLICABLE"
        elif len(left) != 1:
            message += " " + tpl("ao.source_missing_ambiguous")
        else:
            field = rule["path"].split(".")[1]
            report = left[0].get("validation", {}).get("fields", {}).get(field, {})
            result = report.get("status", "REVIEW")
            if result not in {"PASS", "FAIL", "REVIEW", "NOT_APPLICABLE"}:
                result = "REVIEW"
            if actual in (None, "") and result == "PASS":
                result = "FAIL"
            if (
                isinstance(actual, dict)
                and "present" in actual
                and actual["present"] is not True
            ):
                result = "REVIEW" if actual["present"] is None else "FAIL"
    elif kind == "match":
        if settings.get("optional_document") and any(
            t not in visible
            for t in [
                rule["path"].split(".")[0],
                rule.get("other_path", "").split(".")[0],
            ]
            if t not in {"ektp", "account_opening_form", "riplay"}
        ):
            result = "NOT_APPLICABLE"
        elif (
            len(left) == len(right) == 1
            and actual not in (None, "")
            and expected not in (None, "")
        ):
            strict = settings.get("identifier", False)
            result = (
                "PASS"
                if (
                    str(actual).strip() == str(expected).strip()
                    if strict
                    else normalize(actual) == normalize(expected)
                )
                else "FAIL"
            )
            pattern = settings.get("required_pattern")
            allowed = settings.get("allowed_values")
            if pattern and not all(
                isinstance(v, str) and re.fullmatch(pattern, v.strip())
                for v in (actual, expected)
            ):
                result = "FAIL"
                message += (
                    " Both document values must satisfy the required literal format."
                )
            if allowed and not all(
                isinstance(v, str) and normalize(v) in {normalize(a) for a in allowed}
                for v in (actual, expected)
            ):
                result = "FAIL"
                message += " Both document values must use an approved code."
            for pair in settings.get("companion_matches", []):
                first, first_docs = value_at(documents, pair["path"])
                second, second_docs = value_at(documents, pair["other_path"])
                matched = (
                    len(first_docs) == len(second_docs) == 1
                    and isinstance(first, str)
                    and isinstance(second, str)
                    and bool(first.strip())
                    and bool(second.strip())
                    and normalize(first) == normalize(second)
                )
                component_checks.append(
                    {
                        **pair,
                        "actual": first,
                        "expected": second,
                        "result": "PASS" if matched else "FAIL",
                    }
                )
                if not matched:
                    result = "FAIL"
                    message += " Customer job title must also match verbatim; employer signatory/officer titles cannot substitute."
    elif kind == "manual":
        if (
            settings.get("optional_document")
            and rule["path"].split(".")[0] not in visible
        ):
            result = "NOT_APPLICABLE"
        message += " " + tpl("ao.manual_evidence_review")
    dependencies = {
        "nik_birth": ["ektp.birth_date", "ektp.gender"],
        "birth": ["ektp.birth_place", "ektp.birth_date"],
    }.get(kind, [])
    if result in {"PASS", "FAIL"}:
        for path in dependencies:
            _, refs = value_at(documents, path)
            if len(refs) != 1 or any(
                i.get("severity") == "REVIEW"
                for d in refs
                for i in d.get("validation", {})
                .get("fields", {})
                .get(path.split(".")[1], {})
                .get("issues", [])
            ):
                result = "REVIEW"
                message += " " + tpl("ao.supporting_source_review")
    # Source uncertainty or absent crop can never become an automatic confirmed comparison.
    if result in {"PASS", "FAIL"}:
        checked_paths = [(rule["path"], left), (rule.get("other_path"), right)]
        for component in component_checks:
            checked_paths.extend(
                (path, value_at(documents, path)[1])
                for path in (component["path"], component["other_path"])
            )
        for path, refs in checked_paths:
            if not path:
                continue
            key = path.split(".")[1]
            for doc in refs:
                if any(
                    i.get("severity") == "REVIEW"
                    for i in doc.get("validation", {})
                    .get("fields", {})
                    .get(key, {})
                    .get("issues", [])
                ):
                    result = "REVIEW"
                    message += " " + tpl("ao.source_uncertainty_review")
    eligible = True
    condition = rule.get("condition_operator", "always")
    if condition in {"equals", "in"}:
        observed = context.get(rule.get("condition_key"), "UNKNOWN")
        wanted = rule.get("condition_value")
        options = (
            wanted.split(",")
            if condition == "in" and isinstance(wanted, str)
            else [wanted]
        )
        if observed in {None, "", "UNKNOWN"}:
            result = "REVIEW"
            message += " " + tpl("ao.applicability_context")
        elif observed not in options:
            result = "NOT_APPLICABLE"
            eligible = False
    elif condition == "document_present" and rule.get("condition_value") not in visible:
        result = "NOT_APPLICABLE"
        eligible = False
    finding = {
        "rule_id": rule["id"],
        "field": rule["path"],
        "source_ref": rule["source_ref"],
        "scope_basis": rule["scope_basis"],
        "category": rule["report_category"],
        "eligible": eligible,
        "result": result,
        "message": message,
        "actual": actual,
        "expected": expected,
        "evidence": {
            "document_ids": [d["id"] for d in left],
            "reference_document_ids": [d["id"] for d in right],
            "path": rule["path"],
            "other_path": rule.get("other_path"),
            "policy": settings,
        },
    }
    if signature_review_required:
        finding["signature_review_required"] = True
        from .configuration.seed_catalog import seed_value

        finding["evidence"]["supporting_paths"] = settings.get(
            "supporting_paths"
        ) or seed_value("account_identity.signature_paths")
    if component_checks:
        finding["evidence"]["component_checks"] = component_checks
    if settings.get("supporting_paths"):
        finding["evidence"]["supporting_paths"] = settings["supporting_paths"]
    return finding


def score(findings):
    from .configuration.scoring import category_scores, ScoreGroups, defaults

    return category_scores(
        findings, ScoreGroups.model_validate(defaults()["account_opening"])
    )
