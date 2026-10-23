"""Versioned, profile-scoped guidance saved from field reprocessing."""
from .configuration.publication import persist_revision

import copy
import hashlib
from sqlalchemy import text
from .db import Config
from .domain import audit, latest_config, validate_config
from .extraction_prompts import system_instruction


def locked_latest_config(db, org):
    # Serialize all interactive publishers for the organization before reading
    # latest, rather than locking a version which may already have been replaced.
    if db.bind.dialect.name == 'postgresql':
        lock = int.from_bytes(hashlib.sha256(('profile-config:' + org).encode()).digest()[:8], 'big', signed=True)
        db.execute(text('SELECT pg_advisory_xact_lock(:lock)'), {'lock': lock})
    return latest_config(db, org)


def append_profile_guidance(db, config, doc, fields, instruction, user):
    payload = copy.deepcopy(config.payload)
    profile = payload['profiles'][doc.doc_type]
    scope = ', '.join(sorted(fields))
    block = f'Reusable extraction guidance (fields: {scope}):\n{instruction.strip()}'
    existing = system_instruction(profile).rstrip()
    if ('\n\n'+block+'\n\n') in ('\n\n'+existing+'\n\n'):
        return config, False
    profile['system_instruction'] = existing + '\n\n' + block
    validate_config(payload)
    saved = Config(org=user.org, version=config.version + 1, payload=payload, published_by=user.id)
    persist_revision(db, saved)
    audit(db, user.org, user.id, 'config.profile_guidance_appended', doc.branch_id, doc.case_id,
          document_id=doc.id, profile=doc.doc_type, fields=fields,
          version=saved.version, previous_version=config.version)
    return saved, True
