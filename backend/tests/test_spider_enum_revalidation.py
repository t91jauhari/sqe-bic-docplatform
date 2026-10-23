from types import SimpleNamespace
import copy
from app.spider_result import extraction_report


def test_spider_aliases_require_explicit_request_and_preserve_source():
    profile = {'columns': [['religion', 'Religion'], ['name', 'Name']], 'policy': {
        'religion_values': ['Katolik', 'Buddha'], 'enum_aliases': {'religion': {'KATHOLIK': 'Katolik'}},
        'enum_raw_fallback_fields': ['religion']}}
    cfg = {'profiles': {'ektp': profile}}
    response = {'extract_result': {'religion': 'KATHOLIK', 'name': 'Synthetic customer'}}
    original = copy.deepcopy(response)
    doc = SimpleNamespace(doc_type='ektp', overrides={}, provider_state={})
    assert extraction_report(doc, cfg, response)['normalized']['religion'] == 'KATHOLIK'
    doc.provider_state = {'normalization_enum_aliases': {'religion': {'KATHOLIK': 'Katolik'}},
                          'normalization_enum_raw_fallback_fields': ['religion'], 'normalization_source_config_id': 'approved-revision'}
    result = extraction_report(doc, cfg, response)
    assert result['normalized']['religion'] == 'Katolik'
    assert result['normalized']['name'] == original['extract_result']['name']
    assert result['original_raw'] == original['extract_result']
    assert response == original
    assert result['normalization']['source_config_id'] == 'approved-revision'
    assert result['corrections'][0]['method'] == 'approved_enum_alias'


def test_unrecognized_explicit_enum_retains_text_and_uncertainty():
    profile = {'columns': [['religion', 'Religion']], 'policy': {'religion_values': ['Katolik'],
        'enum_aliases': {}, 'enum_raw_fallback_fields': ['religion']}}
    doc = SimpleNamespace(doc_type='ektp', overrides={}, provider_state={'normalization_enum_aliases': {},
        'normalization_enum_raw_fallback_fields': ['religion']})
    result = extraction_report(doc, {'profiles': {'ektp': profile}}, {'extract_result': {'religion': 'Other belief'}})
    assert result['normalized']['religion'] == 'Other belief'
    assert result['fields']['religion']['status'] == 'REVIEW'
