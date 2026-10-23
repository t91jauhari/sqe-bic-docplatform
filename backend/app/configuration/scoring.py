"""Configurable report grouping; every applicable SOP still earns one point."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

CORE_CATEGORIES = {
    "DATA_COMPLETION",
    "CUSTOMER_SIGNATURE",
    "DOCUMENT_COMPLETION",
    "OFFICER_REVIEW_APPROVAL",
}
Category = Literal[
    "DATA_COMPLETION",
    "CUSTOMER_SIGNATURE",
    "DOCUMENT_COMPLETION",
    "OFFICER_REVIEW_APPROVAL",
    "DOCUMENT_VERIFICATION",
    "OBSERVATIONS",
]


class ScoreGroups(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    total_a: list[Category]
    total_b: list[Category]

    @model_validator(mode="after")
    def partition(self):
        values = self.total_a + self.total_b
        if (
            not self.total_a
            or not self.total_b
            or len(values) != len(set(values))
            or not CORE_CATEGORIES <= set(values)
        ):
            raise ValueError("Assign every score category once to Total A or Total B.")
        return self


def defaults():
    from .seed_catalog import seed_value

    return seed_value("report_scoring.groups")


def groups_for(cfg, flow_id):
    from app.document_families import families

    flow = cfg["templates"][flow_id]
    family = families(cfg)[flow.get("document_family", "forex")]
    raw = family.get("scoring_policy")
    if raw is None:
        raw = defaults()[flow.get("report_layout", "forex")]
    return ScoreGroups.model_validate(raw)


def category_scores(findings, groups):
    def roll(values):
        return (
            0
            if 0 in values
            else 1 if values and all(value == 1 for value in values) else None
        )

    scores = {}
    for category in groups.total_a + groups.total_b:
        results = [
            finding["result"]
            for finding in findings
            if finding.get("eligible")
            and finding.get("category") == category
            and finding["result"] != "NOT_APPLICABLE"
        ]
        scores[category] = (
            0
            if "FAIL" in results
            else 1 if results and all(v == "PASS" for v in results) else None
        )
    scores["total_a"] = roll([scores[key] for key in groups.total_a])
    scores["total_b"] = roll([scores[key] for key in groups.total_b])
    scores["total"] = roll([scores["total_a"], scores["total_b"]])
    return scores
