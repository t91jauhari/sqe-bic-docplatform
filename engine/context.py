"""Auditable text correction and local-checkbox evidence reconciliation.

This module operates on extracted observations. It is not an independent image
detector and cannot verify a model's visual observations against the PDF pixels.
"""
import re
import unicodedata


def identity(text):
    if not isinstance(text, str):
        return ""
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).upper()))


def checkbox_identity(text):
    """Keep relation operators distinct while normalizing option labels."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("!=", " NOT_EQUAL ").replace("≠", " NOT_EQUAL ").replace("=", " EQUAL ")
    return identity(text)


def check_directory(directory):
    for bucket in ["bank_names", "branch_names", "bank_branch_names"]:
        entries = directory.get(bucket, [])
        if not isinstance(entries, list):
            raise ValueError(f"Directory {bucket} must be a list")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not any(c.isalpha() for c in entry["name"]):
                raise ValueError(f"Directory {bucket}: every canonical name must contain letters")
            if not isinstance(entry.get("aliases", []), list):
                raise ValueError(f"Directory {bucket}: aliases must be a list")
            for alias in entry.get("aliases", []):
                if not isinstance(alias, str) or not any(c.isalpha() for c in alias):
                    raise ValueError(f"Directory {bucket}: aliases must be text containing letters")
            prefixes = entry.get("bic_prefixes", [])
            if not isinstance(prefixes, list) or any(not isinstance(p, str) or not re.fullmatch(r"[A-Z0-9]{6,8}", p) for p in prefixes):
                raise ValueError(f"Directory {bucket}: bic_prefixes must contain verified 6-8 character uppercase prefixes")


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j-1] + 1, previous[j-1] + (ca != cb)))
        previous = current
    return previous[-1]


def correct_name(value, directory, bucket, policy, swift=None, bank_context=None):
    """Only approved exact aliases can change a value; fuzzy matches are suggestions."""
    result = {"value": value, "applied": False, "method": None, "candidates": [], "issues": []}
    if not isinstance(value, str) or not identity(value) or not policy.get("context_corrections_enabled", True):
        return result
    target = identity(value)
    entries = directory.get(bucket, [])
    entries = [e for e in entries if not e.get("bank_name") or identity(e["bank_name"]) == identity(bank_context)]
    matched = [e for e in entries if target in {identity(e["name"]), *(identity(x) for x in e.get("aliases", []))}]
    unique = {e["name"] for e in matched}
    if len(unique) > 1:
        result.update(candidates=sorted(unique), issues=["CORRECTION_DIRECTORY_CONFLICT"])
        return result
    if len(unique) == 1:
        entry = matched[0]
        # A verified contradictory BIC can block an alias; never invent a BIC.
        if swift and re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?", swift):
            observed_banks = {e["name"] for e in entries if any(swift.startswith(p) for p in e.get("bic_prefixes", []))}
            prefixes = entry.get("bic_prefixes", [])
            if (observed_banks and entry["name"] not in observed_banks) or (prefixes and not any(swift.startswith(p) for p in prefixes)):
                result.update(candidates=[entry["name"]], issues=["CORRECTION_CONFLICTS_WITH_VERIFIED_BIC"])
                return result
        if target != identity(entry["name"]):
            if policy.get("apply_approved_aliases", True):
                result.update(value=entry["name"], applied=True, method="approved_alias", candidates=[entry["name"]])
            else:
                result.update(method="approved_alias_suggestion", candidates=[entry["name"]], issues=["BANK_NAME_CORRECTION_SUGGESTED"])
        return result
    # Single-edit, same-token-count suggestions constrain matching to a narrow
    # candidate set. Edit distance is not a calibrated probability/confidence.
    max_edits = int(policy.get("bank_name_suggestion_max_edits", 1))
    if len(target) >= 6:
        near = {e["name"] for e in entries if len(target.split()) == len(identity(e["name"]).split())
                and edit_distance(target, identity(e["name"])) <= max_edits}
        if near:
            result.update(method="edit_distance_suggestion", candidates=sorted(near), issues=["BANK_NAME_CORRECTION_SUGGESTED"])
    return result


def resolve_checkbox(group, policy):
    """Decide from per-option observations, not stroke length or label overlap."""
    result = {"selected": group.get("selected"), "source": "legacy_selected",
              "issues": [], "reconciled": False, "options": group.get("options")}
    options = group.get("options")
    if not options or group.get("options_complete") is not True:
        result["issues"] = ["CHECKBOX_LOCAL_EVIDENCE_UNAVAILABLE_OR_INCOMPLETE"]
        # Legacy values may be displayed but cannot receive a clean PASS.
        return result
    accepted = set(policy.get("accepted_checkbox_mark_types", ["tick", "cross", "fill"]))
    selected, seen = [], set()
    uncertain = False
    for option in options:
        label, state = option.get("label"), option.get("state")
        local, tail, kind = option.get("local_mark_present"), option.get("tail_overlap_only"), option.get("mark_type")
        if not isinstance(label, str) or not label.strip() or checkbox_identity(label) in seen:
            uncertain = True
            continue
        seen.add(checkbox_identity(label))
        if not isinstance(option.get("evidence"), str) or not option["evidence"].strip():
            uncertain = True
        if tail is True and local is False and state in {"selected", "unselected"} and kind in {"none", "strike_through"}:
            # Only a tail crosses this option; it has no independently anchored mark.
            continue
        if state == "selected" and local is True and tail is False and kind in accepted:
            selected.append(label)
        elif state == "unselected" and local is False and tail is False and kind == "none":
            continue
        else:
            uncertain = True
    result["source"] = "local_checkbox_evidence"
    if uncertain:
        result.update(selected=None, issues=["CHECKBOX_LOCAL_MARK_AMBIGUOUS_OR_CONFLICTING"])
        return result
    result["selected"] = selected
    aliases = policy.get("enum_aliases", {})
    def comparable(values):
        if values is None:
            return None
        return sorted(checkbox_identity(aliases.get(x.strip().casefold(), x)) for x in values)
    result["reconciled"] = comparable(selected) != comparable(group.get("selected"))
    if result["reconciled"]:
        result["issues"].append("CHECKBOX_SELECTION_RECONCILED_FROM_LOCAL_MARKS")
    return result
