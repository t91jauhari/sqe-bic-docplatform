"""Explicit, missing-only draft additions from a versioned compatibility release."""
import copy
import json
from pathlib import Path

from .codec import fingerprint


def release_definition():
    return json.loads((Path(__file__).parents[1] / "config_data" / "compatibility_defaults_v1.json").read_text(encoding="utf-8-sig"))


def missing_settings(payload):
    release = release_definition()
    return {"release": release["release"], "additions": [
        {"key": key, "value": copy.deepcopy(value)}
        for key, value in release["defaults"].items() if key not in payload
    ]}


def propose_compatibility(payload, selected_keys):
    from app.domain import validate_config

    release = release_definition()
    if not selected_keys or len(selected_keys) != len(set(selected_keys)):
        raise ValueError("Select distinct compatibility settings.")
    if set(selected_keys) - set(release["defaults"]):
        raise ValueError("Unknown compatibility setting.")
    if any(key in payload for key in selected_keys):
        raise ValueError("Compatibility updates cannot replace existing settings.")
    draft = copy.deepcopy(payload)
    additions = []
    for key in selected_keys:
        value = copy.deepcopy(release["defaults"][key])
        draft[key] = value
        additions.append({"key": key, "value": copy.deepcopy(value)})
    validate_config(draft)
    return {"release": release["release"], "basis_sha256": fingerprint(payload),
            "additions": additions, "payload": draft, "activated": False}
