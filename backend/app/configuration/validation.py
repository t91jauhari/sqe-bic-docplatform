"""Configuration Validation operations."""

from app.native_profiles import ACCOUNT_REFERENCE, PROFILE_NAMES, check_directory
import copy
import re
from app.settings import settings
from account_opening.profiles import REFERENCE as ACCOUNT_REFERENCE


def validate_config(payload):
    from app.configuration.bootstrap import default_config
    from app.configuration.contracts import validate_envelope

    validate_envelope(payload)
    from app.configuration.dataset_policy import validate_comparison_policies

    validate_comparison_policies(payload)
    from app.configuration.reporting import validate_report_definitions

    validate_report_definitions(payload)
    from app.configuration.contexts import validate_definitions

    validate_definitions(payload)
    if "rule_order" in payload:
        order = payload["rule_order"]
        known = {
            rule["id"]
            for rule in payload.get("sop_rules", [])
            + payload.get("generic_sop_rules", [])
        }
        if (
            not isinstance(order, list)
            or any((not isinstance(value, str) for value in order))
            or len(order) != len(set(order))
            or (set(order) != known)
        ):
            raise ValueError("Rule order must list each registered rule exactly once.")
    if "generic_sop_rules" in payload:
        from app.configuration.generic_sop import validate_generic_rules

        validate_generic_rules(payload)
    if "rule_scope" in payload:
        from app.configuration.rule_scope import validate_rule_scope

        validate_rule_scope(payload)
    if "identity_policy" in payload:
        from app.configuration.identity import IdentityPolicy, validate_bindings

        validate_bindings(
            IdentityPolicy.model_validate(payload["identity_policy"]),
            payload["profiles"],
        )
    from app.forex_sop import validate_policy

    validate_policy(payload)
    from app.schema_descriptions import validate_profile_schema, validate_descriptions

    base = default_config()
    variants = payload.get("profile_variants", {})
    if not isinstance(variants, dict) or set(variants) - set(
        payload.get("profiles", {})
    ):
        raise ValueError("Invalid profile variant document types.")
    for name, bank in variants.items():
        if not isinstance(bank, dict) or len(bank) > 30:
            raise ValueError("Invalid profile variant collection.")
        for key, variant in bank.items():
            if (
                not isinstance(key, str)
                or not isinstance(variant, dict)
                or (not isinstance(variant.get("name"), str))
                or (not variant["name"].strip())
            ):
                raise ValueError("Profile variants require a name.")
            candidate = copy.deepcopy(base)
            candidate["profiles"][name] = variant["profile"]
            validate_config(candidate)
    if payload.get("provider") not in {"spider-ai", "fixture"}:
        raise ValueError(
            "Select spider-ai or fixture provider. Llama provider has been removed."
        )
    if payload["provider"] == "fixture" and settings.environment != "development":
        raise ValueError("Fixture mode is development-only.")
    if type(payload.get("sop_review_bypass")) is not bool:
        raise ValueError("sop_review_bypass must be true or false.")
    if payload.get("sop_review_bypass_result") not in {
        "PASS",
        "REVIEW",
        "NOT_APPLICABLE",
    }:
        raise ValueError(
            "sop_review_bypass_result must be PASS, REVIEW, or NOT_APPLICABLE."
        )
    prefixes = payload.get("grouping_prefixes")
    if (
        not isinstance(prefixes, list)
        or not all((isinstance(p, str) and p.strip() for p in prefixes))
        or len(prefixes) > 200
    ):
        raise ValueError("grouping_prefixes must be a list of non-empty strings.")
    aliases = payload.get("suffix_aliases")
    if (
        not isinstance(aliases, dict)
        or not all(
            (
                isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
                for (k, v) in aliases.items()
            )
        )
        or len(aliases) > 500
    ):
        raise ValueError(
            "suffix_aliases must map non-empty strings to non-empty strings."
        )
    templates = payload.get("sop_message_templates")
    if (
        not isinstance(templates, dict)
        or not all(
            (
                isinstance(k, str) and k.strip() and isinstance(v, str)
                for (k, v) in templates.items()
            )
        )
        or len(templates) > 500
    ):
        raise ValueError("sop_message_templates must map keys to message strings.")
    for flag in ["sequential_page_extraction", "cross_page_reference"]:
        if type(payload.get(flag)) is not bool:
            raise ValueError(f"{flag} must be true or false.")
    for tier in ["parse_tier", "extract_tier"]:
        if payload.get(tier) not in {"agentic", "agentic_plus", "cost_effective"}:
            raise ValueError("Invalid processing tier.")
    if payload.get("family_catalog_mode", "legacy") != "explicit" and (
        not set(PROFILE_NAMES).issubset(payload.get("profiles", {}))
    ):
        raise ValueError("All supported profile configurations are required.")
    if len(payload["profiles"]) > 200:
        raise ValueError("Configure at most 200 document profiles.")
    for name, p in payload["profiles"].items():
        if not re.fullmatch("[a-z][a-z0-9_]{0,49}", name) or not isinstance(p, dict):
            raise ValueError(
                "Profile IDs must use lowercase identifiers of at most 50 characters and object definitions."
            )
        if (
            not isinstance(p.get("label"), str)
            or not 1 <= len(p["label"].strip()) <= 200
        ):
            raise ValueError(f"{name}: a display label is required.")
        native = name in base["profiles"]
        if not native and payload["provider"] == "fixture":
            raise ValueError(
                "Custom profiles require a configured extraction provider; built-in fixture files do not cover them."
            )
        if p.get("validation_adapter", "native" if native else "") != (
            "native" if native else "schema"
        ):
            raise ValueError(
                "Custom profiles require the schema validation adapter; native adapters cannot be replaced."
            )
        baseline = (
            base["profiles"][name]
            if native
            else {"schema": p.get("schema", {}), "policy": {}}
        )
        if not native and (not p.get("schema")):
            raise ValueError("Custom profiles require an explicit schema.")
        if "system_instruction" in p and (
            not isinstance(p["system_instruction"], str)
            or not 10 <= len(p["system_instruction"].strip()) <= 30000
        ):
            raise ValueError(
                f"{name}: System Instruction must contain 10–30000 characters."
            )
        if name in ACCOUNT_REFERENCE["profiles"]:
            from account_opening.profiles import validate_policy

            validate_policy(name, p.get("policy", {}))
        if name == "ektp":
            from app.enum_aliases import validate_aliases

            validate_aliases(p.get("policy", {}))
        validate_profile_schema(p, baseline, payload["provider"])
        from app.configuration.field_checks import validate_field_checks

        validate_field_checks(p)
        if not native:
            from app.configuration.profiles import validate_schema_adapter

            validate_schema_adapter(p)
        if "schema" in p:
            validate_descriptions(p["schema"], name)
        if "schema_version" in p and (
            not re.fullmatch("[a-f0-9]{64}", str(p["schema_version"]))
        ):
            raise ValueError(f"{name}: invalid schema version.")
        if not isinstance(p.get("policy"), dict) or not set(
            baseline["policy"]
        ).difference({"enum_aliases", "enum_raw_fallback_fields"}).issubset(
            p["policy"]
        ):
            raise ValueError(f"{name}: missing policy keys.")
        if not all(
            (
                isinstance(p.get(x), str) and p[x].strip()
                for x in ["parse_prompt", "system_prompt"]
            )
        ):
            raise ValueError(f"{name}: prompts cannot be blank.")
        if (
            not isinstance(p.get("classification_description"), str)
            or not p["classification_description"].strip()
        ):
            raise ValueError(f"{name}: classification description is required.")
        if not isinstance(p.get("suffixes"), list) or not all(
            (isinstance(x, str) and x.strip() for x in p["suffixes"])
        ):
            raise ValueError(f"{name}: invalid suffixes.")
        for key, expected in baseline["policy"].items():
            actual = p["policy"][key]
            if expected is not None:
                valid = isinstance(actual, type(expected))
                if isinstance(expected, float):
                    valid = isinstance(actual, (int, float)) and (
                        not isinstance(actual, bool)
                    )
                if isinstance(expected, int) and (not isinstance(expected, bool)):
                    valid = isinstance(actual, int) and (not isinstance(actual, bool))
                if not valid:
                    raise ValueError(f"{name}: policy.{key} has an invalid type.")
    aliases = payload.get("customer_aliases", {})
    if not isinstance(aliases, dict) or any(
        (
            not isinstance(k, str)
            or not k.strip()
            or (not isinstance(v, str))
            or (not v.strip())
            for (k, v) in aliases.items()
        )
    ):
        raise ValueError(
            "Customer aliases must map non-empty labels to canonical names."
        )
    if len({k.strip().casefold() for k in aliases}) != len(aliases):
        raise ValueError("Duplicate normalized customer alias.")
    check_directory(payload.get("name_directory", {}))
    if not isinstance(payload.get("maker_checker"), bool):
        raise ValueError("maker_checker must be boolean.")
    if (
        not isinstance(payload.get("classification_threshold"), (int, float))
        or not 0 <= payload["classification_threshold"] <= 1
    ):
        raise ValueError("Classification threshold must be between zero and one.")
    from app.transaction_flows import validate_flows

    validate_flows(payload)
    if (
        not isinstance(payload.get("report_title"), str)
        or not payload["report_title"].strip()
        or len(payload["report_title"]) > 200
    ):
        raise ValueError("Report title must contain 1–200 characters.")
    for key in ("parse_version", "extract_version"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError("Provider versions must not be blank.")
    for template in payload["templates"].values():
        if not set(template.get("required", [])).issubset(payload["profiles"]):
            raise ValueError("Template includes an unknown document type.")
    ids = set()
    for rule in payload.get("rules", []):
        if rule.get("id") in ids or not rule.get("id"):
            raise ValueError("Rule IDs must be unique.")
        ids.add(rule["id"])
        if rule.get("operator") not in {
            "required",
            "equals",
            "enum",
            "positive",
            "match",
        }:
            raise ValueError("Unsupported SOP operator.")
        if rule.get("severity") not in {"FAIL", "REVIEW"}:
            raise ValueError("Rule severity must be FAIL or REVIEW.")
        if (
            not rule.get("path")
            or rule["path"].split(".")[0] not in payload["profiles"]
        ):
            raise ValueError("Rule paths start with a document profile.")
        if rule["operator"] == "match" and (
            not rule.get("other_path")
            or rule["other_path"].split(".")[0] not in payload["profiles"]
        ):
            raise ValueError("A match rule requires another profile.field path.")
    from app.sop import validate_business

    validate_business(payload)
    return payload
