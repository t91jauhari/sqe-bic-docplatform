"""Typed identity bindings and pure evaluation, independent of persistence/API."""
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IdentityBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile: str = Field(min_length=1, max_length=80)
    field_path: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$", max_length=500)
    # Extraction schemas may wrap text, while normalized results expose a scalar.
    schema_path: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$", max_length=500)
    role: Literal["customer"] = "customer"


class IdentityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    bindings: tuple[IdentityBinding, ...] = Field(max_length=100)
    comparison: Literal["exact_tokens", "compatible_initials"] = "compatible_initials"

    @model_validator(mode="after")
    def unique_profiles(self):
        if len({binding.profile for binding in self.bindings}) != len(self.bindings):
            raise ValueError("Configure one customer identity binding per profile.")
        for binding in self.bindings:
            if binding.schema_path and not (
                binding.schema_path == binding.field_path
                or binding.schema_path.startswith(binding.field_path + ".")
            ):
                raise ValueError("Schema path must identify the same field or its wrapped value.")
        return self


def tokens(value):
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value).casefold()
    return tuple(re.findall(r"[^\W_]+", value, re.UNICODE))


def expands(short, full):
    if not short or len(short) > len(full):
        return False
    if not any(a == b and len(a) > 1 for a, b in zip(short, full)):
        return False
    return all(a == b or (len(a) == 1 and b.startswith(a)) for a, b in zip(short, full))


def _resolve(node, root):
    seen = set()
    while "$ref" in node:
        reference = node["$ref"]
        if not reference.startswith("#/") or reference in seen:
            raise ValueError("Identity schema requires noncyclic local references.")
        seen.add(reference)
        target = root
        for part in reference[2:].split("/"):
            target = target.get(part.replace("~1", "/").replace("~0", "~"))
            if not isinstance(target, dict):
                raise ValueError("Identity field has an unresolved schema reference.")
        node = target
    return node


def validate_bindings(policy: IdentityPolicy, profiles: dict) -> None:
    for binding in policy.bindings:
        if binding.profile not in profiles:
            raise ValueError(f"Unknown identity profile: {binding.profile}")
        root = profiles[binding.profile].get("schema", {})
        node = root
        for part in (binding.schema_path or binding.field_path).split("."):
            node = _resolve(node, root).get("properties", {}).get(part)
            if not isinstance(node, dict):
                raise ValueError(f"Unknown identity field: {binding.profile}.{binding.field_path}")
        node = _resolve(node, root)
        variants = node.get("anyOf", [node])
        types = set()
        for variant in variants:
            kind = _resolve(variant, root).get("type")
            types.update(kind if isinstance(kind, list) else [kind])
        if "string" not in types or types - {"string", "null"}:
            raise ValueError("Customer identity fields must be string or nullable string.")


def observe_identities(documents, policy: IdentityPolicy):
    paths = {binding.profile: binding.field_path.split(".") for binding in policy.bindings}
    observed = []
    for document in documents:
        if document.get("status") != "COMPLETED" or document.get("doc_type") not in paths:
            continue
        value = document.get("normalized", {})
        for part in paths[document["doc_type"]]:
            value = value.get(part) if isinstance(value, dict) else None
        if isinstance(value, str) and tokens(value):
            observed.append((document["id"], value, tokens(value)))
    return observed


def conflicting_pairs(observed, policy: IdentityPolicy):
    def compatible(left, right):
        if policy.comparison == "exact_tokens":
            return left == right
        return expands(left, right) or expands(right, left)

    return [(left, right) for index, left in enumerate(observed)
            for right in observed[index + 1:] if not compatible(left[2], right[2])]
