"""Typed account SOP policy grammar; historical JSON remains lossless."""

import copy
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Pair(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    path: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", max_length=500)
    other_path: str = Field(
        pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", max_length=500
    )


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    path: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", max_length=500)
    true_values: list[str] = Field(min_length=1, max_length=1000)
    false_values: list[str] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def disjoint_options(self):
        def normalized(values):
            return {" ".join(value.split()).casefold() for value in values}

        left, right = normalized(self.true_values), normalized(self.false_values)
        if (
            "" in left | right
            or left & right
            or len(left) != len(self.true_values)
            or len(right) != len(self.false_values)
        ):
            raise ValueError(
                "Conditional values must be nonempty, distinct and nonoverlapping after case/space normalization."
            )
        return self


class AccountPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    kind: Literal[
        "field",
        "document",
        "match",
        "identity_name",
        "gender",
        "birth",
        "nik_birth",
        "conditional_edd",
        "conditional_bo",
        "conditional_visit",
        "conditional_signature",
        "conditional_survey",
        "manual",
    ]
    optional_document: bool = False
    require_two_signatures: bool = False
    identifier: bool = False
    target: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,49}$")
    required_pattern: str | None = Field(default=None, max_length=120)
    allowed_values: list[str] | None = Field(
        default=None, min_length=1, max_length=1000
    )
    companion_matches: list[Pair] = Field(default_factory=list, max_length=100)
    trigger: Condition | None = None
    supporting_paths: list[str] | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("required_pattern")
    @classmethod
    def bounded_format(cls, value):
        if value is not None and not re.fullmatch(r"\[0-9\]\{[1-9][0-9]?\}", value):
            raise ValueError(
                "Use a fixed digit-count constraint, for example [0-9]{16}."
            )
        return value

    @model_validator(mode="after")
    def applicable_settings(self):
        allowed = {"kind"}
        if self.kind in {"field", "match", "identity_name", "manual"}:
            allowed.add("optional_document")
        if self.kind in {"identity_name", "manual"}:
            allowed.add("require_two_signatures")
            allowed.add("supporting_paths")
        if self.kind == "match":
            allowed.update(
                {
                    "identifier",
                    "required_pattern",
                    "allowed_values",
                    "companion_matches",
                }
            )
        if self.kind.startswith("conditional_"):
            allowed.update({"target", "trigger"})
            if not self.target:
                raise ValueError(
                    "Conditional document checks require a target profile ID."
                )
        if self.model_fields_set - allowed:
            raise ValueError(
                "This check kind cannot execute the supplied policy options."
            )
        if self.allowed_values and any(
            not value.strip() or len(value) > 1000 for value in self.allowed_values
        ):
            raise ValueError(
                "Allowed values require nonempty text of at most 1000 characters."
            )
        if self.supporting_paths is not None and (
            not self.require_two_signatures or len(set(self.supporting_paths)) != 2
        ):
            raise ValueError(
                "Supporting signature paths require two distinct regions and signature comparison."
            )
        return self


def parse_policy(value):
    raw = json.loads(value) if isinstance(value, str) else copy.deepcopy(value)
    AccountPolicy.model_validate(raw)
    return raw


def condition_result(documents, definition):
    from app.sop import value_at, normalize

    policy = Condition.model_validate(definition)
    value, refs = value_at(documents, policy.path)
    if len(refs) != 1:
        return None
    field = (
        refs[0]
        .get("validation", {})
        .get("fields", {})
        .get(policy.path.split(".")[1], {})
    )
    if field.get("status") in {"FAIL", "ERROR", "REVIEW"} or any(
        issue.get("severity") in {"FAIL", "ERROR", "REVIEW"}
        for issue in field.get("issues", [])
    ):
        return None
    if isinstance(value, dict) and "raw" in value and value.get("complete") is True:
        value = value["raw"]
    if not isinstance(value, str) or not value.strip():
        return None
    observed = normalize(value)
    return (
        True
        if observed in {normalize(value) for value in policy.true_values}
        else (
            False
            if observed in {normalize(value) for value in policy.false_values}
            else None
        )
    )


def captured_conditions():
    return json.loads(
        (
            Path(__file__).parents[1] / "config_data/account_conditions_v1.json"
        ).read_text(encoding="utf-8")
    )


def propose_conditions(payload, selected_ids):
    from app.configuration.validation import validate_config

    catalog = captured_conditions()
    proposal = copy.deepcopy(payload)
    selected = set(selected_ids)
    rules = {rule["id"]: rule for rule in proposal.get("sop_rules", [])}
    if selected - set(rules):
        raise ValueError("Conditional upgrade selection contains unknown rules.")
    changed = []
    for rule_id in selected_ids:
        rule = rules[rule_id]
        policy = parse_policy(rule["comparison_policy"])
        if policy["kind"] not in catalog:
            raise ValueError(
                "This requirement has no captured condition; define its criteria explicitly."
            )
        if "trigger" not in policy:
            policy["trigger"] = copy.deepcopy(catalog[policy["kind"]])
            rule["comparison_policy"] = json.dumps(policy, ensure_ascii=False)
            changed.append(rule_id)
    validate_config(proposal)
    return {"changed_rule_ids": changed, "payload": proposal}
