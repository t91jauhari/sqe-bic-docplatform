"""Versioned reference comparison settings; never alter extraction or SOP scores."""
import copy
import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetComparisonPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    enabled: bool = True
    exclude_final_page: bool = False
    minimum_similarity: float = Field(ge=0, le=1)
    acceptance_similarity: float = Field(ge=0, le=1)
    minimum_length: int = Field(ge=1, le=10000)
    maximum_length: int = Field(ge=1, le=10000)
    acceptance_minimum_length: int = Field(ge=1, le=10000)
    long_text_length: int = Field(ge=1, le=10000)
    short_edit_limit: int = Field(ge=0, le=10)
    long_edit_limit: int = Field(ge=0, le=10)
    descriptive_fields: list[str] = Field(max_length=500)
    excluded_fields: list[str] = Field(max_length=500)
    excluded_suffixes: list[str] = Field(max_length=100)

    @model_validator(mode='after')
    def coherent(self):
        if self.acceptance_similarity < self.minimum_similarity:
            raise ValueError('Acceptance similarity must be at least the review similarity.')
        if self.minimum_length > self.maximum_length or self.acceptance_minimum_length > self.maximum_length:
            raise ValueError('Comparison text length limits are inconsistent.')
        for values in (self.descriptive_fields, self.excluded_fields, self.excluded_suffixes):
            if len(values) != len(set(values)) or any(not value.strip() or len(value) > 200 for value in values):
                raise ValueError('Comparison field names and suffixes must be distinct nonempty values.')
        return self


@lru_cache(maxsize=1)
def _defaults():
    return json.loads((Path(__file__).parents[1] / 'config_data/dataset_comparison_v1.json').read_text(encoding='utf-8'))


def comparison_policy(configuration=None, flow_id=None):
    values = copy.deepcopy(_defaults())
    if configuration and flow_id:
        from app.document_families import families
        flow = configuration['templates'][flow_id]
        family = families(configuration)[flow.get('document_family', 'forex')]
        values.update(family.get('comparison_policy', {}))
    return DatasetComparisonPolicy.model_validate(values)


def validate_comparison_policies(configuration):
    for family in configuration.get('document_families', {}).values():
        if isinstance(family, dict) and 'comparison_policy' in family:
            if not isinstance(family['comparison_policy'], dict):
                raise ValueError('Family comparison policy must be an object.')
            DatasetComparisonPolicy.model_validate({**_defaults(), **family['comparison_policy']})
