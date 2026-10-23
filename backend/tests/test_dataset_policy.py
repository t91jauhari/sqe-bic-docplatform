import copy

import pytest

from app.configuration.dataset_policy import comparison_policy, validate_comparison_policies
from app.dataset_comparison import fuzzy_text


def configured():
    return {'templates': {'custom': {'document_family': 'custom'}},
            'document_families': {'custom': {'label': 'Custom', 'profiles': []},
                                  'other': {'label': 'Other', 'profiles': []}}}


@pytest.mark.parametrize('change', [
    {'minimum_similarity': .99, 'acceptance_similarity': .95},
    {'minimum_length': 3000, 'maximum_length': 2000},
    {'short_edit_limit': 100}, {'enabled': 1}, {'ignored_option': True},
    {'descriptive_fields': ['name', 'name']}, {'excluded_suffixes': ['']},
])
def test_invalid_comparison_policies_are_rejected(change):
    cfg = configured()
    cfg['document_families']['custom']['comparison_policy'] = change
    with pytest.raises(ValueError):
        validate_comparison_policies(cfg)


def test_family_policy_is_scoped_and_does_not_mutate_published_payload():
    cfg = configured()
    cfg['document_families']['custom']['comparison_policy'] = {'enabled': False}
    cfg['templates']['other'] = {'document_family': 'other'}
    original = copy.deepcopy(cfg)
    assert comparison_policy(cfg, 'custom').enabled is False
    assert comparison_policy(cfg, 'other').enabled is True
    assert cfg == original


def test_disabled_similarity_and_changed_identifier_digits_never_match():
    policy = comparison_policy().model_copy(update={'enabled': False})
    assert fuzzy_text('Long descriptive text.', 'Long descriptive text', 'text', 'details', policy) is None
    enabled = comparison_policy()
    assert fuzzy_text('Address number 123', 'Address number 124', 'text', 'details', enabled) is None
    assert fuzzy_text('ABC12345678', 'ABC12345679', 'text', 'account_number', enabled) is None


def test_configured_fields_and_limits_control_acceptance_without_rewriting_values():
    a, b = 'A sufficiently long descriptive statement', 'A sufficiently long descriptivf statement'
    default = fuzzy_text(a, b, 'text', 'name')
    assert default['status'] == 'REVIEW'
    policy = comparison_policy().model_copy(update={'descriptive_fields': ['name']})
    assert fuzzy_text(a, b, 'text', 'name', policy)['status'] == 'FUZZY_MATCH'
    strict = policy.model_copy(update={'short_edit_limit': 0, 'long_edit_limit': 0})
    assert fuzzy_text(a, b, 'text', 'name', strict) is None
    assert a == 'A sufficiently long descriptive statement'


def test_comparison_uses_case_pin_after_new_family_policy_is_published(signed, monkeypatch):
    def upload_case(label):
        branch = signed.get('/api/branches').json()[0]['id']
        response = signed.post('/api/uploads', data={'branch_id': branch, 'template': 'forex'},
            files=[('files', (label + '_ektp.pdf', b'%PDF-1.4\n% ' + label.encode(), 'application/pdf'))],
            headers={'Idempotency-Key': label})
        assert response.status_code == 202, response.text
        return response.json()['case_ids'][0]
    monkeypatch.setattr('app.dataset_comparison.dataset_for_case', lambda *args: {})
    monkeypatch.setattr('app.dataset_comparison.compare',
                        lambda *args, policy: {'enabled': policy.enabled})
    before = upload_case('Synthetic Before')
    current = signed.get('/api/config').json()
    cfg = current['payload']
    from app.document_families import families
    family = families(cfg)['forex']
    cfg.setdefault('document_families', {})['forex'] = {**family, 'comparison_policy': {'enabled': False}}
    response = signed.post('/api/config/publish', json={'expected_version': current['version'], 'payload': cfg})
    assert response.status_code == 200, response.text
    after = upload_case('Synthetic After')
    assert signed.get(f'/api/cases/{before}/comparison').json() == {'enabled': True}
    assert signed.get(f'/api/cases/{after}/comparison').json() == {'enabled': False}
    assert signed.get('/api/config/catalog').json()['dataset_comparison_policy']['enabled'] is True


def test_blank_presence_reference_means_absent_without_changing_text_blanks():
    from app.dataset_comparison import canonical
    for value in (None, '', '[BLANK]'):
        assert canonical(value, 'presence') is False
        assert canonical(value, 'initials') is False
        assert canonical(value, 'text') is None
    assert canonical(True, 'presence') is True


def test_issuance_projection_accepts_raw_and_normalized_components():
    from types import SimpleNamespace
    from app.dataset_comparison import canonical, project
    for value in (
        {'place': 'QA CITY', 'date': '23-10-2026'},
        {'raw': 'QA CITY\n23-10-2026', 'place_raw': 'QA CITY', 'date_raw': '23-10-2026'},
        {'raw': 'QA CITY, 23-10-2026', 'complete': True},
    ):
        projected=project(SimpleNamespace(normalized={'issuance':value}), 'issuance', 'text')
        assert canonical(projected, 'text', 'issuance') == canonical('QA CITY, 23-10-2026','text','issuance')


def test_month_only_dates_keep_precision_without_inventing_a_day():
    from app.dataset_comparison import canonical
    assert canonical('Februari 2025','date') == canonical('February 2025','date') == ('month','2025-02')
    assert canonical('Sep 2025','date') == ('month','2025-09')
    assert canonical('01-09-2025','date') != canonical('September 2025','date')
    for invalid in ('unknown 2025','Februari 0000'):
        with pytest.raises(ValueError):canonical(invalid,'date')
