"""Bounded policies for configured visual, date and currency comparisons."""

import re
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PATH = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"


class BoundPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    left: str = Field(pattern=PATH, max_length=500)
    right: str = Field(pattern=PATH, max_length=500)


class VisualPolicy(BoundPolicy):
    type: Literal["visual"]
    check: Literal["presence", "consistency", "placement", "all_pages"]
    expected_pages: int | None = Field(default=None, ge=1, le=1000)

    @model_validator(mode="after")
    def meaningful_bindings(self):
        if (self.check == "consistency") == (self.left == self.right):
            raise ValueError(
                "Consistency needs two regions; other visual checks use the same source on both sides."
            )
        if self.expected_pages is not None and self.check != "all_pages":
            raise ValueError("Expected page count applies only to all-page marks.")
        return self


class DatePolicy(BoundPolicy):
    type: Literal["date"]
    relation: Literal["equal", "on_or_after"] = "equal"

    @model_validator(mode="after")
    def different_fields(self):
        if self.left == self.right:
            raise ValueError("A date field cannot verify itself.")
        return self


class MoneyPolicy(BoundPolicy):
    type: Literal["money"]
    left_currency: str = Field(pattern=PATH, max_length=500)
    right_currency: str = Field(pattern=PATH, max_length=500)
    decimal_separator: Literal[".", ","] = "."
    thousands_separator: Literal[".", ",", " "] | None = None

    @model_validator(mode="after")
    def separate_currency_and_value(self):
        if self.decimal_separator == self.thousands_separator:
            raise ValueError("Decimal and thousands separators must differ.")
        if (
            self.left == self.right
            or self.left == self.left_currency
            or self.right == self.right_currency
        ):
            raise ValueError("Choose distinct amount and currency fields.")
        return self


def paths(policy):
    result = [policy.left, policy.right]
    if isinstance(policy, MoneyPolicy):
        result += [policy.left_currency, policy.right_currency]
    return list(dict.fromkeys(result))


def read_value(documents, path):
    profile, *parts = path.split(".")
    matches = [
        d
        for d in documents
        if d.get("doc_type") == profile and d.get("status") == "COMPLETED"
    ]
    if len(matches) != 1:
        return None, "AMBIGUOUS_DOCUMENT" if matches else "MISSING_DOCUMENT"
    value = matches[0].get("normalized", {})
    for part in parts:
        value = value.get(part) if isinstance(value, dict) else None
    if isinstance(value, dict) and set(value) == {"raw", "complete"}:
        if value["complete"] is not True:
            return None, "INCOMPLETE_VALUE"
        value = value["raw"]
    return value, None


def evaluate_policy(policy, documents):
    values = {}
    for path in paths(policy):
        value, error = read_value(documents, path)
        if error:
            return "FAIL", error
        values[path] = value
    left, right = values[policy.left], values[policy.right]
    if isinstance(policy, VisualPolicy):
        if not isinstance(left, dict) or not isinstance(right, dict):
            return "REVIEW", "VISUAL_REVIEW_REQUIRED"
        if policy.check == "all_pages":
            count, pages = left.get("page_count"), left.get("pages")
            if (
                policy.expected_pages
                and type(count) is int
                and count != policy.expected_pages
            ):
                return "FAIL", "PAGE_COUNT_MISMATCH"
            if (
                type(count) is not int
                or count < 1
                or not isinstance(pages, list)
                or len(pages) != count
            ):
                return "REVIEW", "PAGE_COVERAGE_UNVERIFIED"
            if any(
                not isinstance(p, dict) or type(p.get("page_number")) is not int
                for p in pages
            ):
                return "REVIEW", "PAGE_COVERAGE_UNVERIFIED"
            if {p["page_number"] for p in pages} != set(range(1, count + 1)):
                return "REVIEW", "PAGE_COVERAGE_UNVERIFIED"
            flags = [
                p.get(k)
                for p in pages
                for k in ("footer_present", "non_text", "complete")
            ]
            grounded = all(
                isinstance(p.get("evidence"), str) and p["evidence"].strip()
                for p in pages
            )
        else:
            keys = ["present", "complete"] + (
                ["at_signer_region"] if policy.check == "placement" else []
            )
            regions = [left, right] if policy.check == "consistency" else [left]
            flags = [r.get(k) for r in regions for k in keys]
            grounded = all(
                type(r.get("page_number")) is int
                and r["page_number"] > 0
                and isinstance(r.get("evidence"), str)
                and r["evidence"].strip()
                for r in regions
            )
        if any(flag is False for flag in flags):
            return "FAIL", "VISUAL_REQUIREMENT_ABSENT"
        if (
            policy.check == "consistency"
            or not grounded
            or not all(flag is True for flag in flags)
        ):
            return "REVIEW", "VISUAL_REVIEW_REQUIRED"
        return "PASS", "VISUAL_REQUIREMENT_OBSERVED"
    if left in (None, "") or right in (None, ""):
        return "FAIL", "MISSING_VALUE"
    if isinstance(policy, DatePolicy):
        from validation import parse_date

        try:
            a, b = parse_date(left), parse_date(right)
            matched = a == b if policy.relation == "equal" else a >= b
        except (ValueError, TypeError, OverflowError):
            return "FAIL", "INVALID_DATE"
        return ("PASS", "DATES_MATCH") if matched else ("FAIL", "DATES_DIFFER")
    from .field_checks import evaluate_field

    amounts = []
    for value in (left, right):
        status, reason = evaluate_field(
            value,
            {
                "kind": "number",
                "decimal_separator": policy.decimal_separator,
                "thousands_separator": policy.thousands_separator,
            },
        )
        if status != "PASS":
            return "FAIL", reason
        if type(value) in {int, float}:
            amounts.append(Decimal(str(value)))
            continue
        text = str(value)
        if policy.thousands_separator:
            text = text.replace(policy.thousands_separator, "")
        amounts.append(Decimal(text.replace(policy.decimal_separator, ".")))
    import pycountry

    currencies = [values[policy.left_currency], values[policy.right_currency]]
    if any(
        not isinstance(v, str)
        or not re.fullmatch("[A-Z]{3}", v)
        or pycountry.currencies.get(alpha_3=v) is None
        for v in currencies
    ):
        return "FAIL", "INVALID_CURRENCY"
    if any(value <= 0 for value in amounts):
        return "FAIL", "NONPOSITIVE_AMOUNT"
    return (
        ("PASS", "AMOUNTS_MATCH")
        if amounts[0] == amounts[1] and currencies[0] == currencies[1]
        else ("FAIL", "AMOUNTS_DIFFER")
    )


def validate_visual_binding(profiles, path, policy):
    from .identity import _resolve

    profile, *parts = path.split(".")
    root = profiles.get(profile, {}).get("schema", {})
    node = root
    for part in parts:
        node = _resolve(node, root).get("properties", {}).get(part)
        if not isinstance(node, dict):
            raise ValueError("Visual policy must reference an existing region field.")
    node = _resolve(node, root)
    required = (
        {"pages", "page_count"}
        if policy.check == "all_pages"
        else {"present", "complete"}
    )
    if policy.check == "placement":
        required.add("at_signer_region")
    if not required <= set(node.get("properties", {})):
        raise ValueError(
            "Selected region does not supply the observations required by this visual check."
        )
    expected = (
        {"pages": "array", "page_count": "integer"}
        if policy.check == "all_pages"
        else {key: "boolean" for key in required}
    )
    for key, wanted in expected.items():
        kind = _resolve(node["properties"][key], root).get("type")
        types = set(kind if isinstance(kind, list) else [kind])
        if wanted not in types or types - {wanted, "null"}:
            raise ValueError(
                "Visual observations must use typed boolean, page-count and page-list properties."
            )
