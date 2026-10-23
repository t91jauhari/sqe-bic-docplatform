"""Seed approved spellings without changing canonical bank choices or prompts."""
from .configuration.publication import persist_revision

import copy

DEFAULTS = {'religion': {'KATHOLIK': 'Katolik', 'BUDHA': 'Buddha'}}
RELEASE = 'enum-raw-fallback-v1'


def apply_requested_aliases(report, doc, profile):
    """Honor an audited, explicit revalidation request without another extraction."""
    state = getattr(doc, 'provider_state', {})
    if 'normalization_enum_aliases' not in state:
        return report
    policy = copy.deepcopy(profile['policy'])
    policy['enum_aliases'] = copy.deepcopy(state['normalization_enum_aliases'])
    policy['enum_raw_fallback_fields'] = copy.deepcopy(state.get('normalization_enum_raw_fallback_fields', []))
    validate_aliases(policy)
    aliases = policy['enum_aliases']
    fallback = policy['enum_raw_fallback_fields']
    for key in sorted(set(aliases) | set(fallback)):
        if key not in report['fields']:
            raise ValueError('Requested enum policy references a field absent from the extraction report.')
        before = report['normalized'].get(key)
        value = before.strip() if isinstance(before, str) else None
        canonical = next((choice for choice in policy.get(key + '_values', []) if value and choice.strip().casefold() == value.casefold()), None)
        alias = next((target for spelling, target in aliases.get(key, {}).items() if value and spelling.strip().casefold() == value.casefold()), None) if canonical is None else None
        normalized = canonical or alias or (value if value and key in fallback else None)
        status = 'PASS' if canonical or alias else 'REVIEW' if value else 'FAIL'
        field = report['fields'][key]
        field['normalized_value'] = normalized
        field['status'] = status
        field['issues'] = [] if status == 'PASS' else [{'code': 'UNRECOGNIZED_ENUM' if value else 'MISSING_ENUM', 'severity': status}]
        report['normalized'][key] = normalized
        if normalized != before or (value and not (canonical or alias)):
            report['corrections'].append({'field': key, 'before': before, 'after': normalized,
                'method': 'approved_enum_alias' if alias else 'case_insensitive_exact_enum' if canonical else 'unrecognized_enum_raw_fallback',
                'review_required': status != 'PASS'})
    report['normalization'] = {'status': 'EXPLICIT_ENUM_ALIAS_POLICY', 'handled_by': 'audited_revalidation',
                               'source_config_id': state.get('normalization_source_config_id')}
    return report


def validate_aliases(policy):
    fallback = policy.get('enum_raw_fallback_fields', ['religion'])
    if not isinstance(fallback, list) or any(v not in {'gender', 'blood_type', 'religion', 'marital_status', 'citizenship'} for v in fallback):
        raise ValueError('Invalid enum raw fallback fields')
    aliases = policy.get('enum_aliases', {})
    fields = {'gender', 'blood_type', 'religion', 'marital_status', 'citizenship'}
    if not isinstance(aliases, dict) or set(aliases) - fields:
        raise ValueError('enum_aliases must map supported enum fields')
    for field, mapping in aliases.items():
        values = policy.get(field + '_values', [])
        if not isinstance(mapping, dict) or any(not isinstance(a, str) or not a.strip() or b not in values for a, b in mapping.items()) or len({a.strip().casefold() for a in mapping}) != len(mapping):
            raise ValueError('Invalid enum alias spelling or canonical target')
        if any(any(a.strip().casefold() == v.strip().casefold() and b != v for v in values) for a, b in mapping.items()):
            raise ValueError('Aliases cannot remap canonical enum values')


def upgrade_payload(payload):
    result = copy.deepcopy(payload)
    profiles = [result['profiles']['ektp']]
    profiles += [v['profile'] for v in result.get('profile_variants', {}).get('ektp', {}).values()]
    for profile in profiles:
        policy = profile['policy']
        policy.setdefault('enum_raw_fallback_fields', ['religion'])
        aliases = policy.setdefault('enum_aliases', {})
        for field, mapping in DEFAULTS.items():
            bank = aliases.setdefault(field, {})
            for source, target in mapping.items():
                if target in policy.get(field + '_values', []) and source.casefold() not in {s.casefold() for s in bank}:
                    bank[source] = target
    result.setdefault('seed_releases', []).append(RELEASE)
    return result


def seed_enum_aliases():
    from sqlalchemy import select, text
    from .db import Config, SessionLocal
    from .domain import latest_config, audit
    with SessionLocal.begin() as db:
        if db.bind.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(730308)'))
        elif db.bind.dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        for org in db.scalars(select(Config.org).distinct()).all():
            old = latest_config(db, org)
            if RELEASE in old.payload.get('seed_releases', []):
                continue
            persist_revision(db, Config(org=org, version=old.version+1, payload=upgrade_payload(old.payload), published_by='system.enum-aliases-v1'))
            audit(db, org, 'system', 'configuration.enum_aliases_seeded', None, previous_version=old.version)
