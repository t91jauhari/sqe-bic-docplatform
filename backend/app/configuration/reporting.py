"""Typed report projections; presentation cannot change findings or scores."""
import json
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class ReportBinding(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    source: Literal['document', 'context', 'customer', 'literal']
    path: str | None = Field(default=None, max_length=500)
    default: str | None = Field(default=None, max_length=500)
    fallback_customer: bool = False

    @model_validator(mode='after')
    def required_path(self):
        if (self.source in {'document', 'context'}) != bool(self.path):
            raise ValueError('Document/context bindings require a path; other sources cannot use one.')
        if self.source == 'document' and '.' not in self.path:
            raise ValueError('Document report bindings require profile.field paths.')
        if self.fallback_customer and self.source != 'document':
            raise ValueError('Customer fallback is supported only for document bindings.')
        return self


class ReportDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    timezone: str = Field(max_length=100)
    bindings: dict[str, ReportBinding]

    @field_validator('timezone')
    @classmethod
    def timezone_exists(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError('Choose a registered IANA timezone.') from exc
        return value


def defaults():
    return json.loads((Path(__file__).parents[1] / 'config_data/report_bindings_v1.json').read_text(encoding='utf-8'))


def definitions(configuration):
    return {key: ReportDefinition.model_validate(value) for key, value in
            {**defaults(), **configuration.get('report_definitions', {})}.items()}


def validate_report_definitions(configuration):
    raw = configuration.get('report_definitions', {})
    baseline = defaults()
    if not isinstance(raw, dict) or set(raw) - set(baseline):
        raise ValueError('Report definitions must use registered layout IDs.')
    family_definitions = configuration.get('document_families', {})
    if not isinstance(family_definitions, dict) or any(not isinstance(value, dict) for value in family_definitions.values()):
        raise ValueError('Document family definitions must be objects.')
    if not raw and not any(value.get('report_definition') is not None for value in family_definitions.values()):
        return
    from .identity import _resolve
    from .contexts import definitions as context_definitions
    from app.document_families import families
    catalog = families(configuration)
    def validate(layout, value, family=None):
        if layout not in baseline:
            raise ValueError('Unknown report layout for family mapping.')
        contexts = context_definitions(configuration, family)
        definition = ReportDefinition.model_validate(value)
        if set(definition.bindings) != set(baseline[layout]['bindings']):
            raise ValueError('Configure every supported report binding exactly once.')
        for binding in definition.bindings.values():
            if binding.source == 'document':
                profile, path = binding.path.split('.', 1)
                if profile not in configuration['profiles']:
                    raise ValueError('Report binding references an unknown document profile.')
                if family and profile not in catalog[family]['profiles']:
                    raise ValueError('Report binding references a document outside this family.')
                root = configuration['profiles'][profile]['schema']
                node = root
                for part in path.split('.'):
                    node = _resolve(node, root).get('properties', {}).get(part)
                    if not isinstance(node, dict):
                        raise ValueError('Report binding references an unknown schema field.')
            elif binding.source == 'context' and binding.path not in contexts:
                raise ValueError('Report bindings must use registered case context fields.')
    for layout, value in raw.items():
        validate(layout, value)
    for family, value in family_definitions.items():
        if value.get('report_definition') is not None:
            validate(value.get('report_layout', 'forex'), value['report_definition'], family)


def project_report(snapshot, layout):
    from app.sop import value_at
    configuration = snapshot.get('configuration', {})
    flow = configuration.get('templates', {}).get(snapshot.get('template'), {})
    family = flow.get('document_family', 'account_opening' if layout == 'account_opening' else 'forex')
    override = configuration.get('document_families', {}).get(family, {}).get('report_definition')
    definition = ReportDefinition.model_validate(override) if override is not None else definitions(configuration)[layout]
    values = {}
    for key, binding in definition.bindings.items():
        if binding.source == 'document':
            value, matches = value_at(snapshot['documents'], binding.path)
            value = value if len(matches) == 1 else None
        elif binding.source == 'context':
            value = snapshot.get('case_context', {}).get(binding.path)
        elif binding.source == 'customer':
            value = snapshot['customer']
        else:
            value = binding.default
        if value in (None, ''):
            value = snapshot['customer'] if binding.fallback_customer else binding.default
        values[key] = value
    return values, definition.timezone
