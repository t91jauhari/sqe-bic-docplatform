"""Generalized sequential image extraction with cross-page reference and conservative merging.

Phase 3 §3.5 — Generalizes the RIPLAY-only sequential extraction to all multi-page
document types and adds cross-page reference passing so the model receives extracted
values from prior pages as continuity context.
"""

import json
from copy import deepcopy


def page_specific_initials(page_number, items):
    """Keep only the current physical page's initial observation when a model
    echoes prior-page observations from cross-page reference context.
    """
    if not isinstance(items, list):
        return items
    matching = [
        item
        for item in items
        if isinstance(item, dict) and item.get("page_number") in (None, page_number)
    ]
    return matching if matching else items


def deduplicate_page_initials(pages_list):
    """Deduplicate page_initials.pages by 1-based page_number while preserving order."""
    if not isinstance(pages_list, list):
        return pages_list
    by_page = {}
    passthrough = []
    for item in pages_list:
        if isinstance(item, dict) and isinstance(item.get("page_number"), int) and not isinstance(item.get("page_number"), bool):
            by_page[item["page_number"]] = deepcopy(item)
        else:
            passthrough.append(deepcopy(item))
    if not by_page:
        return pages_list
    return [by_page[k] for k in sorted(by_page)] + passthrough


def combine_pages(pages):
    from .spatial_grounding import split_locations
    original_pages = deepcopy(pages)
    pages = [{**page, "result": split_locations(page["result"], page["page_number"])[0]} for page in pages]
    conflicts = []

    def combine(entries, path):
        entries = [
            (page, value)
            for page, value in entries
            if value is not None and value != ""
        ]
        if not entries:
            return None
        # A blank signing area on a different page does not negate a visible signature.
        if all(isinstance(value, dict) for _, value in entries):
            positive = [
                (page, value) for page, value in entries if value.get("present") is True
            ]
            if positive:
                entries = positive
            text = [
                (page, value)
                for page, value in entries
                if value.get("raw") not in (None, "")
            ]
            if text:
                entries = text
            keys = dict.fromkeys(key for _, value in entries for key in value)
            return {
                key: combine(
                    [(page, value.get(key)) for page, value in entries],
                    f"{path}.{key}".strip("."),
                )
                for key in keys
            }
        if all(isinstance(value, list) for _, value in entries):
            if path == "page_initials.pages":
                combined = [
                    deepcopy(item)
                    for page, value in entries
                    for item in page_specific_initials(page, value)
                ]
                return deduplicate_page_initials(combined)
            return [deepcopy(item) for _, value in entries for item in value]
        if path == "page_initials.page_count":
            return len(pages)
        first = entries[0][1]
        if all(type(value) is type(first) and value == first for _, value in entries):
            return deepcopy(first)
        conflicts.append(
            {
                "field": path,
                "page_values": [
                    {"page_number": page, "value": deepcopy(value)}
                    for page, value in entries
                ],
            }
        )
        return None

    keys = dict.fromkeys(
        key for page in pages for key in page["result"] if key != "page_results"
    )
    merged = {
        key: combine(
            [(page["page_number"], page["result"].get(key)) for page in pages], key
        )
        for key in keys
    }
    # page_count is source metadata, not an inferred observation from the model.
    if isinstance(merged.get("page_initials"), dict):
        merged["page_initials"]["page_count"] = len(pages)
        if isinstance(merged["page_initials"].get("pages"), list):
            merged["page_initials"]["pages"] = deduplicate_page_initials(
                merged["page_initials"]["pages"]
            )
    merged["page_results"] = original_pages
    return merged, conflicts


def prune_for_reference(value, max_chars=280):
    """Compact a page extraction for cross-page reference context.

    Drops nulls/empty strings recursively and truncates long strings so the
    accumulated reference injected into page-N prompts stays bounded instead
    of growing with the field catalog and page count.
    """
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        pruned = {
            key: prune_for_reference(child, max_chars)
            for key, child in value.items()
            if key
            not in {
                "box_2d",
                "_field_locations",
                "field_locations",
                "page_results",
                "page_initials",
            }
        }
        return {key: child for key, child in pruned.items() if child is not None} or None
    if isinstance(value, list):
        pruned = [prune_for_reference(item, max_chars) for item in value]
        return [item for item in pruned if item is not None] or None
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + "…"
    return value


def reference_text(previous_extractions, max_chars=6000):
    """Serialize prior-page extractions as bounded reference context."""
    pruned = [
        prune_for_reference({"page": page["page_number"], "result": page["result"]})
        for page in previous_extractions
    ]
    text = json.dumps(
        [item for item in pruned if item is not None], ensure_ascii=False
    )
    if len(text) > max_chars:
        text = text[:max_chars] + "…(truncated)"
    return text


def extract_pages(doc, images, messages, options, key, heartbeat, cfg=None):
    """Sequential per-page extraction with optional cross-page reference.

    Generalized from spider_riplay.extract_pages — works for any document schema.
    The only RIPLAY-specific part was the prompt text about page_initials.pages;
    that has been generalized to a schema-agnostic per-page instruction.
    """
    from .spider_provider import completion, content_json
    from .provider import checkpoint

    cfg = cfg or {}
    cross_page = cfg.get("cross_page_reference", True)

    pages, receipts = [], []
    count = len(images) // 2
    previous_extractions = []  # accumulate results from prior pages

    for number in range(1, count + 1):
        heartbeat()
        request = deepcopy(messages)
        page_instruction = (
            f"This request contains only physical page {number} of {count}. "
            f"Extract only this page; do not invent observations for unseen pages. "
            f"Fields absent on this page are null. "
            f"Any signature/stamp page_number must refer to physical page {number}. "
            f"For page_initials.pages (when in schema), return only one entry for physical page {number}. "
            f"Include _field_locations with page_number={number} and box_2d for every visible text and visual region (including signatures, stamps, meterai, photos, and footer initials) on this page. "
        )

        # Cross-page reference — provide extracted values from previous pages
        if previous_extractions and cross_page:
            page_instruction += (
                f"Previously extracted from pages 1-{number - 1}: "
                + reference_text(previous_extractions)
                + " Use this only as reference context for continuity "
                "(e.g., multi-page tables, continued sections). "
                "Do not duplicate values from previous pages unless they "
                "also appear on this page. Extract only what is visible on THIS page."
            )

        request[1]["content"] = [
            request[1]["content"][0],
            {"type": "text", "text": page_instruction},
        ] + images[(number - 1) * 2 : number * 2]
        from .field_detail_images import detail_images
        profile=cfg.get('profiles',{}).get(doc.doc_type,{})
        if profile:
            request[1]['content'].extend(detail_images(doc,list(profile.get('schema',{}).get('properties',{})),number,heartbeat,profile=profile,max_bytes=options.get('_detail_image_budget',180000)))

        output = completion(
            doc, f"extract_page_{number}", request, options, key, heartbeat
        )
        value = content_json(output)
        pages.append({"page_number": number, "result": value})
        previous_extractions.append(pages[-1])  # accumulate for next page

        receipts.append(
            {
                "page_number": number,
                "id": output.get("id"),
                "usage": output.get("usage"),
            }
        )
        checkpoint(
            doc.id,
            spider_extraction_progress={"completed_pages": number, "total_pages": count},
        )
    merged, conflicts = combine_pages(pages)
    return merged, receipts, conflicts
