"""Text bindings derived from the submitted profile schemas, not fixed names."""
from .identity import IdentityBinding, IdentityPolicy, validate_bindings, _resolve


def validate_text_binding(binding, profiles):
    validate_bindings(IdentityPolicy(bindings=(binding,)), profiles)
    root = profiles[binding.profile]["schema"]
    node = root
    for part in (binding.schema_path or binding.field_path).split("."):
        node = _resolve(node, root)
        if "present" in node.get("properties", {}):
            raise ValueError("Visual-region observations require a visual policy, not a text comparison.")
        node = node.get("properties", {})[part]


def text_field_options(payload, family):
    from app.document_families import families

    catalog = families(payload)
    if family not in catalog:
        raise ValueError("Unknown document family.")
    result = []

    def is_text(node):
        kind = node.get("type")
        kinds = set(kind if isinstance(kind, list) else [kind])
        return "string" in kinds and not kinds - {"string", "null"}

    for profile in catalog[family]["profiles"]:
        definition = payload["profiles"].get(profile, {})
        labels = dict(definition.get("columns", []))

        def walk(node, path, depth=0):
            if depth > 15 or not isinstance(node, dict):
                return
            properties = node.get("properties", {})
            if "present" in properties:
                return  # Signature/stamp/photo evidence is not a text value.
            wrapped = set(properties) == {"raw", "complete"} and is_text(properties["raw"])
            if path and (is_text(node) or wrapped):
                schema_path = path + ".raw" if wrapped else path
                binding = IdentityBinding(profile=profile, field_path=path, schema_path=schema_path)
                validate_text_binding(binding, payload["profiles"])
                result.append({"path": profile + "." + path,
                               "schema_path": profile + "." + schema_path,
                               "profile": profile, "profile_label": definition.get("label", profile),
                               "label": labels.get(path.split(".")[0], path)})
                return
            for key, child in properties.items():
                walk(child, path + "." + key if path else key, depth + 1)

        walk(definition.get("schema", {}), "")
    return result
