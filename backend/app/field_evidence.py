"""Source crops for populated extraction leaves; no guessed coordinates or values."""

import hashlib
import json
import re
import fitz
from .evidence import rectangle, visual_fields
from .parse_evidence import parse_box, nodes
from .storage import original_key, object_key, store, fitz_open_original


def populated_fields(value, path="", include_empty=False):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.startswith("_") or key == "page_results":
                continue
            if key == "complete" and set(value) == {"raw", "complete"}:
                continue  # Completeness describes the value, not another source field.
            yield from populated_fields(
                child, f"{path}.{key}" if path else key, include_empty
            )
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from populated_fields(child, f"{path}.{i}", include_empty)
    elif (
        include_empty
        or value is not None
        and (not isinstance(value, str) or value.strip())
    ):
        yield path, value


def at_path(value, path):
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def same_text(a, b):
    return re.sub(r"\s+", " ", str(a)).strip() == re.sub(r"\s+", " ", str(b)).strip()


def citation_boxes(citations):
    boxes, errors = [], []
    if isinstance(citations, dict):
        citations = [citations]
    for i, cite in enumerate(citations or []):
        try:
            if not isinstance(cite, dict):
                raise ValueError("Invalid citation")
            dims = cite.get("page_dimensions") or {}
            page = dict(
                page_number=cite.get("page"),
                page_width=dims.get("width"),
                page_height=dims.get("height"),
            )
            if (
                not isinstance(page["page_number"], int)
                or isinstance(page["page_number"], bool)
                or page["page_number"] < 1
            ):
                raise ValueError("Citation page number unavailable")
            regions = cite.get("bounding_boxes") or []
            if not regions:
                raise ValueError("Citation has no source region")
            for j, region in enumerate(regions):
                box = parse_box([region], page, f"citation[{i}].bounding_boxes[{j}]")
                box.update(source="extract", link_review_required=False)
                boxes.append(box)
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
    return boxes, errors


def parse_candidates(value, parsed):
    if isinstance(value, bool):
        return []
    found = {}
    for section in ("forms", "items"):
        for page in (parsed.get(section) or {}).get("pages", []):
            for node, path in nodes(page, section):
                # Match a complete value, never a substring or a nearby label.
                texts = [node.get(k) for k in ("value", "text", "md")]
                if not any(
                    isinstance(t, (str, int, float))
                    and not isinstance(t, bool)
                    and same_text(t, value)
                    for t in texts
                ):
                    continue
                regions = node.get("value_items")
                if isinstance(regions, list) and regions:
                    region_boxes = [
                        b
                        for item in regions
                        if isinstance(item, dict)
                        for b in (item.get("bbox") or [])
                    ]
                else:
                    region_boxes = node.get("bbox")
                try:
                    box = parse_box(region_boxes, page, path)
                    key = (box["page_number"], tuple(box["bbox"]))
                    found[key] = box
                except (ValueError, TypeError):
                    continue
    return list(found.values())


def build_field_evidence(doc, response):
    from .spatial_grounding import normalize_response
    response = normalize_response(response)
    raw = response.get("extract_result") or {}
    metadata = response.get("extract_metadata") or {}
    field_meta = (metadata.get("field_metadata") or {}).get("document_metadata") or {}
    parse_key = response.get("parse_response_key") or doc.provider_state.get(
        "parse_response_key"
    )
    if metadata.get("provider") == "spider-ai":
        parse_key = None
    parsed = json.loads(store().read(parse_key)) if parse_key else {}
    manual = metadata.get("visual_evidence") or {}
    visual_roots = {name.split(".")[0] for name, _ in visual_fields(raw)}
    revision = hashlib.sha256(
        json.dumps(
            dict(
                source=doc.sha256,
                extraction=response.get("id"),
                metadata=metadata,
                parse=parse_key,
            ),
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()[:24]
    result, source = [], None
    try:
        entries = dict(populated_fields(raw))
        for path in metadata.get("spatial_evidence", {}):
            value = at_path(raw, path)
            if isinstance(value, dict) and set(value) == {"raw", "complete"}:
                # Providers can locate the wrapper instead of its raw leaf.
                # Use that location once, while retaining the business value.
                if value["raw"] is not None and value["raw"] != "":
                    entries.pop(f"{path}.raw", None)
                    entries[path] = value["raw"]
            elif isinstance(value, (dict,list)):
                entries[path] = value
        allowed = dict(populated_fields(raw, include_empty=True))
        entries.update({field: allowed[field] for field in manual if field in allowed})
        for field, value in entries.items():
            if field.split(".")[0] in visual_roots:
                continue  # existing visual evidence handles these observations
            item = dict(
                field=field,
                value=value,
                available=False,
                image_available=False,
                review_status="REVIEW",
                revision=revision,
                source_sha256=doc.sha256,
                extraction_id=response.get("id"),
                crops=[],
                parse_response_key=parse_key,
            )
            leaf = field_meta.get(field) or at_path(field_meta, field) or {}
            if not isinstance(leaf, dict):
                leaf = {}
            citations = leaf.get("citation") or []
            item["confidence"] = leaf.get("confidence")
            boxes, errors = citation_boxes(citations)
            if field in manual:
                boxes, errors = [manual[field]], []
            elif field in metadata.get("spatial_evidence", {}):
                boxes = metadata["spatial_evidence"][field]
                errors = metadata.get("spatial_errors", {}).get(field, [])
            elif field in metadata.get("spatial_errors", {}):
                boxes, errors = [], metadata["spatial_errors"][field]
            elif not boxes:
                candidates = parse_candidates(value, parsed)
                if len(candidates) == 1:
                    boxes = candidates
                elif candidates:
                    item["candidate_count"] = len(candidates)
                    errors.append(
                        "Value appears in multiple source regions; select the correct region."
                    )
            if not boxes:
                item["error"] = (
                    "; ".join(errors)
                    or "No localized source evidence returned; select a region for review."
                )
            for i, box in enumerate(boxes):
                try:
                    if source is None:
                        source = fitz_open_original(
                            store().read(original_key(doc))
                        )
                    page_number = box.get("page_number")
                    if (
                        isinstance(page_number, bool)
                        or not isinstance(page_number, int)
                        or not 1 <= page_number <= len(source)
                    ):
                        raise ValueError("Source page out of bounds")
                    page = source[page_number - 1]
                    clip = rectangle(box, page)
                    scale = min(2, 2000 / max(clip.width, clip.height))
                    data = page.get_pixmap(
                        matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False
                    ).tobytes("png")
                    image_id = hashlib.sha256(
                        f"field:{field}:{i}".encode()
                    ).hexdigest()[:16]
                    key = object_key(
                        doc.org,
                        doc.branch_id,
                        "evidence",
                        doc.id,
                        f"{revision}-{image_id}.png",
                    )
                    store().put(key, data, "image/png")
                    item["crops"].append(
                        dict(
                            available=True,
                            revision=revision,
                            storage_key=key,
                            page_number=page_number,
                            bbox=box,
                            image_sha256=hashlib.sha256(data).hexdigest(),
                        )
                    )
                except ValueError as exc:
                    errors.append(str(exc))
            available = bool(item["crops"])
            item.update(
                available=available,
                image_available=available,
                review_status="REVIEWED"
                if available and field in manual
                else "REVIEW"
                if errors or any(b.get("link_review_required") for b in boxes)
                else "PENDING"
                if available
                else "REVIEW",
            )
            if errors:
                item["error"] = "; ".join(errors)
            result.append(item)
    finally:
        if source is not None:
            source.close()
    return result


def evidence_images(validation):
    yield from validation.get("visual_evidence", [])
    for field in validation.get("field_evidence", []):
        if not field.get("crops"):
            yield {**field, "available": False}
        for crop in field.get("crops", []):
            yield {
                **crop,
                "field": field["field"],
                "review_status": field["review_status"],
            }


def attach_field_evidence(report, evidence):
    report["field_evidence"] = evidence
    visual = report.get("visual_evidence") or []
    for root, result in report.get("fields", {}).items():
        entries = [e for e in evidence if e["field"].split(".")[0] == root]
        if entries:
            result["cropped_evidence"] = entries
            result["image_available"] = all(e["image_available"] for e in entries)
        else:
            v_entries = [
                e
                for e in visual
                if isinstance(e, dict) and e.get("field", "").split(".")[0] == root
            ]
            if v_entries:
                result["image_available"] = all(
                    bool(e.get("available")) for e in v_entries
                )
    return report
