"""Configuration-defined text comparisons with explicit applicability/evidence."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .comparison import ComparisonPolicy, evaluate_comparison, _read
from .identity import IdentityBinding
from .field_options import validate_text_binding
from .sop_policies import (
    DatePolicy,
    MoneyPolicy,
    VisualPolicy,
    paths,
    read_value,
    evaluate_policy,
    validate_visual_binding,
)


class Applicability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    context_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=80)
    equals: str = Field(min_length=1, max_length=200)


class GenericRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    label: str = Field(min_length=1, max_length=1000)
    enabled: bool = True
    families: tuple[str, ...] = Field(min_length=1, max_length=100)
    report_category: Literal[
        "DATA_COMPLETION",
        "CUSTOMER_SIGNATURE",
        "DOCUMENT_COMPLETION",
        "OFFICER_REVIEW_APPROVAL",
    ] = "DATA_COMPLETION"
    source_ref: str = Field(default="Configured SOP rule", min_length=1, max_length=500)
    policy: ComparisonPolicy | DatePolicy | MoneyPolicy | VisualPolicy
    schema_paths: dict[str, str] = Field(default_factory=dict)
    applicability: Applicability | None = None


def validate_generic_rules(payload):
    from app.document_families import families

    catalog = families(payload)
    ids = {rule["id"] for rule in payload.get("sop_rules", [])}
    rules = []
    context_catalogs = {}
    if (
        not isinstance(payload.get("generic_sop_rules", []), list)
        or len(payload.get("generic_sop_rules", [])) > 1000
    ):
        raise ValueError("Configure at most 1000 generic SOP rules.")
    for value in payload.get("generic_sop_rules", []):
        rule = GenericRule.model_validate(value)
        if rule.applicability:
            from .contexts import enum_options

            for family in rule.families:
                if family not in context_catalogs:
                    context_catalogs[family] = enum_options(payload, family)
                if rule.applicability.equals not in context_catalogs[family].get(
                    rule.applicability.context_key, []
                ):
                    raise ValueError(
                        "Generic applicability must use a registered context option available to its family."
                    )
        if rule.id in ids:
            raise ValueError("Generic SOP rule IDs must be unique across all rules.")
        ids.add(rule.id)
        if len(set(rule.families)) != len(rule.families) or set(rule.families) - set(
            catalog
        ):
            raise ValueError("Choose distinct registered rule families.")
        bindings = paths(rule.policy)
        if set(rule.schema_paths) - set(bindings):
            raise ValueError("Schema bindings must reference a compared field.")
        for path in bindings:
            profile, field = path.split(".", 1)
            schema_path = rule.schema_paths.get(path, path)
            if not schema_path.startswith(profile + "."):
                raise ValueError("Schema binding must reference the same profile.")
            binding = IdentityBinding(
                profile=profile,
                field_path=field,
                schema_path=schema_path.split(".", 1)[1],
            )
            if isinstance(rule.policy, VisualPolicy):
                validate_visual_binding(payload["profiles"], schema_path, rule.policy)
            elif isinstance(rule.policy, MoneyPolicy) and path in {
                rule.policy.left,
                rule.policy.right,
            }:
                from .field_options import validate_scalar_binding

                validate_scalar_binding(binding, payload["profiles"])
            else:
                validate_text_binding(binding, payload["profiles"])
            if any(
                profile not in catalog[family]["profiles"] for family in rule.families
            ):
                raise ValueError(
                    "Compared profiles must belong to every selected family."
                )
        rules.append(rule)
    by_id = {rule.id: rule for rule in rules}
    for flow in payload.get("templates", {}).values():
        for rule_id in flow.get("sop_rule_ids") or []:
            if (
                rule_id in by_id
                and flow.get("document_family", "forex") not in by_id[rule_id].families
            ):
                raise ValueError("Flow selects a generic rule from another family.")
    return rules


def runtime_rule(rule: GenericRule, context_options=None):
    return {
        "id": rule.id,
        "label": rule.label,
        "enabled": rule.enabled,
        "operator": "configured_" + rule.policy.type,
        "path": rule.policy.left,
        "other_path": rule.policy.right,
        "source_ref": rule.source_ref,
        "report_category": rule.report_category,
        "scope_basis": "Configured document comparison",
        "generic_definition": rule.model_dump(mode="json"),
        "context_options": context_options,
    }


def evaluate_generic(rule, documents, context):
    definition = GenericRule.model_validate(rule["generic_definition"])
    policy = definition.policy
    reader = _read if isinstance(policy, ComparisonPolicy) else read_value
    actual, _ = reader(documents, policy.left)
    expected, _ = reader(documents, policy.right)
    refs = [
        [
            doc
            for doc in documents
            if doc.get("doc_type") == path.split(".")[0]
            and doc.get("status") == "COMPLETED"
        ]
        for path in (policy.left, policy.right)
    ]
    if isinstance(policy, ComparisonPolicy):
        result = evaluate_comparison(documents, policy)
        status, reason = result.result, result.reason.upper()
    else:
        status, reason = evaluate_policy(policy, documents)
    if definition.applicability:
        observed = context.get(definition.applicability.context_key)
        known = (rule.get("context_options") or {}).get(
            definition.applicability.context_key
        )
        if (
            observed in (None, "", "UNKNOWN")
            or known is not None
            and observed not in known
        ):
            status, reason = "FAIL", "APPLICABILITY_UNKNOWN"
        elif observed != definition.applicability.equals:
            status, reason = "NOT_APPLICABLE", "EXPLICITLY_NOT_APPLICABLE"
    if (
        not isinstance(policy, VisualPolicy)
        and status in {"PASS", "FAIL"}
        and reason != "APPLICABILITY_UNKNOWN"
    ):
        for path in paths(policy):
            matches = [
                doc
                for doc in documents
                if doc.get("doc_type") == path.split(".")[0]
                and doc.get("status") == "COMPLETED"
            ]
            field = path.split(".")[1]
            if any(
                issue.get("severity") in {"REVIEW", "FAIL", "ERROR"}
                for doc in matches
                for issue in doc.get("validation", {})
                .get("fields", {})
                .get(field, {})
                .get("issues", [])
            ):
                status, reason = "FAIL", "INSUFFICIENT_OR_UNVERIFIED_DATA"
    return {
        "rule_id": definition.id,
        "field": policy.left,
        "source_ref": definition.source_ref,
        "scope_basis": rule["scope_basis"],
        "category": definition.report_category,
        "eligible": True,
        "result": status,
        "reason_code": reason,
        "message": definition.label + " — " + reason.replace("_", " ").lower(),
        "actual": actual,
        "expected": expected,
        "evidence": {
            "document_ids": [doc["id"] for doc in refs[0]],
            "reference_document_ids": [doc["id"] for doc in refs[1]],
            "path": policy.left,
            "other_path": policy.right,
            "policy": policy.model_dump(mode="json"),
        },
    }
