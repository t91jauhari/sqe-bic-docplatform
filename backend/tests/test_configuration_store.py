"""Synthetic-only storage contract tests; no provider or operational database."""

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.configuration.store import (
    ConfigurationBase,
    ConfigurationEntry,
    Publication,
    ProfileRecord,
    GenericSOPRuleRecord,
    FamilyRuleMemberRecord,
    FamilyRuleScopeRecord,
    IdentityBindingRecord,
    IdentityPolicyRecord,
    compile_publication,
    import_publication,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    ConfigurationBase.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def sample():
    return {
        "profiles": {
            "custom": {
                "schema": {"type": "object"},
                "system_prompt": "Visible text only",
            }
        },
        "document_families": {"new_family": {"profiles": ["custom"]}},
        "templates": {},
        "sop_rules": [{"id": "second"}, {"id": "first"}],
        "unknown_future_extension": {"value": [None, "é", 12]},
    }


def load(db, payload=None, organization="test"):
    return import_publication(
        db,
        organization=organization,
        revision=1,
        source_config_id="synthetic",
        payload=sample() if payload is None else payload,
    )


def test_round_trip_preserves_order_extensions_and_empty_sections(db):
    payload = sample()
    publication = load(db, payload)
    assert compile_publication(db, publication) == payload
    assert "profile_variants" not in compile_publication(db, publication)
    assert [r["id"] for r in compile_publication(db, publication)["sop_rules"]] == [
        "second",
        "first",
    ]


def test_idempotent_and_organization_scoped(db):
    first = load(db)
    assert load(db).id == first.id
    assert load(db, organization="other").id != first.id


def test_rewrite_rejected(db):
    load(db)
    with pytest.raises(ValueError, match="cannot be replaced"):
        load(db, {"profiles": {}})


def test_persisted_tampering_detected(db):
    publication = load(db)
    entry = db.scalar(select(ProfileRecord))
    entry.value = {"tampered": True}
    db.flush()
    with pytest.raises(ValueError, match="integrity"):
        compile_publication(db, publication)


def test_caller_controls_rollback(db):
    load(db)
    db.rollback()
    assert db.scalar(select(Publication)) is None


@pytest.mark.parametrize(
    "payload", [{"profiles": []}, {"sop_rules": {}}, {"profiles": {"bad": 1}}]
)
def test_invalid_structure_rejected_before_writes(db, payload):
    with pytest.raises(ValueError):
        load(db, payload)
    assert db.scalar(select(Publication)) is None


def test_returned_payload_does_not_mutate_storage(db):
    publication = load(db)
    compiled = compile_publication(db, publication)
    compiled["profiles"].clear()
    assert "custom" in compile_publication(db, publication)["profiles"]


def test_existing_application_defaults_round_trip(db):
    from app.domain import default_config

    # Match the existing JSON database contract (Python tuples become arrays).
    payload = json.loads(json.dumps(default_config()))
    publication = load(db, payload)
    assert compile_publication(db, publication) == payload


def test_identity_policy_survives_publication(db):
    payload = sample()
    payload["profiles"]["custom"]["schema"]["properties"] = {
        "customer": {"type": "string"}
    }
    payload["identity_policy"] = {
        "comparison": "exact_tokens",
        "bindings": [{"profile": "custom", "field_path": "customer"}],
    }
    publication = load(db, payload)
    assert (
        compile_publication(db, publication)["identity_policy"]
        == payload["identity_policy"]
    )
    assert "identity_policy" not in publication.extensions
    assert db.get(IdentityPolicyRecord, publication.id) is not None
    assert db.scalar(select(IdentityBindingRecord)).profile == "custom"


def test_empty_identity_binding_policy_is_distinct_from_absence(db):
    payload = sample()
    payload["identity_policy"] = {"bindings": []}
    publication = load(db, payload)
    assert compile_publication(db, publication)["identity_policy"] == {"bindings": []}


def test_identity_binding_corruption_detected(db):
    payload = sample()
    payload["profiles"]["custom"]["schema"]["properties"] = {
        "customer": {"type": "string"}
    }
    payload["identity_policy"] = {
        "bindings": [{"profile": "custom", "field_path": "customer"}]
    }
    publication = load(db, payload)
    binding = db.scalar(select(IdentityBindingRecord))
    binding.definition = {"profile": "custom", "field_path": "supplier"}
    db.flush()
    with pytest.raises(ValueError, match="integrity"):
        compile_publication(db, publication)


def test_family_rule_membership_is_stored_separately(db):
    payload = sample()
    payload["rule_scope"] = {
        "family_rule_ids": {
            "forex": ["first", "second"],
            "account_opening": [],
            "new_family": ["second"],
        }
    }
    publication = load(db, payload)
    assert "rule_scope" not in publication.extensions
    assert len(db.scalars(select(FamilyRuleScopeRecord)).all()) == 3
    assert len(db.scalars(select(FamilyRuleMemberRecord)).all()) == 3
    assert compile_publication(db, publication) == payload
    assert load(db, payload).id == publication.id


def test_family_membership_tampering_detected(db):
    payload = sample()
    payload["rule_scope"] = {
        "family_rule_ids": {
            "forex": ["first"],
            "account_opening": [],
            "new_family": [],
        }
    }
    publication = load(db, payload)
    db.delete(db.scalar(select(FamilyRuleMemberRecord)))
    db.flush()
    with pytest.raises(ValueError, match="integrity"):
        compile_publication(db, publication)


def test_generic_rules_are_stored_as_entries(db):
    payload = sample()
    payload["profiles"]["custom"]["schema"]["properties"] = {
        "name": {"type": "string"},
        "other_name": {"type": "string"},
    }
    payload["generic_sop_rules"] = [
        {
            "id": "generic_rule",
            "label": "Configured comparison",
            "families": ["new_family"],
            "policy": {"left": "custom.name", "right": "custom.other_name"},
        }
    ]
    publication = load(db, payload)
    assert publication.extensions["generic_sop_rules"] == []
    assert db.scalar(select(GenericSOPRuleRecord)) is not None
    assert compile_publication(db, publication) == payload


def test_legacy_and_entity_publications_remain_readable_together(db):
    legacy = import_publication(
        db,
        organization="legacy",
        revision=1,
        source_config_id="legacy",
        payload=sample(),
        storage_version=1,
    )
    current = load(db)
    assert legacy.schema_version == 1 and current.schema_version == 2
    assert (
        compile_publication(db, legacy) == compile_publication(db, current) == sample()
    )
    assert (
        db.scalar(
            select(ConfigurationEntry).where(
                ConfigurationEntry.publication_id == current.id
            )
        )
        is None
    )
    assert (
        db.scalar(
            select(ProfileRecord).where(ProfileRecord.publication_id == current.id)
        )
        is not None
    )
