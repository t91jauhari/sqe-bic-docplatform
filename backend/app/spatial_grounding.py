"""Translate explicit model locations to immutable source-page evidence."""

from .configuration.seed_catalog import seed_value
from copy import deepcopy
import math

SPATIAL_INSTRUCTION = seed_value("spatial_grounding.SPATIAL_INSTRUCTION")


def append_instruction(text):
    text = (text or "").rstrip()
    return text if SPATIAL_INSTRUCTION in text else text + "\n\n" + SPATIAL_INSTRUCTION


def spatial_schema(schema):
    schema = deepcopy(schema)
    schema.setdefault("properties", {})["_field_locations"] = {
        "type": "array",
        "description": "Explicit source locations for extracted fields; not business data.",
        "items": {
            "type": "object",
            "properties": {
                "field": {"type": "string"},
                "page_number": {"type": "integer"},
                "box_2d": {"type": "array", "items": {"type": "number"}},
            },
            "required": ["field", "page_number", "box_2d"],
            "additionalProperties": False,
        },
    }
    return schema


def box_location(entry, default_page=None):
    coords = entry.get("box_2d")
    if not isinstance(coords, list) or len(coords) != 4:
        raise ValueError("box_2d must contain four coordinates")
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
        for v in coords
    ):
        raise ValueError("box_2d coordinates must be finite numbers")
    y0, x0, y1, x1 = coords
    if not (0 <= x0 < x1 <= 1000 and 0 <= y0 < y1 <= 1000):
        raise ValueError("box_2d is empty, reversed or outside 0–1000")
    page = entry.get("page_number", default_page)
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("A 1-based original physical page number is required")
    if default_page is not None and page != default_page:
        raise ValueError("Box page does not match the physical extraction page")
    return {
        "page_number": page,
        "bbox": [x0 / 1000, y0 / 1000, x1 / 1000, y1 / 1000],
        "units": "normalized",
        "origin": "top_left",
        "box_2d": list(coords),
        "source": "model_box_2d",
        "link_review_required": False,
    }


def split_locations(raw, page_number=None):
    """Accept the sidecar plus inline visual boxes and value/box wrappers."""
    locations, errors = {}, {}

    def add(path, entry):
        if entry.get("box_2d") in (None, []):
            return
        try:
            box = box_location(entry, page_number)
            locations.setdefault(path, [])
            if box not in locations[path]:
                locations[path].append(box)
        except (ValueError, TypeError) as exc:
            errors.setdefault(path, []).append(str(exc))

    def walk(value, path=""):
        if isinstance(value, dict):
            if "box_2d" in value and path:
                add(path, value)
            wrapper = (
                "value" in value
                and "box_2d" in value
                and set(value) <= {"value", "box_2d", "page_number"}
            )
            if wrapper:
                return walk(value["value"], path)
            return {
                k: walk(v, f"{path}.{k}".strip("."))
                for k, v in value.items()
                if k not in {"box_2d", "_field_locations", "field_locations"}
            }
        if isinstance(value, list):
            return [walk(v, f"{path}.{i}".strip(".")) for i, v in enumerate(value)]
        return deepcopy(value)

    clean = walk(raw)
    sidecar = (
        raw.get("_field_locations", raw.get("field_locations", []))
        if isinstance(raw, dict)
        else []
    )
    if isinstance(sidecar, dict):
        sidecar = [
            dict(value, field=field)
            for field, value in sidecar.items()
            if isinstance(value, dict)
        ]
    for entry in sidecar if isinstance(sidecar, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("field"), str):
            add(entry["field"], entry)
    return clean, locations, errors


def _at(value, path):
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def _canonical_visual_target(field, visual_map):
    for vp in visual_map:
        if field == vp or field.startswith(f"{vp}."):
            return vp
    return None


def _visual_observed_absent(obs):
    if obs is None or obs is False:
        return True
    if isinstance(obs, dict):
        present = obs.get(
            "present", obs.get("footer_present", obs.get("signature_present"))
        )
        if present is False:
            return True
    return False


def normalize_response(response):
    """Idempotent transport conversion. Cached responses retain their metadata."""
    from .evidence import visual_fields
    from .spider_extraction import deduplicate_page_initials, page_specific_initials

    raw = response.get("extract_result") or {}
    pages = raw.get("page_results") if isinstance(raw, dict) else None
    clean, locations, errors = split_locations(raw)
    if (
        isinstance(clean, dict)
        and isinstance(clean.get("page_initials"), dict)
        and isinstance(clean["page_initials"].get("pages"), list)
    ):
        clean["page_initials"]["pages"] = deduplicate_page_initials(
            clean["page_initials"]["pages"]
        )
        if pages:
            clean["page_initials"]["page_count"] = len(pages)
    if pages:
        # Page results retain annotations until after conservative value merging.
        locations, errors, offsets = {}, {}, {}
        for page in pages:
            value, found, invalid = split_locations(page["result"], page["page_number"])
            if (
                isinstance(value, dict)
                and isinstance(value.get("page_initials"), dict)
                and isinstance(value["page_initials"].get("pages"), list)
            ):
                value["page_initials"]["pages"] = page_specific_initials(
                    page["page_number"], value["page_initials"]["pages"]
                )

            def remap(path):
                parts, original = path.split("."), []
                for i, part in enumerate(parts):
                    prefix = ".".join(original)
                    original.append(part)
                    if part.isdigit() and prefix in offsets:
                        parts[i] = str(int(part) + offsets[prefix])
                return ".".join(parts)

            for field, boxes in found.items():
                target = remap(field)
                # Never attach a crop from a rejected/conflicting page value.
                if _at(clean, target) == _at(value, field):
                    locations.setdefault(target, []).extend(boxes)
            for field, messages in invalid.items():
                errors.setdefault(remap(field), []).extend(messages)

            def count_arrays(item, path=""):
                if isinstance(item, dict):
                    for key, child in item.items():
                        count_arrays(child, f"{path}.{key}".strip("."))
                elif isinstance(item, list):
                    offsets[path] = offsets.get(path, 0) + len(item)

            count_arrays(value)
        clean["page_results"] = deepcopy(
            pages
        )  # Keep immutable per-page provider observations for replay.
    visual_map = dict(visual_fields(clean)) if isinstance(clean, dict) else {}
    metadata = deepcopy(response.get("extract_metadata") or {})
    existing = metadata.get("spatial_evidence", {})
    for field, boxes in locations.items():
        vp = _canonical_visual_target(field, visual_map)
        if vp is not None:
            if _visual_observed_absent(visual_map[vp]):
                continue
            bucket = existing.setdefault(vp, [])
            for box in boxes:
                if box not in bucket:
                    bucket.append(box)
        value = _at(clean, field)
        if (
            value is None
            or value == ""
            or isinstance(value, dict)
            and value.get("present") is False
        ):
            continue
        if vp is not None and _visual_observed_absent(visual_map[vp]):
            continue
        existing[field] = boxes
    for field, boxes in list(existing.items()):
        vp = _canonical_visual_target(field, visual_map)
        if (
            vp is not None
            and field != vp
            and not _visual_observed_absent(visual_map[vp])
        ):
            bucket = existing.setdefault(vp, [])
            for box in boxes if isinstance(boxes, list) else []:
                if box not in bucket:
                    bucket.append(box)
    merged_errors = {**metadata.get("spatial_errors", {}), **errors}
    for field, messages in list(merged_errors.items()):
        vp = _canonical_visual_target(field, visual_map)
        if vp is not None and field != vp and messages:
            bucket = merged_errors.setdefault(vp, [])
            for msg in messages:
                if msg not in bucket:
                    bucket.append(msg)
    metadata["spatial_evidence"] = existing
    metadata["spatial_errors"] = merged_errors
    metadata["spatial_grounding_version"] = 1
    return {**response, "extract_result": clean, "extract_metadata": metadata}
