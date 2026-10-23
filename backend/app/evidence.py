"""Immutable visual crops from explicit provider boxes; never guess coordinates."""

import hashlib
import math
import json
import fitz
from .storage import original_key, object_key, store, fitz_open_original

VISUAL_WORDS = (
    "signature",
    "initial",
    "stamp",
    "photo",
    "portrait",
    "meterai",
    "approval",
)


def visual_fields(raw):
    for field, value in raw.items():
        observation = isinstance(value, dict) and bool(
            {"present", "footer_present", "signature_present"} & set(value)
        )
        pages = (
            isinstance(value, dict)
            and "page_count" in value
            and isinstance(value.get("pages"), list)
        )
        if observation or pages or any(word in field.lower() for word in VISUAL_WORDS):
            if pages or field == "page_initials" and isinstance(value, dict):
                for i, page in enumerate(value.get("pages", [])):
                    if isinstance(page, dict):
                        yield f"{field}.pages.{i}", page
            else:
                yield field, value


def rectangle(box, page):
    """Canonical bbox: {page_number, bbox:[x0,y0,x1,y1], units, origin}.
    Units must be normalized, points or pixels (with source dimensions).
    Coordinates are top-left in the displayed, rotation-aware original page.
    """
    if box.get("origin", "top_left") != "top_left":
        raise ValueError("Unsupported coordinate origin")
    coords = box.get("bbox")
    if not isinstance(coords, (list, tuple)) or len(coords) != 4:
        raise ValueError("Missing bbox")
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
        for v in coords
    ):
        raise ValueError("Invalid bbox")
    x0, y0, x1, y1 = coords
    if not (0 <= x0 < x1 and 0 <= y0 < y1):
        raise ValueError("Empty or reversed bbox")
    width, height = page.rect.width, page.rect.height
    units = box.get("units")
    if units == "normalized":
        if x1 > 1 or y1 > 1:
            raise ValueError("Out of bounds")
        coords = [x0 * width, y0 * height, x1 * width, y1 * height]
    elif units == "pixels":
        sw, sh = box.get("source_width"), box.get("source_height")
        if not sw or not sh or sw <= 0 or sh <= 0 or x1 > sw or y1 > sh:
            raise ValueError("Invalid source dimensions")
        coords = [x0 * width / sw, y0 * height / sh, x1 * width / sw, y1 * height / sh]
    elif units == "points":
        if x1 > width or y1 > height:
            raise ValueError("Out of bounds")
    else:
        raise ValueError("Explicit coordinate units required")
    return fitz.Rect(coords)


def build_evidence(doc, response):
    from .spatial_grounding import normalize_response

    response = normalize_response(response)
    raw = response["extract_result"]
    metadata = response.get("extract_metadata") or {}
    # Provider adapter contract: retain exact original metadata and map known
    # provider coordinates to visual_evidence. Unknown shapes remain REVIEW.
    boxes = {}
    for entry in raw.get("_visual_evidence", []):
        if isinstance(entry, dict) and isinstance(entry.get("field"), str):
            boxes[entry["field"]] = entry
    boxes.update(metadata.get("visual_evidence") or {})
    parse_key = response.get("parse_response_key") or getattr(
        doc, "provider_state", {}
    ).get("parse_response_key")
    if metadata.get("provider") == "spider-ai":
        parse_key = None
    parse_result = json.loads(store().read(parse_key)) if parse_key else None
    from .parse_evidence import link_parse_evidence

    linked, candidates = link_parse_evidence(raw, parse_result or {})
    for name, box in linked.items():
        boxes.setdefault(name, box)
    field_meta = (metadata.get("field_metadata") or {}).get("document_metadata") or {}
    revision = hashlib.sha256(
        (
            str(doc.sha256)
            + str(response.get("id"))
            + json.dumps(
                {"metadata": metadata, "parse_key": parse_key, "links": linked},
                sort_keys=True,
                default=str,
            )
        ).encode()
    ).hexdigest()[:24]
    result = []
    source = None
    try:
        for field, observation in visual_fields(raw):
            observed = (
                observation.get(
                    "present",
                    observation.get(
                        "footer_present", observation.get("signature_present")
                    ),
                )
                if isinstance(observation, dict)
                else observation if isinstance(observation, bool) else None
            )
            item = {
                "field": field,
                "observed_present": observed,
                "available": False,
                "review_status": "REVIEW",
                "source_sha256": doc.sha256,
                "extraction_id": response.get("id"),
                "revision": revision,
                "parse_response_key": parse_key,
                "parse_candidates": candidates.get(field, []),
            }
            try:
                spatial = metadata.get("spatial_evidence", {}).get(field, [])
                box = (
                    boxes.get(field)
                    or (spatial[0] if spatial else None)
                    or field_meta.get(field)
                    or {}
                )
                if not box and candidates.get(field):
                    raise ValueError(
                        "Parse field has no unique localized visual region; select its region for review"
                    )
                page_number = box.get("page_number")
                if (
                    isinstance(page_number, bool)
                    or not isinstance(page_number, int)
                    or page_number < 1
                ):
                    details = metadata.get("spatial_errors", {}).get(field)
                    raise ValueError(
                        "; ".join(details)
                        if details
                        else "Missing or invalid page number"
                    )
                expected = (
                    observation.get("page_number")
                    if isinstance(observation, dict)
                    else None
                )
                if expected is not None and expected != page_number:
                    raise ValueError("Box page does not match observation")
                if source is None:
                    source = fitz_open_original(store().read(original_key(doc)))
                if page_number > len(source):
                    raise ValueError("Page out of bounds")
                page = source[page_number - 1]
                clip = rectangle(box, page)
                # get_pixmap clips in the displayed rotation-aware page frame.
                scale = min(2, 2000 / max(clip.width, clip.height))
                data = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False
                ).tobytes("png")
                key = object_key(
                    doc.org,
                    doc.branch_id,
                    "evidence",
                    doc.id,
                    revision
                    + "-"
                    + hashlib.sha256(field.encode()).hexdigest()[:16]
                    + ".png",
                )
                store().put(key, data, "image/png")
                item.update(
                    available=True,
                    review_status=(
                        "REVIEW" if box.get("link_review_required") else "PENDING"
                    ),
                    link_review_required=bool(box.get("link_review_required")),
                    page_number=page_number,
                    bbox=box,
                    storage_key=key,
                    image_sha256=hashlib.sha256(data).hexdigest(),
                )
            except ValueError as exc:
                item["error"] = str(exc)
            result.append(item)
    finally:
        if source is not None:
            source.close()
    return result


def apply_evidence_review(report, evidence):
    report["visual_evidence"] = evidence
    for item in evidence:
        if not item["available"] or item.get("link_review_required"):
            root = item["field"].split(".")[0]
            field = report.get("fields", {}).get(root)
            if field and field.get("status") == "NOT_APPLICABLE":
                continue
            if field:
                field.setdefault("issues", []).append(
                    {
                        "code": (
                            "CROP_EVIDENCE_REQUIRED"
                            if not item["available"]
                            else "CROP_LINK_REVIEW_REQUIRED"
                        ),
                        "severity": "REVIEW",
                    }
                )
                if field.get("status") != "FAIL":
                    field["status"] = "REVIEW"
            if report.get("status") != "FAIL":
                report["status"] = "REVIEW"
    return report
