import copy
import json
from pathlib import Path

import pytest

from app.configuration.account_policies import parse_policy, condition_result
from app.account_opening_sop import evaluate_rule


def condition():
    return {'path': 'account_opening_form.risk_category', 'true_values': ['Risiko Tinggi'],
            'false_values': ['Risiko Rendah', 'Risiko Sedang']}


def documents(value, status='PASS'):
    return [{'id': 'form', 'doc_type': 'account_opening_form', 'status': 'COMPLETED',
             'normalized': {'risk_category': value}, 'validation': {'fields': {'risk_category': {'status': status}}}}]


def test_all_captured_account_policies_validate_without_changing_json():
    rules = json.loads((Path(__file__).parents[1] / 'app/config_data/account_opening_rules.json').read_text(encoding='utf-8'))
    for rule in rules:
        source = json.loads(rule['comparison_policy'])
        assert parse_policy(source) == source
        assert parse_policy(rule['comparison_policy']) == source


@pytest.mark.parametrize('value,expected', [('RISIKO TINGGI', True), ('Risiko Rendah', False), ('Other', None), (None, None),
    ({'raw': 'Risiko Tinggi', 'complete': False}, None)])
def test_condition_is_explicit_and_unknown_is_not_false(value, expected):
    assert condition_result(documents(value), condition()) is expected


def test_ambiguous_or_unverified_condition_never_excludes_requirement():
    source = documents('Risiko Rendah')
    assert condition_result(source + copy.deepcopy(source), condition()) is None
    assert condition_result(documents('Risiko Rendah', 'FAIL'), condition()) is None


@pytest.mark.parametrize('policy', [
    {'kind': 'field', 'unused': True}, {'kind': 'field', 'identifier': True},
    {'kind': 'conditional_edd'}, {'kind': 'match', 'required_pattern': '(a+)+$'},
    {'kind': 'conditional_edd', 'target': 'edd', 'trigger': {'path': 'form.risk', 'true_values': ['Yes'], 'false_values': [' YES ']}},
])
def test_invalid_or_ignored_policy_options_are_rejected(policy):
    with pytest.raises(ValueError):
        parse_policy(policy)


def test_configured_trigger_requires_target_only_when_explicitly_applicable():
    rule = {'id': 'synthetic', 'path': 'account_opening_form.risk_category', 'label': 'Risk evidence',
            'comparison_policy': json.dumps({'kind': 'conditional_edd', 'target': 'edd', 'trigger': condition()}),
            'source_ref': 'AO:synthetic', 'scope_basis': 'Synthetic', 'report_category': 'DOCUMENT_COMPLETION'}
    cfg = {'profiles': {'account_opening_form': {}, 'edd': {}}}
    assert evaluate_rule(rule, documents('Risiko Tinggi'), cfg, {})['result'] == 'FAIL'
    assert evaluate_rule(rule, documents('Risiko Rendah'), cfg, {})['result'] == 'NOT_APPLICABLE'
    assert evaluate_rule(rule, documents('Other'), cfg, {})['result'] == 'REVIEW'
    source = documents('Risiko Tinggi') + [{'id': 'edd', 'doc_type': 'edd', 'status': 'COMPLETED', 'normalized': {}}]
    assert evaluate_rule(rule, source, cfg, {})['result'] == 'PASS'
