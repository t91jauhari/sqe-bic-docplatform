from types import SimpleNamespace
import copy
import json

import pytest

from app.configuration.field_checks import FieldCheck, evaluate_field, validate_field_checks
from app.spider_result import extraction_report


@pytest.mark.parametrize('value,policy,status,reason', [
    ('001234', {'kind': 'identifier', 'digits': 6}, 'PASS', 'VALID_VALUE'),
    ('001 234', {'kind': 'identifier', 'digits': 6}, 'FAIL', 'INVALID_IDENTIFIER'),
    ('2025-02-31', {'kind': 'date'}, 'FAIL', 'INVALID_DATE'),
    ('31-05-2025', {'kind': 'date'}, 'PASS', 'VALID_VALUE'),
    ({'raw': 'Name', 'complete': False}, {'kind': 'text'}, 'FAIL', 'INCOMPLETE_EXTRACTION'),
    (None, {'kind': 'text'}, 'FAIL', 'MISSING_VALUE'),
    (None, {'kind': 'text', 'required': False}, 'NOT_APPLICABLE', 'OPTIONAL_EMPTY'),
    ('Private', {'kind': 'choice', 'choices': ['Private']}, 'PASS', 'VALID_VALUE'),
    ('private', {'kind': 'choice', 'choices': ['Private']}, 'FAIL', 'UNREGISTERED_CHOICE'),
    ('USD 1.234,56', {'kind': 'number', 'currency': 'USD', 'decimal_separator': ',', 'thousands_separator': '.'}, 'PASS', 'VALID_VALUE'),
    ('USD 1,23.56', {'kind': 'number', 'currency': 'USD', 'decimal_separator': '.', 'thousands_separator': ','}, 'FAIL', 'INVALID_NUMBER_FORMAT'),
    (float('nan'), {'kind': 'number'}, 'FAIL', 'INVALID_NUMBER'),
    (False, {'kind': 'boolean'}, 'PASS', 'VALID_VALUE'),
    ('false', {'kind': 'boolean'}, 'FAIL', 'INVALID_TYPE'),
])
def test_explicit_data_checks(value, policy, status, reason):
    assert evaluate_field(value, policy) == (status, reason)


def test_spider_data_checks_preserve_raw_values_and_leave_unchecked_fields_skipped():
    profile = {'columns': [['name', 'Name'], ['identifier', 'ID'], ['signature', 'Signature']],
               'schema': {'properties': {'name': {'type': 'string'}, 'identifier': {'type': 'string'},
                                         'signature': {'type': 'object', 'properties': {'present': {'type': 'boolean'}}}}},
               'field_checks': {'name': {'kind': 'text'}, 'identifier': {'kind': 'identifier', 'digits': 6}}}
    doc = SimpleNamespace(doc_type='synthetic', overrides={})
    response = {'extract_result': {'name': 'Printed name', 'identifier': '001234', 'signature': {'present': True}}}
    original = copy.deepcopy(response)
    report = extraction_report(doc, {'profiles': {'synthetic': profile}}, response)
    assert report['fields']['name']['status'] == report['fields']['identifier']['status'] == 'PASS'
    assert report['fields']['signature']['status'] == 'SKIPPED'
    assert report['normalized'] == original['extract_result']
    assert response == original
    assert report['normalization']['status'] == 'SKIPPED'
    assert report['data_validation']['scope'] == 'configured_data_checks_only'
    profile['field_checks']['signature'] = {'kind': 'boolean'}
    with pytest.raises(ValueError, match='Visual-region'):
        validate_field_checks(profile)


def test_unconfigured_profiles_keep_existing_spider_behavior():
    report = extraction_report(SimpleNamespace(doc_type='synthetic', overrides={}),
        {'profiles': {'synthetic': {'columns': [['name', 'Name']]}}}, {'extract_result': {'name': 'Name'}})
    assert report['fields']['name']['status'] == 'SKIPPED'
    assert 'data_validation' not in report


def test_unknown_policy_and_conflicting_separators_are_rejected():
    for value in [{'kind': 'number', 'decimal_separator': '.', 'thousands_separator': '.'},
                  {'kind': 'text', 'unused_constraint': True}, {'kind': 'choice', 'choices': []}]:
        with pytest.raises(ValueError):
            FieldCheck.model_validate(value)


@pytest.mark.parametrize('prior', ['FAIL', 'ERROR', 'REVIEW'])
def test_additional_check_never_erases_prior_validation(prior):
    from app.configuration.field_checks import apply_field_checks
    report = {'status': prior, 'normalized': {'name': 'Name'},
              'fields': {'name': {'status': prior, 'issues': [{'code': 'EXISTING', 'severity': prior}]}}}
    profile = {'schema': {'properties': {'name': {'type': 'string'}}}, 'field_checks': {'name': {'kind': 'text'}}}
    result = apply_field_checks(report, profile)
    assert result['fields']['name']['status'] == 'FAIL'
    assert result['fields']['name']['issues'][0]['code'] == 'EXISTING'
    assert result['status'] == 'FAIL'


def test_schema_provider_applies_same_configured_checks():
    from app.provider import validate_extraction
    profile = {'validation_adapter': 'schema', 'schema': {'type': 'object', 'properties': {'number': {'type': 'string'}},
               'required': ['number']}, 'field_checks': {'number': {'kind': 'identifier', 'digits': 6}}}
    report = validate_extraction(SimpleNamespace(doc_type='synthetic', overrides={}),
        {'profiles': {'synthetic': profile}}, {'extract_result': {'number': '12345'}})
    assert report['fields']['number']['status'] == 'FAIL'
    assert report['status'] == 'FAIL'


def test_field_checks_and_report_bindings_survive_workbook_round_trip():
    from app.domain import default_config
    from app.config_workbook import export_config, import_config
    from app.configuration.reporting import defaults
    configuration = default_config()
    configuration['profiles']['ektp']['field_checks'] = {'nik': {'kind': 'identifier', 'digits': 16}}
    configuration['report_definitions'] = defaults()
    data = export_config(configuration)
    baseline = default_config()
    draft, errors = import_config(data, baseline)
    assert not errors
    assert draft['profiles']['ektp']['field_checks'] == configuration['profiles']['ektp']['field_checks']
    assert draft['report_definitions'] == configuration['report_definitions']


def test_oversize_workbook_settings_fail_instead_of_silent_truncation():
    from app.domain import default_config
    from app.config_workbook import export_config
    configuration = default_config()
    configuration['profiles']['ektp']['system_instruction'] = 'x' * 32768
    with pytest.raises(ValueError, match='Excel cell limit'):
        export_config(configuration)


@pytest.mark.parametrize('identifier,expected,points', [('001234', 'PASS', 1), ('00123', 'FAIL', 0)])
def test_configured_spider_check_drives_sop_outcome_and_point(identifier, expected, points):
    from app.sop import evaluate
    from app.sop_scoring import point_summary
    profile = {'columns': [['identifier', 'Identifier']], 'schema': {'properties': {'identifier': {'type': 'string'}}},
               'field_checks': {'identifier': {'kind': 'identifier', 'digits': 6}}}
    report = extraction_report(SimpleNamespace(doc_type='synthetic', overrides={}),
        {'profiles': {'synthetic': profile}}, {'extract_result': {'identifier': identifier}})
    rule = {'id': 'synthetic-field', 'label': 'Verify identifier', 'enabled': True, 'operator': 'account_check',
            'path': 'synthetic.identifier', 'source_ref': 'AO:synthetic', 'scope_basis': 'Synthetic check',
            'report_category': 'DATA_COMPLETION', 'comparison_policy': json.dumps({'kind': 'field'})}
    document = {'id': 'one', 'doc_type': 'synthetic', 'status': 'COMPLETED',
                'normalized': report['normalized'], 'validation': report}
    findings = evaluate([document], {'sop_rules': [rule]}, {})
    assert findings[0]['result'] == expected
    assert findings[0]['evaluation_type'] == 'DATA'
    assert point_summary(findings)['earned'] == points
