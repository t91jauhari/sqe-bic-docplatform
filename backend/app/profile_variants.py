"""Named prompt candidates; stored snapshots never replace active customer settings."""
from .configuration.publication import persist_revision

import copy
import json
from pathlib import Path

RELEASE = 'enhanced-v1'


def add_variants(payload):
    from .domain import default_config
    result = copy.deepcopy(payload)
    variants = result.setdefault('profile_variants', {})
    proposals = json.loads((Path(__file__).parent / 'config_data/enhanced_profiles_v1.json').read_text(encoding='utf-8'))
    defaults = default_config()['profiles']
    for name, changes in proposals.items():
        bank = variants.setdefault(name, {})
        original = copy.deepcopy(result['profiles'][name])
        original.setdefault('schema', copy.deepcopy(defaults[name]['schema']))
        bank.setdefault('original-v1', {'name': 'Original v1 · saved settings', 'profile': original})
        enhanced = copy.deepcopy(original)
        for field, description in changes['descriptions'].items():
            enhanced['schema']['properties'][field]['description'] = description
        enhanced['system_prompt'] += '\n\n' + changes['system_addition']
        enhanced['parse_prompt'] = changes['parse_prompt']
        bank.setdefault(RELEASE, {'name': 'Enhanced v1 · evidence-focused candidate', 'profile': enhanced})
    return result


def seed_profile_variants():
    """One new immutable configuration per org, serialized across API instances."""
    from sqlalchemy import select, text
    from .db import Config, SessionLocal
    from .domain import audit, latest_config
    with SessionLocal.begin() as db:
        if db.bind.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(730308)'))
        elif db.bind.dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        orgs = db.scalars(select(Config.org).distinct()).all()
        for org in orgs:
            previous = latest_config(db, org)
            payload = add_variants(previous.payload)
            if payload == previous.payload:
                continue
            persist_revision(db, Config(org=org, version=previous.version + 1, payload=payload, published_by='system.enhanced-v1'))
            audit(db, org, 'system', 'configuration.prompt_variants_seeded', None, release=RELEASE, previous_version=previous.version)
