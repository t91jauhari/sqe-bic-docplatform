import copy

import pytest

from app.configuration.contracts import validate_envelope
from app.domain import default_config, validate_config


@pytest.mark.parametrize('change', [
    {'profiles': []}, {'templates': {'service': []}}, {'maker_checker': 1},
    {'classification_threshold': True}, {'workflow': ['executable.path']},
    {'customer_aliases': {'source': 123}}, {'sop_rules': [None]},
])
def test_invalid_root_shapes_fail_before_profile_and_policy_execution(change):
    cfg = default_config()
    cfg.update(change)
    with pytest.raises(ValueError):
        validate_config(cfg)


def test_root_contract_preserves_extensions_and_does_not_add_defaults():
    cfg = default_config()
    cfg['organization_extension'] = {'nested': [True, None, 'synthetic']}
    before = copy.deepcopy(cfg)
    result = validate_envelope(cfg)
    assert result.organization_extension == cfg['organization_extension']
    assert cfg == before


def test_extension_nonfinite_values_are_rejected_before_persistence():
    cfg = default_config()
    cfg['organization_extension'] = {'hidden': float('nan')}
    with pytest.raises(ValueError, match='finite JSON'):
        validate_config(cfg)
