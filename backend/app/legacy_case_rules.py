"""Legacy Case Rules operations."""

from decimal import Decimal, InvalidOperation


def riplay_identity_findings(documents, cfg):
    riplays = [
        d for d in documents if d.doc_type == "riplay" and d.status == "COMPLETED"
    ]
    if not riplays or not cfg["profiles"].get("riplay", {}).get("policy", {}).get(
        "require_identity_match", True
    ):
        return []
    identities = [
        d for d in documents if d.doc_type == "ektp" and d.status == "COMPLETED"
    ]
    findings = []
    for doc in riplays:
        actual = doc.normalized.get("customer_name")
        expected = (
            identities[0].normalized.get("name") if len(identities) == 1 else None
        )
        valid_reference = (
            len(identities) == 1
            and identities[0].validation.get("fields", {}).get("name", {}).get("status")
            == "PASS"
        )
        result = "REVIEW"
        if actual and expected and valid_reference:

            def normalize(value):
                return " ".join(str(value).split()).casefold()

            result = "PASS" if normalize(actual) == normalize(expected) else "FAIL"
        findings.append(
            {
                "rule_id": "riplay.customer_name_vs_ektp.name",
                "field": "riplay.customer_name",
                "actual": actual,
                "expected": expected,
                "result": result,
                "message": "RIPLAY customer name must match one readable eKTP name in this case; missing or ambiguous reference needs review.",
                "evidence": {
                    "document_id": doc.id,
                    "reference_document_ids": [d.id for d in identities],
                    "match_method": "case_and_whitespace_insensitive_exact",
                },
            }
        )
    return findings


def extract_path(documents, path, context=None):
    from .valas_resolution import is_valas_prefix, get_case_valas_document, resolve_valas_path

    parts = path.split(".")
    prefix = parts[0]
    matched = [
        d
        for d in documents
        if (getattr(d, "doc_type", None) or (d.get("doc_type") if isinstance(d, dict) else None)) == prefix
        and (getattr(d, "status", None) or (d.get("status") if isinstance(d, dict) else None)) == "COMPLETED"
    ]
    if len(matched) != 1 and is_valas_prefix(prefix):
        valas_doc, valas_type = get_case_valas_document(documents, context)
        if valas_doc:
            remapped_path, applicable, _ = resolve_valas_path(path, valas_type, context)
            if applicable:
                matched = [valas_doc]
                parts = remapped_path.split(".")
    if len(matched) != 1:
        return None
    doc = matched[0]
    value = doc.normalized if hasattr(doc, "normalized") else doc.get("normalized", {})
    for part in parts[1:]:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def evaluate_rules(documents, rules):
    findings = []
    for rule in rules:
        actual = extract_path(documents, rule["path"])
        expected = rule.get("value")
        op = rule["operator"]
        result = "PASS"
        if op == "required":
            valid = actual not in (None, "", [], {})
        elif actual is None:
            valid = False
            result = "REVIEW"
        elif op == "equals":
            valid = actual == expected
        elif op == "enum":
            valid = actual in expected if isinstance(expected, list) else False
        elif op == "positive":
            try:
                valid = Decimal(str(actual)) > 0
            except InvalidOperation:
                valid = False
        elif op in {"date_equal", "date_on_or_after"}:
            from .date_utils import compare_dates
            expected = rule.get("value")
            if expected is None and rule.get("other_path"):
                expected = extract_path(documents, rule["other_path"])
            if expected is None:
                result = "REVIEW"
                valid = False
            else:
                try:
                    valid = compare_dates(actual, expected, op=op)
                except Exception:
                    valid = False
        else:
            expected = extract_path(documents, rule["other_path"])
            if expected is None:
                result = "REVIEW"
                valid = False
            else:
                (a, b) = (
                    str(actual).strip().casefold(),
                    str(expected).strip().casefold(),
                )
                valid = a == b
        if not valid and result != "REVIEW":
            result = rule["severity"]
        findings.append(
            {
                "rule_id": rule["id"],
                "field": rule["path"],
                "actual": actual,
                "expected": expected,
                "result": result,
                "message": rule.get("label", rule["id"]),
                "evidence": {"path": rule["path"]},
            }
        )
    return findings
