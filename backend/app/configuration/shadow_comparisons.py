"""Read-only outcome comparison for the supported plain-text SOP subset."""
import argparse
import json
import os
from collections import Counter

from sqlalchemy import create_engine, text


def compare_records(records):
    from app.account_opening_sop import evaluate_rule
    from app.transaction_flows import scope_configuration
    from .comparison import ComparisonPolicy
    from .generic_sop import GenericRule, runtime_rule
    from app.sop import evaluate

    counts = Counter()
    for record in records:
        cfg = scope_configuration(record["configuration"], record["template"])
        for rule in cfg.get("sop_rules", []):
            if not rule.get("enabled") or rule.get("operator") != "account_check":
                continue
            settings = json.loads(rule["comparison_policy"])
            if (settings.get("kind") != "match" or settings.get("identifier")
                    or settings.get("required_pattern") or settings.get("allowed_values")
                    or settings.get("companion_matches") or settings.get("optional_document")
                    or rule.get("condition_operator", "always") != "always"):
                counts["unsupported_rules_skipped"] += 1
                continue
            previous = evaluate_rule(rule, record["documents"], cfg, {})
            if previous["result"] not in {"PASS", "FAIL"}:
                counts["unresolved_results_skipped"] += 1
                continue
            policy = ComparisonPolicy(left=rule["path"], right=rule["other_path"],
                                      normalization="casefold_whitespace")
            generic = GenericRule(id=rule["id"], label=rule["label"], families=("shadow_only",),
                                  policy=policy, report_category=rule["report_category"],
                                  source_ref=rule["source_ref"])
            current = evaluate(record["documents"], {"sop_rules": [runtime_rule(generic)]}, {})[0]
            counts["outcomes_checked"] += 1
            if current["result"] != previous["result"] or current["eligible"] != previous["eligible"] or current["category"] != previous["category"]:
                counts["mismatches"] += 1
    return {"cases_loaded": len(records), "outcomes_checked": counts["outcomes_checked"],
            "mismatches": counts["mismatches"],
            "unsupported_rules_skipped": counts["unsupported_rules_skipped"],
            "unresolved_results_skipped": counts["unresolved_results_skipped"],
            "activated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-database", required=True)
    args = parser.parse_args()
    engine = create_engine(os.environ["REFACTOR_DATABASE_URL"])
    try:
        with engine.begin() as connection:
            if connection.scalar(text("SELECT current_database()")) != args.expected_database:
                raise ValueError("Unexpected database.")
        with engine.begin() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            records = []
            for case in connection.execute(text(
                "SELECT c.id,c.template,cfg.payload FROM cases c JOIN configurations cfg ON cfg.id=c.config_id"
            )).mappings():
                docs = [dict(row) for row in connection.execute(text(
                    "SELECT id,doc_type,status,normalized,validation FROM documents WHERE case_id=:id ORDER BY created_at"
                ), {"id": case["id"]}).mappings()]
                records.append({"configuration": case["payload"], "template": case["template"], "documents": docs})
            result = compare_records(records)
        print(json.dumps(result))
        if not result["outcomes_checked"] or result["mismatches"]:
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
