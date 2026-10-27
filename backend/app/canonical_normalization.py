"""Canonical normalization for banking entity names, personal names, and text comparisons."""
import difflib
import re
import unicodedata

# Standard Salutations & Honorifics (Indonesian & International)
SALUTATIONS = {
    "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "miss",
    "bpk", "bpk.", "bapak", "ibu", "sdr", "sdr.", "saudara", "sdri", "sdri.",
    "dr", "dr.", "dra", "dra.", "ir", "ir.", "prof", "prof.",
    "tuan", "nyonya", "nona",
}

# Corporate Legal Entity Designations
CORP_SUFFIXES = {
    "ltd": "limited",
    "ltd.": "limited",
    "limited": "limited",
    "corp": "corporation",
    "corp.": "corporation",
    "corporation": "corporation",
    "inc": "incorporated",
    "inc.": "incorporated",
    "incorporated": "incorporated",
    "co": "company",
    "co.": "company",
    "company": "company",
    "llc": "llc",
    "llc.": "llc",
    "pt": "pt",
    "pt.": "pt",
    "p.t.": "pt",
    "cv": "cv",
    "cv.": "cv",
    "c.v.": "cv",
    "tbk": "tbk",
    "tbk.": "tbk",
    "sdn bhd": "sdn bhd",
    "sdn. bhd.": "sdn bhd",
    "bhd": "sdn bhd",
    "bhd.": "sdn bhd",
    "gmbh": "gmbh",
    "sa": "sa",
    "nv": "nv",
}


def clean_syntactic_text(val) -> str:
    """Layer 1: Syntactic Sanitization.
    - Unicode NFC normalization.
    - Collapses spaces and non-breaking spaces.
    - Strips leading and trailing punctuation (dots, commas, quotes, hyphens).
    - Removes isolated optical punctuation noise (e.g. 'langit . raharja' -> 'langit raharja').
    """
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        val = " ".join(str(x) for x in val)
    s = unicodedata.normalize("NFC", str(val)).casefold()
    # Normalize unicode whitespace
    s = re.sub(r"[\s\u00a0\u2000-\u200b]+", " ", s)
    # Strip noisy leading/trailing non-alphanumeric punctuation
    s = re.sub(r"^[^\w]+|[^\w]+$", "", s)
    # Remove isolated punctuation surrounded by spaces (optical scanner artifact)
    s = re.sub(r"\s+[^\w\s]+\s+", " ", s)
    # Strip any trailing punctuation that might remain before spaces
    s = re.sub(r"\s*[.,;:!?-]+\s*$", "", s)
    return s.strip()


def strip_salutations(text: str) -> str:
    """Layer 2a: Strip non-substantive personal salutations."""
    tokens = text.split()
    while tokens and tokens[0].rstrip(".").casefold() in {s.rstrip(".") for s in SALUTATIONS}:
        if len(tokens) > 1:
            tokens.pop(0)
        else:
            break
    return " ".join(tokens)


def canonicalize_entity(text: str) -> str:
    """Layer 2b: Harmonize corporate entity abbreviations and designations."""
    # Normalize acronym dots like P.T. -> PT, C.V. -> CV
    s = re.sub(r"\b([a-zA-Z])\.([a-zA-Z])\.", r"\1\2", text)
    tokens = s.split()
    canonical = []
    for t in tokens:
        clean_t = t.rstrip(".")
        if clean_t in CORP_SUFFIXES:
            canonical.append(CORP_SUFFIXES[clean_t])
        elif t in CORP_SUFFIXES:
            canonical.append(CORP_SUFFIXES[t])
        else:
            canonical.append(t)
    return " ".join(canonical)


def compact_token_string(text: str) -> str:
    """Strip all non-alphanumeric characters for compound spacing checks."""
    return re.sub(r"[^\w]", "", text)


def canonical_compare(a, b) -> tuple[bool, str, float]:
    """Evaluates two values through the 3-Tier Canonical Normalization Engine.
    Returns: (matched, method, similarity)
    """
    if a == b:
        return True, "identical_exact", 1.0

    # Layer 1: Syntactic Sanitization
    clean_a = clean_syntactic_text(a)
    clean_b = clean_syntactic_text(b)
    if not clean_a or not clean_b:
        return False, "empty_source", 0.0
    if clean_a == clean_b:
        return True, "syntactic_clean_match", 1.0

    # Layer 2a: Entity Harmonization
    entity_a = canonicalize_entity(clean_a)
    entity_b = canonicalize_entity(clean_b)
    if entity_a == entity_b:
        return True, "canonical_entity_match", 1.0

    # Layer 2b: Salutation Stripping
    sal_a = strip_salutations(clean_a)
    sal_b = strip_salutations(clean_b)
    if sal_a == sal_b:
        return True, "salutation_stripped_match", 1.0

    # Combined Entity + Salutation
    comb_a = strip_salutations(entity_a)
    comb_b = strip_salutations(entity_b)
    if comb_a == comb_b:
        return True, "canonical_combined_match", 1.0

    # Layer 2c: Compound Token Consolidation (e.g. 'sri pujianty' vs 'sri puji anty')
    comp_a = compact_token_string(comb_a)
    comp_b = compact_token_string(comb_b)
    if comp_a and comp_a == comp_b and len(comp_a) >= 4:
        return True, "compact_token_match", 1.0

    # Layer 3: Similarity Evaluation
    ratio = difflib.SequenceMatcher(None, clean_a, clean_b).ratio()
    return False, "differ", ratio
