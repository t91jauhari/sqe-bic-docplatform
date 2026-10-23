"""Dual-publication rehearsal on a restored database, always rolled back."""
import argparse
import json
import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .publication import publish_configuration
from .store import Publication, compile_publication
from .verify_postgres import source_snapshot


def rehearse(engine, expected_database):
    from sqlalchemy import text
    from app.db import Config

    with engine.connect() as connection:
        if connection.scalar(text("SELECT current_database()")) != expected_database:
            raise ValueError("Unexpected database.")
        original = source_snapshot(connection)
        original_publications = connection.scalar(text("SELECT count(*) FROM configuration_publications"))
        original_audits = connection.scalar(text("SELECT count(*) FROM audit"))
    with Session(engine) as session:
        transaction = session.begin()
        try:
            latest = session.scalar(select(Config).order_by(Config.version.desc()).limit(1))
            if latest is None:
                raise ValueError("No restored configuration exists.")
            result = publish_configuration(session, organization=latest.org, actor="publication-rehearsal",
                expected_version=latest.version, payload=latest.payload, storage_mode="dual")
            normalized = session.get(Publication, result["publication_id"])
            if compile_publication(session, normalized) != result["payload"]:
                raise AssertionError("Publication differs from legacy payload.")
            proposed_version = result["version"]
        finally:
            transaction.rollback()
    with engine.connect() as connection:
        if source_snapshot(connection) != original:
            raise AssertionError("Source configuration or cases changed.")
        if connection.scalar(text("SELECT count(*) FROM configuration_publications")) != original_publications:
            raise AssertionError("Rehearsal publication was not rolled back.")
        if connection.scalar(text("SELECT count(*) FROM audit")) != original_audits:
            raise AssertionError("Rehearsal audit was not rolled back.")
    return {"proposed_version": proposed_version, "round_trip_equal": True,
            "rolled_back": True, "original_rows_unchanged": True, "activated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-database", required=True)
    args = parser.parse_args()
    engine = create_engine(os.environ["REFACTOR_DATABASE_URL"])
    try:
        print(json.dumps(rehearse(engine, args.expected_database)))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
