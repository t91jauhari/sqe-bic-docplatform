"""Sequential image extraction with lossless page results and conservative merging."""

from copy import deepcopy


def combine_pages(pages):
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
            return [deepcopy(item) for _, value in entries for item in value]
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
    merged["page_results"] = deepcopy(pages)
    return merged, conflicts


def extract_pages(doc, images, messages, options, key, heartbeat):
    from .spider_provider import completion, content_json
    from .provider import checkpoint

    pages, receipts = [], []
    count = len(images) // 2
    for number in range(1, count + 1):
        heartbeat()
        request = deepcopy(messages)
        request[1]["content"] = [
            request[1]["content"][0],
            {
                "type": "text",
                "text": f"This request contains only physical RIPLAY page {number} of {count}. Extract only this page; do not invent observations for unseen pages. Fields absent on this page are null. page_initials.pages must contain only this page's observation with page_number={number}; page_count={count}. Any signature/stamp page_number must refer to physical page {number}. The final system appends all page results; do not merge other pages or treat this page as a complete document.",
            },
        ] + images[(number - 1) * 2 : number * 2]
        output = completion(
            doc, f"extract_page_{number}", request, options, key, heartbeat
        )
        value = content_json(output)
        pages.append({"page_number": number, "result": value})
        receipts.append(
            {
                "page_number": number,
                "id": output.get("id"),
                "usage": output.get("usage"),
            }
        )
        checkpoint(
            doc.id,
            spider_riplay_progress={"completed_pages": number, "total_pages": count},
        )
    merged, conflicts = combine_pages(pages)
    return merged, receipts, conflicts
