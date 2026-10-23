"""Explicit, lossless draft proposals; never writes/publishes configuration."""
import copy
import json
import argparse
from pathlib import Path

from .generic_sop import GenericRule, validate_generic_rules
from .identity import IdentityBinding, IdentityPolicy, validate_bindings
from .codec import fingerprint


def supported(rule):
    if rule.get("operator") != "account_check" or rule.get("condition_operator", "always") != "always":
        return False
    try:
        settings = json.loads(rule["comparison_policy"])
    except (KeyError, ValueError, TypeError):
        return False
    return (settings.get("kind") == "match"
            and not (set(settings) - {"kind", "identifier", "optional_document"})
            and not settings.get("identifier") and not settings.get("optional_document"))


def propose_upgrade(payload, selected_ids):
    from app.document_families import families
    from app.transaction_flows import scope_configuration
    from app.domain import validate_config

    selected = set(selected_ids)
    original_rules = payload.get("sop_rules", [])
    existing = {rule["id"] for rule in payload.get("generic_sop_rules", [])}
    known = {rule["id"] for rule in original_rules} | existing
    if selected - known:
        raise ValueError("Upgrade selection includes unknown rules.")
    proposal = copy.deepcopy(payload)
    family_members = {}
    for family in families(payload):
        probe = copy.deepcopy(payload)
        probe["templates"]["__upgrade_probe"] = {"label": "Upgrade probe", "document_family": family}
        family_members[family] = {rule["id"] for rule in scope_configuration(probe, "__upgrade_probe")["sop_rules"]}
    converted = []
    for rule in original_rules:
        if rule["id"] not in selected:
            continue
        if not supported(rule):
            raise ValueError("Selected rule requires an unsupported conversion policy.")
        assigned = [family for family, ids in family_members.items() if rule["id"] in ids]
        if not assigned:
            raise ValueError("Selected rule has no default family membership; assign scope explicitly first.")
        schema_paths = {}
        for path in (rule["path"], rule["other_path"]):
            profile, field = path.split(".", 1)
            # Resolve an explicit scalar or wrapped scalar binding for the draft.
            for schema_field in (field, field + ".raw"):
                try:
                    validate_bindings(IdentityPolicy(bindings=(IdentityBinding(
                        profile=profile, field_path=field, schema_path=schema_field,
                    ),)), payload["profiles"])
                    schema_paths[path] = profile + "." + schema_field
                    break
                except ValueError:
                    continue
            else:
                raise ValueError("Selected rule has no supported text schema binding.")
        definition = GenericRule(
            id=rule["id"], label=rule["label"], enabled=rule["enabled"], families=tuple(assigned),
            source_ref=rule["source_ref"], report_category=rule["report_category"],
            policy={"left": rule["path"], "right": rule["other_path"], "normalization": "casefold_whitespace"},
            schema_paths=schema_paths,
        )
        proposal.setdefault("generic_sop_rules", []).append(definition.model_dump(mode="json"))
        converted.append(rule["id"])
    proposal["sop_rules"] = [rule for rule in proposal["sop_rules"] if rule["id"] not in converted]
    if converted:
        proposal["rule_order"] = payload.get("rule_order", [rule["id"] for rule in original_rules]
                                             + [rule["id"] for rule in payload.get("generic_sop_rules", [])])
    validate_generic_rules(proposal)
    validate_config(proposal)
    return {"basis_sha256": fingerprint(payload), "converted_rule_ids": converted,
            "already_converted": sorted(selected & existing), "payload": proposal,
            "activated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--rule", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
    matches = [record for record in records if record["org"] == args.organization and record["version"] == args.version]
    if len(matches) != 1:
        raise ValueError("Snapshot must contain exactly one selected configuration revision.")
    proposal = propose_upgrade(matches[0]["payload"], args.rule)
    # Exclusive creation avoids accidentally replacing an earlier review draft.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(proposal, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"converted": len(proposal["converted_rule_ids"]), "activated": False}))


if __name__ == "__main__":
    main()
