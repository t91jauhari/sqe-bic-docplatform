"""Captured seed and historical compatibility data, never startup publications."""
import copy
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def _catalog():
    return json.loads((Path(__file__).parents[1] / 'config_data/native_catalog_v1.json').read_text(encoding='utf-8'))


def native_catalog():
    return copy.deepcopy(_catalog())


def legacy_forex_rule(rule):
    result = copy.deepcopy(rule)
    for patch in _catalog()['legacy_forex_rule_patches']:
        if all(result.get(key) == value for key, value in patch['when'].items()):
            result.update(copy.deepcopy(patch['set']))
    return result
