"""Generic, pure SOP comparison contracts; runtime activation remains separate."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ComparisonPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["compare"] = "compare"
    left: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", max_length=500)
    right: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", max_length=500)
    normalization: Literal["literal", "casefold_whitespace"] = "literal"
    pattern: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def distinct_fields(self):
        if self.left == self.right:
            raise ValueError("Choose two different fields; a field cannot verify itself.")
        return self

    @field_validator("pattern")
    @classmethod
    def supported_pattern(cls, value):
        # Limited declarative constraint, not administrator-supplied regex code.
        if value is not None and not re.fullmatch(r"\[0-9\]\{[1-9][0-9]?\}", value):
            raise ValueError("Only fixed digit-length patterns are supported.")
        return value


class ComparisonResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    result: Literal["PASS", "FAIL"]
    reason: Literal["equal", "different", "missing", "ambiguous", "invalid_format"]


def _read(documents, path):
    profile, *parts = path.split(".")
    matches = [doc for doc in documents if doc.get("doc_type") == profile and doc.get("status") == "COMPLETED"]
    if len(matches) != 1:
        return None, "ambiguous" if len(matches) > 1 else "missing"
    value = matches[0].get("normalized", {})
    for part in parts:
        value = value.get(part) if isinstance(value, dict) else None
    if value is None or not isinstance(value, str) or not value.strip():
        return None, "missing"
    return value, None


def evaluate_comparison(documents, policy: ComparisonPolicy) -> ComparisonResult:
    left, left_error = _read(documents, policy.left)
    right, right_error = _read(documents, policy.right)
    if left_error or right_error:
        return ComparisonResult(result="FAIL", reason=left_error or right_error)
    if policy.pattern and any(re.fullmatch(policy.pattern, value) is None for value in (left, right)):
        return ComparisonResult(result="FAIL", reason="invalid_format")
    if policy.normalization == "casefold_whitespace":
        left, right = (" ".join(value.split()).casefold() for value in (left, right))
    return ComparisonResult(result="PASS" if left == right else "FAIL", reason="equal" if left == right else "different")
