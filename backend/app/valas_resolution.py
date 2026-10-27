"""Dynamic Valas 1 vs Valas 2 resolution for SOP checks and path extraction."""

VALAS_SHARED_FIELDS = {
    "customer_name",
    "customer_address",
    "creation_place",
    "creation_date",
    "signatory",
    "signatory_company",
    "stamp_duty",
    "signatory_signature",
}

VALAS1_ONLY_FIELDS = {
    "identity_number",
    "npwp",
    "usage_purpose",
    "usage_date",
    "usage_amount",
    "receipt_source",
    "receipt_date",
    "receipt_amount",
}

VALAS2_ONLY_FIELDS = {
    "currency",
    "stamp_verification",
}

VALAS_PREFIXES = {
    "valas",
    "valas_declaration",
    "valas_declaration_1",
    "valas_declaration_2",
}


def _get_doc_attr(doc, attr):
    if isinstance(doc, dict):
        return doc.get(attr)
    return getattr(doc, attr, None)


def get_case_valas_document(documents, context=None):
    """Determine the active Valas declaration document from the case.
    Returns (document, doc_type) or (None, None).
    """
    completed = [
        d for d in documents
        if _get_doc_attr(d, "status") == "COMPLETED"
    ]
    valas_docs = [
        d for d in completed
        if _get_doc_attr(d, "doc_type") in {"valas_declaration_1", "valas_declaration_2"}
    ]

    if not valas_docs:
        return None, None

    # Check explicit context selection
    selected_id = (context or {}).get("declaration_document_id") if isinstance(context, dict) else None
    if selected_id:
        for d in valas_docs:
            if _get_doc_attr(d, "id") == selected_id:
                return d, _get_doc_attr(d, "doc_type")

    # Check threshold context
    threshold = (context or {}).get("threshold_state") if isinstance(context, dict) else None
    if threshold == "ABOVE":
        v1 = [d for d in valas_docs if _get_doc_attr(d, "doc_type") == "valas_declaration_1"]
        if v1:
            return v1[0], "valas_declaration_1"
    elif threshold == "WITHIN":
        v2 = [d for d in valas_docs if _get_doc_attr(d, "doc_type") == "valas_declaration_2"]
        if v2:
            return v2[0], "valas_declaration_2"

    if len(valas_docs) == 1:
        return valas_docs[0], _get_doc_attr(valas_docs[0], "doc_type")

    # If both are present and no context differentiator, prefer valas_declaration_1
    v1 = [d for d in valas_docs if _get_doc_attr(d, "doc_type") == "valas_declaration_1"]
    if v1:
        return v1[0], "valas_declaration_1"
    return valas_docs[0], _get_doc_attr(valas_docs[0], "doc_type")


def is_valas_prefix(prefix):
    return prefix in VALAS_PREFIXES


def is_field_applicable_to_valas(field_root, valas_doc_type):
    """Check if a field root is applicable to valas_declaration_1 or valas_declaration_2."""
    if field_root in VALAS_SHARED_FIELDS:
        return True
    if valas_doc_type == "valas_declaration_1":
        return field_root in VALAS1_ONLY_FIELDS or field_root == "currency"
    if valas_doc_type == "valas_declaration_2":
        return field_root in VALAS2_ONLY_FIELDS
    return False


def resolve_valas_path(path, active_valas_type, context=None):
    """Dynamically remap rule path based on the active Valas document in the case.

    Returns (remapped_path, is_applicable, explanation).
    """
    parts = path.split(".", 1)
    prefix = parts[0]
    subpath = parts[1] if len(parts) > 1 else ""
    field_root = subpath.split(".")[0] if subpath else ""

    if prefix not in VALAS_PREFIXES:
        return path, True, None

    if not active_valas_type:
        # No valas doc found
        return path, False, "No completed Valas declaration found in case."

    # Generic "valas" or "valas_declaration"
    if prefix in {"valas", "valas_declaration"}:
        if field_root == "currency" and active_valas_type == "valas_declaration_1":
            return "valas_declaration_1.usage_amount.currency", True, None
        if is_field_applicable_to_valas(field_root, active_valas_type):
            return f"{active_valas_type}.{subpath}", True, None
        return path, False, f"{active_valas_type} does not contain field '{field_root}'."

    # Rule targeted valas_declaration_1
    if prefix == "valas_declaration_1":
        if active_valas_type == "valas_declaration_1":
            return path, True, None
        # Active is valas_declaration_2
        if field_root in VALAS_SHARED_FIELDS:
            return f"valas_declaration_2.{subpath}", True, None
        if field_root in VALAS1_ONLY_FIELDS:
            threshold = (context or {}).get("threshold_state") if isinstance(context, dict) else None
            if threshold == "ABOVE":
                return path, False, "Above-threshold context requires Valas 1; Valas 2 cannot substitute for its missing fields."
            return path, False, "Valas 2 is the applicable uploaded declaration; this Valas 1-only field is not on that form."
        return path, False, f"Field '{field_root}' is not present on {active_valas_type}."

    # Rule targeted valas_declaration_2
    if prefix == "valas_declaration_2":
        if active_valas_type == "valas_declaration_2":
            return path, True, None
        # Active is valas_declaration_1
        if field_root in VALAS_SHARED_FIELDS:
            return f"valas_declaration_1.{subpath}", True, None
        if field_root == "currency":
            return "valas_declaration_1.usage_amount.currency", True, None
        return path, False, f"Field '{field_root}' is not present on {active_valas_type}."

    return path, True, None
