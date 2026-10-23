"""Lossless compatibility storage for immutable configuration publications.

Independent metadata deliberately prevents application startup from creating or
activating these tables. The caller owns migrations and transaction boundaries.
"""

import copy
import uuid

from .codec import fingerprint

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    declared_attr,
)


class ConfigurationBase(DeclarativeBase):
    pass


class ContextDefinitionRecord(ConfigurationBase):
    __tablename__ = "configuration_context_definitions"
    __table_args__ = (UniqueConstraint("publication_id", "position"),)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("configuration_publications.id"), primary_key=True
    )
    context_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(JSON)


class Publication(ConfigurationBase):
    __tablename__ = "configuration_publications"
    __table_args__ = (UniqueConstraint("organization", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization: Mapped[str] = mapped_column(String(80), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    source_config_id: Mapped[str] = mapped_column(String(36))
    digest: Mapped[str] = mapped_column(String(64))
    # Unmodeled extensions remain lossless while consumers migrate gradually.
    extensions: Mapped[dict] = mapped_column(JSON)


class ConfigurationEntry(ConfigurationBase):
    __tablename__ = "configuration_entries"
    __table_args__ = (UniqueConstraint("publication_id", "section", "entry_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("configuration_publications.id"), index=True
    )
    section: Mapped[str] = mapped_column(String(80))
    entry_key: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    value: Mapped[dict] = mapped_column(JSON)


class EntityRevision:
    """Publication-owned entity identity, ordering and lossless typed definition."""

    publication_id: Mapped[str] = mapped_column(
        ForeignKey("configuration_publications.id"), primary_key=True
    )
    entry_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    value: Mapped[dict] = mapped_column(JSON)

    @declared_attr.directive
    def __table_args__(cls):
        return (
            UniqueConstraint("publication_id", "position"),
            CheckConstraint("position >= 0"),
        )


class FamilyRecord(EntityRevision, ConfigurationBase):
    __tablename__ = "configuration_families"


class ProfileRecord(EntityRevision, ConfigurationBase):
    __tablename__ = "configuration_profiles"


class ProfileVariantRecord(EntityRevision, ConfigurationBase):
    __tablename__ = "configuration_profile_variants"


class FlowRecord(EntityRevision, ConfigurationBase):
    __tablename__ = "configuration_flows"


class ReportDefinitionRecord(EntityRevision, ConfigurationBase):
    __tablename__ = "configuration_report_definitions"


class SOPRuleRecord(EntityRevision, ConfigurationBase):
    __tablename__ = "configuration_sop_rules"


class GenericSOPRuleRecord(EntityRevision, ConfigurationBase):
    __tablename__ = "configuration_generic_sop_rules"


class IdentityPolicyRecord(ConfigurationBase):
    __tablename__ = "configuration_identity_policies"
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("configuration_publications.id"), primary_key=True
    )
    settings: Mapped[dict] = mapped_column(JSON)


class IdentityBindingRecord(ConfigurationBase):
    __tablename__ = "configuration_identity_bindings"
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("configuration_identity_policies.publication_id"), primary_key=True
    )
    profile: Mapped[str] = mapped_column(String(80), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(JSON)


class FamilyRuleScopeRecord(ConfigurationBase):
    __tablename__ = "configuration_family_rule_scopes"
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("configuration_publications.id"), primary_key=True
    )
    family: Mapped[str] = mapped_column(String(80), primary_key=True)


class FamilyRuleMemberRecord(ConfigurationBase):
    __tablename__ = "configuration_family_rule_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["publication_id", "family"],
            [
                "configuration_family_rule_scopes.publication_id",
                "configuration_family_rule_scopes.family",
            ],
        ),
        UniqueConstraint("publication_id", "family", "position"),
    )
    publication_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    family: Mapped[str] = mapped_column(String(80), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)


# Structural sections only: no family names, field paths or business rules.
MAPPING_SECTIONS = (
    "document_families",
    "profiles",
    "profile_variants",
    "templates",
    "report_definitions",
)
LIST_SECTIONS = ("sop_rules", "generic_sop_rules")
ENTITY_SECTIONS = dict(
    zip(
        MAPPING_SECTIONS + LIST_SECTIONS,
        (
            FamilyRecord,
            ProfileRecord,
            ProfileVariantRecord,
            FlowRecord,
            ReportDefinitionRecord,
            SOPRuleRecord,
            GenericSOPRuleRecord,
        ),
    )
)


def import_publication(
    session: Session,
    *,
    organization: str,
    revision: int,
    source_config_id: str,
    payload: dict,
    storage_version: int = 2,
) -> Publication:
    """Import once, reject revision rewrites, never commit or activate."""
    if not organization.strip() or revision < 1 or not isinstance(payload, dict):
        raise ValueError("Organization, positive revision and object payload required.")
    if storage_version not in {1, 2}:
        raise ValueError("Unsupported configuration storage version.")
    digest = fingerprint(payload)
    existing = session.scalar(
        select(Publication).where(
            Publication.organization == organization,
            Publication.revision == revision,
        )
    )
    if existing:
        if existing.digest != digest or existing.source_config_id != source_config_id:
            raise ValueError("An imported revision cannot be replaced.")
        compile_publication(session, existing)
        return existing
    extensions = copy.deepcopy(payload)
    if "report_definitions" in payload:
        from .reporting import validate_report_definitions

        validate_report_definitions(payload)
    contexts = None
    if "context_definitions" in payload:
        from .contexts import validate_definitions

        validate_definitions(payload)
        contexts = copy.deepcopy(payload["context_definitions"])
        extensions["context_definitions"] = {}
    if "generic_sop_rules" in payload:
        from .generic_sop import validate_generic_rules

        validate_generic_rules(payload)
    scope = None
    if "rule_scope" in payload:
        from .rule_scope import validate_rule_scope

        scope = validate_rule_scope(payload)
        extensions.pop("rule_scope")
    identity = extensions.pop("identity_policy", None)
    if "identity_policy" in payload:
        from .identity import IdentityPolicy, validate_bindings

        validate_bindings(
            IdentityPolicy.model_validate(identity), payload.get("profiles", {})
        )
    entries = []
    for section in MAPPING_SECTIONS + LIST_SECTIONS:
        if section not in extensions:
            continue
        values = extensions[section]
        if section in MAPPING_SECTIONS:
            if not isinstance(values, dict):
                raise ValueError(f"{section} must be an object.")
            rows = list(values.items())
        else:
            if not isinstance(values, list):
                raise ValueError(f"{section} must be a list.")
            rows = [(str(index), value) for index, value in enumerate(values)]
        for position, (key, value) in enumerate(rows):
            if not isinstance(value, dict):
                raise ValueError(f"{section}.{key} must be an object.")
            entries.append((section, key, position, value))
        # Retain empty containers to distinguish absent sections from empty ones.
        extensions[section] = {} if section in MAPPING_SECTIONS else []
    publication = Publication(
        id=str(uuid.uuid4()),
        organization=organization,
        revision=revision,
        source_config_id=source_config_id,
        digest=digest,
        extensions=extensions,
        schema_version=storage_version,
    )
    session.add(publication)
    session.flush()
    if contexts is not None:
        for position, (key, definition) in enumerate(contexts.items()):
            session.add(
                ContextDefinitionRecord(
                    publication_id=publication.id,
                    context_key=key,
                    position=position,
                    definition=definition,
                )
            )
    if scope is not None:
        for family in scope.family_rule_ids:
            session.add(
                FamilyRuleScopeRecord(publication_id=publication.id, family=family)
            )
        session.flush()
        for family, rule_ids in scope.family_rule_ids.items():
            for position, rule_id in enumerate(rule_ids):
                session.add(
                    FamilyRuleMemberRecord(
                        publication_id=publication.id,
                        family=family,
                        rule_id=rule_id,
                        position=position,
                    )
                )
    if identity is not None:
        settings = {
            key: copy.deepcopy(value)
            for key, value in identity.items()
            if key != "bindings"
        }
        session.add(
            IdentityPolicyRecord(publication_id=publication.id, settings=settings)
        )
        session.flush()
        for position, binding in enumerate(identity["bindings"]):
            session.add(
                IdentityBindingRecord(
                    publication_id=publication.id,
                    profile=binding["profile"],
                    position=position,
                    definition=copy.deepcopy(binding),
                )
            )
    for section, key, position, value in entries:
        if storage_version == 1:
            session.add(
                ConfigurationEntry(
                    id=str(uuid.uuid4()),
                    publication_id=publication.id,
                    section=section,
                    entry_key=key,
                    position=position,
                    value=value,
                )
            )
        else:
            session.add(
                ENTITY_SECTIONS[section](
                    publication_id=publication.id,
                    entry_key=key,
                    position=position,
                    value=value,
                )
            )
    session.flush()
    compile_publication(session, publication)
    return publication


def compile_publication(session: Session, publication: Publication) -> dict:
    """Reconstruct the legacy contract and detect accidental persisted changes."""
    payload = copy.deepcopy(publication.extensions)
    if publication.schema_version not in {1, 2}:
        raise ValueError("Unsupported persisted configuration storage version.")
    if "context_definitions" in payload:
        payload["context_definitions"] = {
            row.context_key: copy.deepcopy(row.definition)
            for row in session.scalars(
                select(ContextDefinitionRecord)
                .where(ContextDefinitionRecord.publication_id == publication.id)
                .order_by(ContextDefinitionRecord.position)
            )
        }
    scopes = session.scalars(
        select(FamilyRuleScopeRecord).where(
            FamilyRuleScopeRecord.publication_id == publication.id,
        )
    ).all()
    if scopes:
        membership = {row.family: [] for row in scopes}
        for row in session.scalars(
            select(FamilyRuleMemberRecord)
            .where(
                FamilyRuleMemberRecord.publication_id == publication.id,
            )
            .order_by(FamilyRuleMemberRecord.family, FamilyRuleMemberRecord.position)
        ):
            membership[row.family].append(row.rule_id)
        payload["rule_scope"] = {"family_rule_ids": membership}
    identity = session.get(IdentityPolicyRecord, publication.id)
    if identity is not None:
        settings = copy.deepcopy(identity.settings)
        settings["bindings"] = [
            copy.deepcopy(binding.definition)
            for binding in session.scalars(
                select(IdentityBindingRecord)
                .where(IdentityBindingRecord.publication_id == publication.id)
                .order_by(IdentityBindingRecord.position)
            )
        ]
        payload["identity_policy"] = settings
    entries = []
    if publication.schema_version == 1:
        entries = [
            (entry.section, entry)
            for entry in session.scalars(
                select(ConfigurationEntry)
                .where(
                    ConfigurationEntry.publication_id == publication.id,
                )
                .order_by(ConfigurationEntry.section, ConfigurationEntry.position)
            )
        ]
    else:
        for section, model in ENTITY_SECTIONS.items():
            entries.extend(
                (section, row)
                for row in session.scalars(
                    select(model)
                    .where(model.publication_id == publication.id)
                    .order_by(model.position)
                )
            )
    for section, entry in entries:
        if section in MAPPING_SECTIONS:
            payload[section][entry.entry_key] = copy.deepcopy(entry.value)
        elif section in LIST_SECTIONS:
            payload[section].append(copy.deepcopy(entry.value))
        else:
            raise ValueError("Unknown persisted configuration section.")
    if fingerprint(payload) != publication.digest:
        raise ValueError("Configuration integrity check failed.")
    return payload
