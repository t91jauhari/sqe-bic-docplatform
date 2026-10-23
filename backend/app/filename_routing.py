"""Filename Routing operations."""

from app.native_profiles import GROUPING_PREFIXES, SOP_MESSAGE_TEMPLATES, SUFFIX_ALIASES
import re
from pathlib import Path


def route(filename, cfg):
    templates = cfg.get("sop_message_templates", {})
    stem = re.sub("^(?:\\(Compressed\\)\\s*)+", "", Path(filename).stem, flags=re.I)
    stem = re.sub("[\\[\\]()]", " ", stem).strip()
    prefixes = cfg.get("grouping_prefixes", GROUPING_PREFIXES)
    if prefixes:
        prefix_pattern = (
            "^(?:" + "|".join((re.escape(p) for p in prefixes)) + ")[_\\s.-]+"
        )
        stem = re.sub(prefix_pattern, "", stem, flags=re.I)
    stem = re.sub(
        "[_\\s.-]+(?:signed|unsigned|scanned|scan|ttd|final|copy)+(?=[_\\s.-]|$)",
        "",
        stem,
        flags=re.I,
    )
    labels = {
        "form riplay": "riplay",
        "riplay": "riplay",
        "form lld": "lld",
        "lld": "lld",
        "slip aplikasi transaksi": "application",
        "aplikasi transaksi": "application",
        "dokumen underlying": "invoice",
        "invoice": "invoice",
        "ektp": "ektp",
        "surat pernyataan pembelian valas": "unknown",
    }
    for name, profile in cfg["profiles"].items():
        for suffix in profile["suffixes"]:
            labels[suffix] = name
    for alias, canonical in cfg.get("suffix_aliases", SUFFIX_ALIASES).items():
        if canonical in labels:
            labels[alias] = labels[canonical]
    patterns = []
    for label, kind in sorted(labels.items(), key=lambda x: -len(x[0])):
        words = re.findall("[^\\W_]+", label, re.UNICODE)
        if words:
            patterns.append(("[_\\s.-]+".join((re.escape(w) for w in words)), kind))
    matched = []
    customer = stem
    for _ in range(3):
        found = False
        for pattern, kind in patterns:
            if re.fullmatch(pattern, customer, re.I):
                customer = ""
                matched.append(kind)
                found = True
                break
            prefix = re.match(pattern + "[_\\s.-]+(.+)$", customer, re.I)
            suffix = re.search("[_\\s.-]+" + pattern + "$", customer, re.I)
            if prefix:
                customer = prefix.group(1).strip(" _-")
            elif suffix:
                customer = customer[: suffix.start()].strip(" _-")
            else:
                continue
            matched.append(kind)
            found = True
            break
        if not found or not customer:
            break
    if not matched and customer:
        from difflib import SequenceMatcher

        (best_label, best_ratio) = (None, 0.0)
        for label, kind in labels.items():
            ratio = SequenceMatcher(None, customer.lower(), label).ratio()
            if ratio > best_ratio:
                (best_label, best_ratio) = (kind, ratio)
        if best_ratio >= 0.8:
            matched.append(best_label)
    customer = re.sub("[_\\s]+", " ", customer).strip(" -")
    customer = re.sub(
        "[\\s_-]+(?:form|formulir|dokumen|document|doc)$", "", customer, flags=re.I
    )
    customer = re.sub(
        "^(?:form|formulir|dokumen|document|doc)[\\s_-]+", "", customer, flags=re.I
    ).strip(" -")
    if not matched:
        return (
            "unknown",
            customer,
            {
                "method": "unassigned",
                "reason": templates.get(
                    "route.unassigned_reason",
                    SOP_MESSAGE_TEMPLATES["route.unassigned_reason"],
                ),
            },
        )
    hint = matched[0] if len(set(matched)) == 1 else "unknown"
    return (
        hint,
        customer,
        {
            "method": "filename",
            "reason": templates.get(
                "route.filename_reason", SOP_MESSAGE_TEMPLATES["route.filename_reason"]
            ),
            "confirmed": False,
        },
    )
