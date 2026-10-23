"""Reviewed location retrieval; suggestions never become current-document evidence."""

import hashlib
import io
import json
from collections import defaultdict

import fitz
from PIL import Image
from sqlalchemy import select

from .db import LocationFeedback
from .schema_descriptions import contract
from .storage import original_key, store, fitz_open_original


def schema_hash(profile):
    return hashlib.sha256(
        json.dumps(contract(profile["schema"]), sort_keys=True).encode()
    ).hexdigest()


def layout_signature(doc):
    """Rotation-aware page geometry and coarse visual structure; no OCR values stored."""
    with fitz_open_original(store().read(original_key(doc))) as pdf:
        if not 1 <= len(pdf) <= 100:
            return None
        pages = []
        for page in pdf:
            pix = page.get_pixmap(
                matrix=fitz.Matrix(96 / page.rect.width, 96 / page.rect.width),
                alpha=False,
            )
            image = (
                Image.open(io.BytesIO(pix.tobytes("png"))).convert("L").resize((17, 16))
            )
            pixels = [image.getpixel((x, y)) for y in range(16) for x in range(17)]
            bits = 0
            for y in range(16):
                for x in range(16):
                    bits = (bits << 1) | int(
                        pixels[y * 17 + x] > pixels[y * 17 + x + 1] + 2
                    )
            if bits.bit_count() < 16:
                return None  # Blank/featureless pages cannot establish layout compatibility.
            pages.append(
                {
                    "aspect": round(page.rect.width / page.rect.height, 4),
                    "hash": f"{bits:064x}",
                }
            )
        return {"version": 1, "pages": pages}


def compatible(left, right):
    if (
        not left
        or not right
        or left.get("version") != right.get("version")
        or len(left["pages"]) != len(right["pages"])
    ):
        return False
    return all(
        abs(a["aspect"] - b["aspect"]) <= 0.005
        and (int(a["hash"], 16) ^ int(b["hash"], 16)).bit_count() <= 6
        for a, b in zip(left["pages"], right["pages"])
    )


def overlap(a, b):
    area = lambda r: max(0, r[2] - r[0]) * max(0, r[3] - r[1])
    intersection = area(
        [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]
    )
    return intersection / (area(a) + area(b) - intersection) if intersection else 0


def record_feedback(db, doc, profile, data, user):
    try:
        layout = layout_signature(doc)
    except (ValueError, RuntimeError):
        layout = None
    # Keep an immutable correction history; only the newest region for this document/field is active.
    for old in db.scalars(
        select(LocationFeedback).where(
            LocationFeedback.org == doc.org,
            LocationFeedback.document_id == doc.id,
            LocationFeedback.field == data.field,
            LocationFeedback.enabled.is_(True),
        )
    ):
        old.enabled = False
    item = LocationFeedback(
        org=doc.org,
        branch_id=doc.branch_id,
        document_id=doc.id,
        document_type=doc.doc_type,
        field=data.field,
        schema_hash=schema_hash(profile),
        source_sha256=doc.sha256,
        page_number=data.page_number,
        bbox=data.bbox,
        layout=layout or {},
        reviewer_id=user.id,
        reason=data.reason,
        enabled=data.learn_for_future,
    )
    db.add(item)
    db.flush()
    return item


def retrieve(db, doc, profile):
    try:
        layout = layout_signature(doc)
    except (ValueError, RuntimeError):
        return []
    if not layout:
        return []
    candidates = db.scalars(
        select(LocationFeedback)
        .where(
            LocationFeedback.org == doc.org,
            LocationFeedback.branch_id == doc.branch_id,
            LocationFeedback.document_type == doc.doc_type,
            LocationFeedback.schema_hash == schema_hash(profile),
            LocationFeedback.enabled.is_(True),
            LocationFeedback.document_id != doc.id,
        )
        .order_by(LocationFeedback.created_at.desc(), LocationFeedback.id)
        .limit(500)
    ).all()
    grouped = defaultdict(list)
    for item in candidates:
        if compatible(layout, item.layout):
            grouped[item.field].append(item)
    result = []
    for field, items in sorted(grouped.items()):
        best = items[0]
        if any(
            item.page_number != best.page_number or overlap(item.bbox, best.bbox) < 0.8
            for item in items[1:]
        ):
            continue  # Contradictory examples require reviewer resolution, never majority guessing.
        result.append(
            {
                "field": field,
                "page_number": best.page_number,
                "bbox": best.bbox,
                "units": "normalized",
                "sample_ids": [i.id for i in items[:20]],
                "status": "GUIDANCE_ONLY",
            }
        )
    return result[:100]


def prompt(hints):
    if not hints:
        return ""
    regions = [
        {k: h[k] for k in ("field", "page_number", "bbox", "units")} for h in hints
    ]
    return (
        "\n\nReviewed location guidance from similar forms (provisional, not evidence): "
        + json.dumps(regions, separators=(",", ":"))
        + ". Coordinates use the displayed physical page, top-left origin, normalized 0–1. Inspect these regions and their adjacent labels first, but verify the current form layout and field role. Search the full page and continuation pages if the suggested area is blank, shifted or inconsistent. Never copy earlier values, manufacture citations, declare presence or authenticity, or fill a blank field from this guidance. Return current-document observations only."
    )
