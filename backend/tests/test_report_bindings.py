import copy
import json

import pytest
from app.configuration.reporting import defaults, project_report, validate_report_definitions
from app.domain import default_config


def snapshot():
    return {'customer': 'Synthetic customer', 'configuration': {}, 'documents': [
        {'id': 'one', 'doc_type': 'application', 'status': 'COMPLETED',
         'normalized': {'remitter': {'name': 'Printed name'}, 'remitter_account_number': '00123',
                        'transaction_type': 'Transfer', 'transaction_date': '2025-01-01'}}],
        'case_context': {'transaction_carrier': 'CUSTOMER'}}


def test_default_report_projection_and_explicit_context_binding():
    source = snapshot()
    original = copy.deepcopy(source)
    values, timezone = project_report(source, 'forex')
    assert values['customer'] == 'Printed name'
    assert values['account'] == '00123'
    assert timezone == 'Asia/Jakarta'
    source['configuration']['report_definitions'] = defaults()
    source['configuration']['report_definitions']['forex']['bindings']['account'] = {'source': 'context', 'path': 'new_account_number'}
    source['case_context']['new_account_number'] = '00999'
    assert project_report(source, 'forex')[0]['account'] == '00999'
    assert original['documents'] == source['documents']


def test_ambiguous_sources_do_not_choose_a_document():
    source = snapshot()
    source['documents'].append(copy.deepcopy(source['documents'][0]))
    values, _ = project_report(source, 'forex')
    assert values['account'] is None
    assert values['customer'] == 'Synthetic customer'


def test_family_override_does_not_change_another_family_using_same_layout():
    source = snapshot()
    override = defaults()['forex']
    override['bindings']['account'] = {'source': 'literal', 'default': 'LOAN-ACCOUNT'}
    source['configuration'] = {'templates': {'loan': {'document_family': 'loans'}, 'forex': {'document_family': 'forex'}},
        'document_families': {'loans': {'report_layout': 'forex', 'report_definition': override}}}
    source['template'] = 'loan'
    assert project_report(source, 'forex')[0]['account'] == 'LOAN-ACCOUNT'
    source['template'] = 'forex'
    assert project_report(source, 'forex')[0]['account'] == '00123'


def test_family_binding_cannot_reference_another_familys_documents():
    configuration = default_config()
    configuration['document_families'] = {'loans': {'label': 'Loans', 'profiles': ['ektp'],
        'report_layout': 'forex', 'report_definition': defaults()['forex']}}
    with pytest.raises(ValueError, match='outside this family'):
        validate_report_definitions(configuration)


def test_all_default_report_bindings_validate_against_profile_schemas():
    configuration = default_config()
    configuration['report_definitions'] = defaults()
    validate_report_definitions(configuration)


def test_report_bindings_round_trip_as_immutable_configuration_entries():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.configuration.store import ConfigurationBase, import_publication, compile_publication
    engine = create_engine('sqlite://')
    ConfigurationBase.metadata.create_all(engine)
    payload = json.loads(json.dumps(default_config()))
    payload['report_definitions'] = defaults()
    with Session(engine) as session:
        first = import_publication(session, organization='synthetic', revision=1, source_config_id='one', payload=payload)
        changed = copy.deepcopy(payload)
        changed['report_definitions']['forex']['bindings']['transaction_type'] = {'source': 'literal', 'default': 'Configured report type'}
        second = import_publication(session, organization='synthetic', revision=2, source_config_id='two', payload=changed)
        assert compile_publication(session, first) == payload
        assert compile_publication(session, second) == changed
    engine.dispose()


def test_report_binding_metadata_requires_signed_administrator(signed):
    response = signed.get('/api/config/report-bindings')
    assert response.status_code == 200
    assert response.json() == defaults()


@pytest.mark.parametrize('change', ['unknown_field', 'unknown_context', 'unused_binding', 'timezone'])
def test_unexecutable_report_bindings_are_rejected(change):
    configuration = default_config()
    configuration['report_definitions'] = defaults()
    definition = configuration['report_definitions']['forex']
    if change == 'unknown_field':
        definition['bindings']['account']['path'] = 'application.nonexistent'
    elif change == 'unknown_context':
        definition['bindings']['account'] = {'source': 'context', 'path': 'nonexistent'}
    elif change == 'unused_binding':
        definition['bindings']['unused'] = {'source': 'literal', 'default': 'Unused'}
    else:
        definition['timezone'] = 'Missing/Timezone'
    with pytest.raises(ValueError):
        validate_report_definitions(configuration)
