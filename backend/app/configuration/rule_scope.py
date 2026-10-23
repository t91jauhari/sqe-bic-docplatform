"""Explicit family membership, independent of source-reference wording."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RuleScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    family_rule_ids: dict[str, list[str]] = Field(max_length=100)

    @model_validator(mode="after")
    def distinct_rules(self):
        for rules in self.family_rule_ids.values():
            if len(rules) != len(set(rules)):
                raise ValueError("Family rule selections must not contain duplicates.")
        return self


def validate_rule_scope(payload):
    from app.document_families import families

    policy = RuleScope.model_validate(payload["rule_scope"])
    catalog = families(payload)
    if set(policy.family_rule_ids) != set(catalog):
        raise ValueError("Explicit rule scope must cover every registered family.")
    known = {rule["id"] for rule in payload.get("sop_rules", []) + payload.get("generic_sop_rules", [])}
    generic = {rule["id"]: rule for rule in payload.get("generic_sop_rules", [])}
    for family, rules in policy.family_rule_ids.items():
        if set(rules) - known:
            raise ValueError("Rule scope references unknown SOP rules.")
        if any(rule_id in generic and family not in generic[rule_id]["families"] for rule_id in rules):
            raise ValueError("Generic rule is not assigned to the selected family.")
    return policy
