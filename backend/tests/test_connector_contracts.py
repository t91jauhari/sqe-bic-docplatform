import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.db import SessionLocal, SpiderConnector
from app.extraction.connector_contracts import (
    SpiderConnectorInput, administrative_options, normalized_options, numeric_option_fields,
)
from app.extraction.connector_repository import SqlConnectorRepository
from app.extraction.contracts import ProcessingIssue


def test_key_rotation_preserves_selected_model_and_advanced_options(signed):
    endpoint = '/api/connectors/spider-ai'
    assert signed.put(endpoint, json={'model_id': 'configured-model', 'max_tokens': 2000,
                                     'image_max_bytes': 160000}).status_code == 200
    with SessionLocal.begin() as session:
        record = session.scalar(select(SpiderConnector))
        record.options = {**record.options, 'legacy_private_option': 'preserve-in-storage'}
    response = signed.put(endpoint, json={'api_key': 'synthetic-key'})
    assert response.status_code == 200
    result = signed.get(endpoint)
    assert result.json()['options']['model_id'] == 'configured-model'
    assert result.json()['options']['max_tokens'] == 2000
    assert result.json()['options']['image_max_bytes'] == 160000
    assert 'synthetic-key' not in result.text
    assert 'legacy_private_option' not in result.text
    with SessionLocal() as session:
        assert session.scalar(select(SpiderConnector)).options['legacy_private_option'] == 'preserve-in-storage'
    connection = SqlConnectorRepository(SessionLocal, lambda value: 'decrypted-secret').read('sqe', 'spider-ai')
    assert connection.api_key == 'decrypted-secret'
    assert connection.options['model_id'] == 'configured-model'
    assert 'decrypted-secret' not in repr(connection)
    assert SqlConnectorRepository(SessionLocal, lambda value: value).read('another-org', 'spider-ai').api_key == ''




@pytest.mark.parametrize('change', [
    {'max_tokens': 0}, {'max_tokens': 1.5}, {'top_p': 2}, {'image_jpeg_quality': 101},
    {'base_url': 'http://example.invalid'}, {'base_url': 'https://user:secret@example.invalid'},
    {'api_key': 'Bearer secret'}, {'model_id': '   '}, {'unknown_option': True},
])
def test_invalid_connector_input_is_rejected(change):
    with pytest.raises(ValidationError):
        SpiderConnectorInput.model_validate(change)


def test_invalid_stored_configuration_fails_closed_and_can_be_repaired(signed):
    signed.put('/api/connectors/spider-ai', json={'model_id': 'configured-model'})
    with SessionLocal.begin() as session:
        record = session.scalar(select(SpiderConnector))
        record.options = {'max_tokens': -1, 'model_id': 'configured-model'}
    with pytest.raises(ProcessingIssue, match='settings are invalid'):
        SqlConnectorRepository(SessionLocal, lambda value: value).read('sqe', 'spider-ai')
    response = signed.get('/api/connectors/spider-ai').json()
    assert response['configuration_warning']
    assert response['options']['max_tokens'] > 0
    assert signed.put('/api/connectors/spider-ai', json=response['options']).status_code == 200
    assert signed.get('/api/connectors/spider-ai').json()['configuration_warning'] is None


def test_optional_budget_and_server_defined_numeric_controls():
    assert 'image_max_bytes' not in normalized_options('spider-ai', {'image_max_bytes': None})
    fields = {field['key']: field for field in numeric_option_fields()}
    assert fields['max_tokens']['integer'] is True
    assert fields['image_max_bytes']['nullable'] is True
    assert administrative_options('spider-ai', {})['configuration_warning'] is None
    assert 'synthetic-secret' not in repr(SpiderConnectorInput(api_key='synthetic-secret'))
