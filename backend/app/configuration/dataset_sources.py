"""Explicit dataset rollout and legacy import source; no module-load private data."""
import json
from pathlib import Path

from .datasets import DatasetIntegrityError, read_dataset, register_dataset, dataset_catalog
from .codec import fingerprint


def bundled_datasets():
    directory = Path(__file__).parents[1] / 'datasets'
    forex = json.loads((directory / 'forex_sample.json').read_text(encoding='utf-8'))
    # Captured compatibility mapping from the existing workbook import.
    from app.extraction_quality import INVOICE_FIELDS
    for row in forex['rows']:
        if row['document_type'] == 'invoice':
            for field, (label, _) in INVOICE_FIELDS.items():
                if row['label'] == label:
                    row['field'] = field
        if row['document_type'] == 'valas_declaration_1' and row['label'] == 'Stamp verification':
            row['field'] = 'stamp_verification'
    account = json.loads((directory / 'account_opening_sample.json').read_text(encoding='utf-8'))
    return {value['id']: value for value in (forex, account)}


def import_bundled(session, organization):
    return [register_dataset(session, organization, value) for value in bundled_datasets().values()]


def resolve_dataset(session, organization, dataset_id, *, mode=None):
    if dataset_id is None:
        return {'id': 'none', 'source_name': 'No reference dataset', 'sha256': '', 'samples': [], 'rows': []}
    if mode is None:
        from app.settings import settings
        mode = settings.dataset_read_mode
    if mode not in {'bundled', 'verify', 'registry'}:
        raise ValueError('Unknown dataset read mode.')
    if mode == 'registry':
        return read_dataset(session, organization, dataset_id)
    source = bundled_datasets().get(dataset_id)
    if source is None:
        raise DatasetIntegrityError('The configured reference dataset is unavailable; no fallback was applied.')
    if mode == 'verify' and fingerprint(source) != fingerprint(read_dataset(session, organization, dataset_id)):
        raise DatasetIntegrityError('Bundled and registered reference datasets differ.')
    return source


def catalog(session, organization):
    from app.settings import settings
    if settings.dataset_read_mode == 'bundled':
        return [{'id': value['id'], 'source_name': value['source_name'], 'digest': fingerprint(value)}
                for value in bundled_datasets().values()]
    return dataset_catalog(session, organization)
