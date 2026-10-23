"""Deterministic, batch-local customer resolution; abbreviations never bridge people."""

import re
from difflib import SequenceMatcher
from .domain import route, SOP_MESSAGE_TEMPLATES
from .configuration.identity import expands, tokens


def plan_grouping(filenames, cfg, overrides=None):
    overrides = overrides or {}
    aliases = {tokens(k): v.strip() for k, v in cfg.get("customer_aliases", {}).items()}
    templates = cfg.get("sop_message_templates", {})
    rows = []
    for filename in filenames:
        hint, name, classification = route(filename, cfg)
        observed_name = name
        name = aliases.get(tokens(name), name).strip()
        explicit = filename in overrides
        if explicit:
            name = overrides[filename].strip()
        identity = tokens(name)
        # A document-type-only filename has no customer evidence.
        missing = (
            not identity
            or all(len(t) == 1 for t in identity)
            or any(t.isdigit() for t in identity)
            or (
                identity
                and identity[0] in {"scan", "scanned", "document", "file", "untitled"}
            )
        )
        rows.append(
            dict(
                filename=filename,
                hint=hint,
                original_customer=observed_name,
                candidate_name=name,
                classification=classification,
                identity=identity,
                explicit=explicit,
                missing=missing,
            )
        )
    names = {}
    for row in rows:
        if not row["missing"]:
            identity = row["identity"]
            current = names.get(identity)
            if current is None:
                names[identity] = row["candidate_name"]
                continue
            # Prefer a natural-cased display name over an ALL-CAPS variant
            # (EKTP filenames are often fully uppercased).
            better = (
                not row["candidate_name"].isupper()
                and (current.isupper() or row["candidate_name"].istitle())
            )
            if better:
                names[identity] = row["candidate_name"]
    # Keep distinct maximal names. Never take connected components: a short
    # name could otherwise join two incompatible full names transitively.
    anchors = [a for a in names if not any(a != b and expands(a, b) for b in names)]
    display = {a: names[a] for a in anchors}
    for anchor in anchors:
        compatible = [a for a in names if a != anchor and expands(a, anchor)]
        if compatible and sum(a[0] == anchor[0] for a in anchors) == 1:
            display[anchor] = re.split(
                r"\s+", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", names[anchor])
            )[0]

    def resembles(a, b):
        if a == b or min(len(" ".join(a)), len(" ".join(b))) < 5:
            return False
        return SequenceMatcher(None, " ".join(a), " ".join(b)).ratio() >= 0.90

    result = []
    for row in rows:
        matches = (
            [a for a in anchors if expands(row["identity"], a)]
            if not row["missing"]
            else []
        )
        suspected = [a for a in anchors if any(resembles(a, b) for b in matches)]
        if row["explicit"]:
            customer = row["candidate_name"]
            status, reason = "manual", templates.get(
                "grouping.manual_confirmed",
                SOP_MESSAGE_TEMPLATES["grouping.manual_confirmed"],
            )
            candidates = []
        elif len(matches) == 1 and not suspected:
            customer = display[matches[0]]
            status = "automatic"
            reason = (
                templates.get(
                    "grouping.one_compatible",
                    SOP_MESSAGE_TEMPLATES["grouping.one_compatible"],
                )
                if row["identity"] != matches[0]
                else templates.get(
                    "grouping.normalized_match",
                    SOP_MESSAGE_TEMPLATES["grouping.normalized_match"],
                )
            )
            candidates = []
        else:
            customer = ""
            status = "unresolved"
            reason = (
                templates.get(
                    "grouping.similar_spellings",
                    SOP_MESSAGE_TEMPLATES["grouping.similar_spellings"],
                )
                if suspected
                else (
                    templates.get(
                        "grouping.multiple_compatible",
                        SOP_MESSAGE_TEMPLATES["grouping.multiple_compatible"],
                    )
                    if matches
                    else templates.get(
                        "grouping.missing_name",
                        SOP_MESSAGE_TEMPLATES["grouping.missing_name"],
                    )
                )
            )
            candidates = [display[a] for a in sorted(set(matches + suspected))]
        result.append(
            dict(
                filename=row["filename"],
                hint=row["hint"],
                customer=customer,
                original_customer=row["original_customer"],
                status=status,
                candidates=candidates,
                explanation=reason,
                classification=row["classification"],
            )
        )
    return result


def identity_conflicts(documents, cfg=None):
    """Use explicit customer roles only; supplier, beneficiary and signer names are excluded."""
    templates = (cfg or {}).get("sop_message_templates", {})
    observed = []
    paths = {
        "ektp": ("name",),
        "account_opening_form": ("customer_name",),
        "join_visit": ("customer_name",),
        "edd": ("customer_name",),
        "signature_difference": ("customer_name",),
        "company_reference": ("customer_name",),
        "riplay": ("customer_name",),
        "application": ("remitter", "name"),
    }
    policy = None
    if cfg is not None and "identity_policy" in cfg:
        from .configuration.identity import IdentityPolicy, conflicting_pairs, validate_bindings

        policy = IdentityPolicy.model_validate(cfg["identity_policy"])
        validate_bindings(policy, cfg["profiles"])
        paths = {binding.profile: tuple(binding.field_path.split(".")) for binding in policy.bindings}
    for doc in documents:
        if doc.get("status") != "COMPLETED" or doc.get("doc_type") not in paths:
            continue
        value = doc.get("normalized", {})
        for key in paths[doc["doc_type"]]:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, str) and tokens(value):
            observed.append((doc["id"], value, tokens(value)))
    conflicts = [
        (a, b)
        for i, a in enumerate(observed)
        for b in observed[i + 1 :]
        if not expands(a[2], b[2]) and not expands(b[2], a[2])
    ]
    # Old pins retain the original mapping; explicit policies are authoritative.
    if policy is not None:
        conflicts = conflicting_pairs(observed, policy)
    if not conflicts:
        return []
    return [
        dict(
            rule_id="grouping.customer_identity_conflict",
            field="customer_grouping",
            result="REVIEW",
            eligible=False,
            message=templates.get(
                "grouping.identity_conflict",
                SOP_MESSAGE_TEMPLATES["grouping.identity_conflict"],
            ),
            actual=[{"document_id": d, "name": name} for d, name, _ in observed],
            expected=templates.get(
                "grouping.expected_compatible",
                SOP_MESSAGE_TEMPLATES["grouping.expected_compatible"],
            ),
            evidence={
                "document_ids": sorted({a[0] for pair in conflicts for a in pair})
            },
        )
    ]
