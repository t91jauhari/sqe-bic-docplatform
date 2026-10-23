"""Isolated migration rehearsal. Requires an explicitly named restored database.

Imports restored configuration revisions into the new tables, verifies exact
round trips twice, and checks that original configuration/case rows are unchanged.
Never run this as application startup or against the live database.
"""
import argparse
import json
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .migrate import apply_migrations
from .store import compile_publication, import_publication


def source_snapshot(connection):
    return {
        name: connection.scalar(text(
            f"SELECT md5(COALESCE(jsonb_agg(to_jsonb(t) ORDER BY id)::text, '[]')) "
            f"FROM {name} t"
        )) for name in ("configurations", "cases")
    }


def rehearse(engine, expected_database):
    with engine.connect() as connection:
        if connection.scalar(text("SELECT current_database()")) != expected_database:
            raise ValueError("Unexpected database.")
        before = source_snapshot(connection)
    first = apply_migrations(engine, expected_database=expected_database)
    second = apply_migrations(engine, expected_database=expected_database)
    if second:
        raise AssertionError("Migration replay was not idempotent.")
    with Session(engine) as session, session.begin():
        records = session.execute(text(
            "SELECT id,org,version,payload FROM configurations ORDER BY org,version"
        )).mappings().all()
        if not records:
            raise ValueError("Restored configuration history is empty.")
        for _ in range(2):
            for record in records:
                publication = import_publication(
                    session, organization=record["org"], revision=record["version"],
                    source_config_id=record["id"], payload=record["payload"],
                )
                if compile_publication(session, publication) != record["payload"]:
                    raise AssertionError("Configuration round-trip mismatch.")
    with engine.connect() as connection:
        if source_snapshot(connection) != before:
            raise AssertionError("Original configuration or case rows changed.")
        count = connection.scalar(text("SELECT count(*) FROM configuration_publications"))
    return {"migrations_applied": first, "replay_applied": second,
            "source_revisions_checked": len(records), "publications": count,
            "source_rows_unchanged": True, "activated": False}


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
