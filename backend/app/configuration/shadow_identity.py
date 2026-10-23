"""Read-only comparison on restored cases; no provider calls or activation."""
import argparse
import copy
import json
import os
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, text

from .identity import IdentityPolicy, validate_bindings


def compare(records, policy):
    from app.grouping import identity_conflicts

    mismatches = []
    errors = []
    reasons = Counter()
    for record in records:
        original = record["configuration"]
        configured = copy.deepcopy(original)
        configured["identity_policy"] = {
            **policy, "bindings": [copy.deepcopy(binding) for binding in policy["bindings"]
                                   if binding["profile"] in original["profiles"]],
        }
        try:
            # Historical schemas changed from scalar names to wrapped text.
            # Resolve only these two representations, validating either choice.
            for binding in configured["identity_policy"]["bindings"]:
                try:
                    validate_bindings(IdentityPolicy(bindings=(binding,)), configured["profiles"])
                except ValueError:
                    if "schema_path" not in binding:
                        raise
                    binding.pop("schema_path")
                    validate_bindings(IdentityPolicy(bindings=(binding,)), configured["profiles"])
            validate_bindings(IdentityPolicy.model_validate(configured["identity_policy"]), configured["profiles"])
            old = identity_conflicts(record["documents"], original)
            new = identity_conflicts(record["documents"], configured)
            if old != new:
                mismatches.append(record["id"])
        except ValueError as exc:
            errors.append(record["id"])
            reasons[str(exc)] += 1
    return {"cases_checked": len(records), "mismatches": len(mismatches),
            "configuration_errors": len(errors), "error_reasons": dict(reasons), "activated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-database", required=True)
    args = parser.parse_args()
    # Import application only after explicit isolated environment is established.
    engine = create_engine(os.environ["REFACTOR_DATABASE_URL"])
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != args.expected_database:
                raise ValueError("Unexpected database.")
            connection.commit()
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                records = []
                for case in connection.execute(text(
                    "SELECT c.id, cfg.payload FROM cases c JOIN configurations cfg ON cfg.id=c.config_id ORDER BY c.id"
                )).mappings():
                    docs = [dict(row) for row in connection.execute(text(
                        "SELECT id,doc_type,status,normalized FROM documents WHERE case_id=:id ORDER BY created_at"
                    ), {"id": case["id"]}).mappings()]
                    records.append({"id": case["id"], "configuration": case["payload"], "documents": docs})
                if not records:
                    raise ValueError("No saved cases found.")
                policy = json.loads(Path(__file__).with_name("legacy_identity_bindings.json").read_text())
                result = compare(records, policy)
        print(json.dumps(result))
        if result["mismatches"] or result["configuration_errors"]:
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
