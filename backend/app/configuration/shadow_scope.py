"""Read-only verification of explicit rule membership on restored flow configs."""
import argparse
import copy
import json
import os

from sqlalchemy import create_engine, text


def compare_scope(payload):
    from app.document_families import families
    from app.transaction_flows import scope_configuration

    configured = copy.deepcopy(payload)
    mapping = {}
    for family_id in families(payload):
        probe = copy.deepcopy(payload)
        probe["templates"]["__scope_probe"] = {"label": "Scope probe", "document_family": family_id}
        mapping[family_id] = [rule["id"] for rule in scope_configuration(probe, "__scope_probe")["sop_rules"]]
    configured["rule_scope"] = {"family_rule_ids": mapping}
    checked = 0
    for flow_id in payload["templates"]:
        previous = scope_configuration(payload, flow_id)
        current = scope_configuration(configured, flow_id)
        current.pop("rule_scope", None)
        if previous != current:
            raise ValueError("Explicit membership changed scoped configuration.")
        checked += 1
    return checked


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
            payloads = connection.scalars(text("SELECT payload FROM configurations ORDER BY org,version")).all()
            count = sum(compare_scope(payload) for payload in payloads)
        print(json.dumps({"configurations": len(payloads), "flow_scopes_checked": count,
                          "mismatches": 0, "activated": False}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
