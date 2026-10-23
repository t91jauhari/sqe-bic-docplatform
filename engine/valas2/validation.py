"""Valas 2 uses shared declaration checks with its ten-field schema."""
from valas_common import validate_declaration
from valas2.schema import SCHEMA, COLUMNS, DOCUMENT_NAME


def validate(raw, metadata, policy, as_of=None, directory=None, validation_context=None, extract_job_id=None):
    return validate_declaration(raw, metadata, policy, as_of, directory, validation_context, extract_job_id,
                                schema=SCHEMA, columns=COLUMNS, document_type="valas_declaration_2",
                                document_name=DOCUMENT_NAME)
