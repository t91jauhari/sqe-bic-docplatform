"""Explicit data checks on model values; never infer visual authenticity or edit values."""
import re
import copy
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FieldCheck(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    kind: Literal['text', 'identifier', 'date', 'number', 'choice', 'boolean']
    required: bool = True
    minimum_length: int = Field(default=1, ge=1, le=10000)
    maximum_length: int = Field(default=10000, ge=1, le=100000)
    digits: int | None = Field(default=None, ge=1, le=100)
    choices: list[str] = Field(default_factory=list, max_length=1000)
    normalization: Literal['literal', 'casefold_whitespace'] = 'literal'
    decimal_separator: Literal['.', ','] = '.'
    thousands_separator: Literal['.', ',', ' '] | None = None
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')

    @model_validator(mode='after')
    def coherent_checks(self):
        if self.minimum_length > self.maximum_length:
            raise ValueError('Minimum length cannot exceed maximum length.')
        if self.kind == 'choice' and (not self.choices or any(not value for value in self.choices)):
            raise ValueError('Choice checks require nonempty allowed values.')
        if self.kind != 'choice' and self.choices:
            raise ValueError('Allowed values apply only to choice checks.')
        if self.digits is not None and self.kind != 'identifier':
            raise ValueError('Digit length applies only to identifier checks.')
        if self.thousands_separator == self.decimal_separator:
            raise ValueError('Decimal and thousands separators must differ.')
        return self


def validate_field_checks(profile):
    checks = profile.get('field_checks', {})
    if not isinstance(checks, dict) or len(checks) > 1000:
        raise ValueError('Configure at most 1000 field checks per profile.')
    if not checks:
        return checks
    from .identity import _resolve
    root = profile['schema']
    for field, value in checks.items():
        if field not in root.get('properties', {}):
            raise ValueError('Field checks must reference a configured top-level schema field.')
        node = _resolve(root['properties'][field], root)
        if 'present' in node.get('properties', {}):
            raise ValueError('Visual-region fields require visual review rules, not data checks.')
        FieldCheck.model_validate(value)
    return checks


def evaluate_field(value, definition):
    policy = FieldCheck.model_validate(definition)
    if isinstance(value, dict) and 'raw' in value and 'complete' in value:
        if value['complete'] is not True:
            return 'FAIL', 'INCOMPLETE_EXTRACTION'
        value = value['raw']
    if value is None or value == '' or value == [] or value == {}:
        return ('FAIL', 'MISSING_VALUE') if policy.required else ('NOT_APPLICABLE', 'OPTIONAL_EMPTY')
    if policy.kind == 'boolean':
        return ('PASS', 'VALID_VALUE') if type(value) is bool else ('FAIL', 'INVALID_TYPE')
    if policy.kind == 'number':
        try:
            if isinstance(value, str):
                text = value.strip()
                if policy.currency:
                    if not text.startswith(policy.currency + ' '):
                        return 'FAIL', 'CURRENCY_MISMATCH'
                    text = text[len(policy.currency) + 1:]
                group = re.escape(policy.thousands_separator) if policy.thousands_separator else None
                integral = rf'(?:[0-9]+|[0-9]{{1,3}}(?:{group}[0-9]{{3}})+)' if group else r'[0-9]+'
                if not re.fullmatch(rf'[+-]?{integral}(?:{re.escape(policy.decimal_separator)}[0-9]+)?', text):
                    return 'FAIL', 'INVALID_NUMBER_FORMAT'
                if policy.thousands_separator:
                    text = text.replace(policy.thousands_separator, '')
                number = Decimal(text.replace(policy.decimal_separator, '.'))
            elif type(value) in {int, float} and not policy.currency:
                number = Decimal(str(value))
            else:
                return 'FAIL', 'INVALID_TYPE'
            return ('PASS', 'VALID_VALUE') if number.is_finite() else ('FAIL', 'INVALID_NUMBER')
        except (ValueError, InvalidOperation):
            return 'FAIL', 'INVALID_NUMBER'
    if not isinstance(value, str) or not value.strip():
        return 'FAIL', 'INVALID_TYPE'
    if not policy.minimum_length <= len(value.strip()) <= policy.maximum_length:
        return 'FAIL', 'INVALID_LENGTH'
    if policy.kind == 'identifier' and not re.fullmatch(r'[0-9]{'+str(policy.digits)+'}' if policy.digits else r'[0-9]+', value):
        return 'FAIL', 'INVALID_IDENTIFIER'
    if policy.kind == 'date':
        from validation import parse_date
        try:
            parse_date(value)
        except (ValueError, TypeError, OverflowError):
            return 'FAIL', 'INVALID_DATE'
    if policy.kind == 'choice':
        def normalize(text):
            return ' '.join(text.split()).casefold() if policy.normalization == 'casefold_whitespace' else text
        if normalize(value) not in {normalize(choice) for choice in policy.choices}:
            return 'FAIL', 'UNREGISTERED_CHOICE'
    return 'PASS', 'VALID_VALUE'


def apply_field_checks(report, profile):
    checks = validate_field_checks(profile)
    for key, definition in checks.items():
        value = report.get('normalized', {}).get(key)
        field = report.setdefault('fields', {}).setdefault(key, {
            'raw_value': copy.deepcopy(report.get('original_raw', {}).get(key)),
            'normalized_value': copy.deepcopy(value), 'status': 'SKIPPED', 'issues': []})
        status, reason = evaluate_field(value, definition)
        # Additional checks cannot erase a native failure or uncertainty.
        if field.get('status') in {'FAIL', 'ERROR', 'REVIEW'} or any(issue.get('severity') in {'FAIL', 'ERROR', 'REVIEW'} for issue in field.get('issues', [])):
            status, reason = 'FAIL', 'PRIOR_VALIDATION_UNRESOLVED'
        field['status'] = status
        field['data_check'] = {'policy': copy.deepcopy(definition), 'reason': reason}
        if status == 'FAIL':
            field['issues'] = [*field.get('issues', []), {'code': reason, 'severity': 'FAIL'}]
    if checks:
        failed = any(report['fields'][key]['status'] == 'FAIL' for key in checks)
        report['data_validation'] = {'status': 'FAIL' if failed else 'PASS', 'checked_fields': list(checks),
                                     'scope': 'configured_data_checks_only'}
        if failed and report['status'] != 'SKIPPED':
            report['status'] = 'FAIL'
    return report
