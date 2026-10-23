"""Family-independent SOP outcome and one-point scoring contract."""

import json

VISUAL_OPERATORS = {
    "signature_visible",
    "signature_visual_consistency",
    "all_pages_marked",
    "stamp_present",
    "stamp_placement",
}


def normalize_findings(findings, rules):
    from .sop import fields

    visual_paths = {
        f["path"]
        for f in fields()
        if f.get("type")
        in {"signature_region", "stamp_region", "photo_region", "page_marks"}
    }
    by_id = {r["id"]: r for r in rules}
    for finding in findings:
        rule = by_id.get(finding["rule_id"], {})
        visual = (
            rule.get("operator") in VISUAL_OPERATORS or rule.get("path") in visual_paths
        )
        if rule.get("operator") == "configured_compare":
            visual = False  # Typed text-only policies cannot request visual review.
        if rule.get("operator") == "configured_visual":
            visual = True
        if rule.get("operator") == "account_check":
            policy = rule.get("comparison_policy") or "{}"
            settings = json.loads(policy) if isinstance(policy, str) else policy
            visual = visual or (
                settings.get("kind") == "identity_name"
                and finding.get("signature_review_required") is True
            )
            # Visual field results carry a presence observation; text fields do not.
            visual = visual or (
                settings.get("kind") == "field"
                and isinstance(finding.get("actual"), dict)
                and "present" in finding["actual"]
            )
            # Missing visual observations still need a picture inspection.
            field = rule.get("path", "").lower()
            visual = visual or (
                settings.get("kind") in {"field", "manual"}
                and any(
                    token in field
                    for token in (
                        "signature",
                        "stamp",
                        "photo",
                        "initial",
                        "fingerprint",
                    )
                )
            )
        finding["evaluation_type"] = "VISUAL" if visual else "DATA"
        if finding["result"] == "REVIEW" and not visual:
            finding["result"] = "FAIL"
            finding["reason_code"] = "INSUFFICIENT_OR_UNVERIFIED_DATA"
            finding[
                "message"
            ] += " Check failed: required data, applicability context or reliable comparison evidence is unavailable. Correct the data/context and rerun SOP checks."
        else:
            finding.setdefault(
                "reason_code",
                {
                    "PASS": "CHECK_PASSED",
                    "FAIL": "CHECK_FAILED",
                    "REVIEW": "VISUAL_REVIEW_REQUIRED",
                    "NOT_APPLICABLE": "EXPLICITLY_NOT_APPLICABLE",
                }.get(finding["result"], "EVALUATION_ERROR"),
            )
    return findings


def point_summary(findings):
    applicable = [
        f
        for f in findings
        if f.get("eligible", True) and f["result"] != "NOT_APPLICABLE"
    ]
    passed = sum(f["result"] == "PASS" for f in applicable)
    failed = sum(f["result"] == "FAIL" for f in applicable)
    pending = len(applicable) - passed - failed
    return {
        "version": 1,
        "earned": passed,
        "possible": len(applicable),
        "passed": passed,
        "failed": failed,
        "pending": pending,
        "resolved": passed + failed,
        "not_applicable": sum(f["result"] == "NOT_APPLICABLE" for f in findings),
        "percentage": round(100 * passed / len(applicable), 2) if applicable else None,
        "provisional": pending > 0,
    }
