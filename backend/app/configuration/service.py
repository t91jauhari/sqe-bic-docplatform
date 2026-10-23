"""Configuration operations independent of HTTP and session ownership."""
from .upgrade_comparisons import propose_upgrade, supported


class StaleConfiguration(ValueError):
    pass


def comparison_candidates(payload):
    import copy
    from app.document_families import families
    from app.transaction_flows import scope_configuration

    membership = {}
    for family in families(payload):
        probe = copy.deepcopy(payload)
        probe["templates"]["__preview_probe"] = {"label": "Preview probe", "document_family": family}
        membership[family] = {rule["id"] for rule in scope_configuration(probe, "__preview_probe")["sop_rules"]}
    return [{"id": rule["id"], "label": rule["label"], "left": rule["path"],
             "right": rule["other_path"], "families": [family for family, ids in membership.items() if rule["id"] in ids]}
            for rule in payload.get("sop_rules", []) if supported(rule)]


def preview_comparison_upgrade(*, current_version, expected_version, payload, selected_ids):
    if current_version != expected_version:
        raise StaleConfiguration("Configuration changed. Reload before previewing this upgrade.")
    if not selected_ids or len(selected_ids) != len(set(selected_ids)):
        raise ValueError("Select distinct comparison rules to preview.")
    return {**propose_upgrade(payload, selected_ids), "source_version": current_version}


def preview_compatibility_upgrade(*, current_version, expected_version, payload, selected_keys):
    from .compatibility import propose_compatibility

    if current_version != expected_version:
        raise StaleConfiguration("Configuration changed. Reload before previewing compatibility updates.")
    return {**propose_compatibility(payload, selected_keys), "source_version": current_version}
