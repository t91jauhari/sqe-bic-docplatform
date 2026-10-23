"""Explicit PostgreSQL-only configuration migrations; never called at startup.

Connection URL is supplied through REFACTOR_DATABASE_URL, never command arguments
or logs. --expected-database prevents accidentally targeting the wrong database.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text


MIGRATIONS = Path(__file__).with_name("migrations")


def apply_migrations(engine, *, expected_database: str) -> list[str]:
    if engine.dialect.name != "postgresql":
        raise ValueError("Configuration schema migrations require PostgreSQL.")
    if not expected_database:
        raise ValueError("Expected database name is required.")
    applied = []
    with engine.begin() as connection:
        actual = connection.scalar(text("SELECT current_database()"))
        if actual != expected_database:
            raise ValueError("Connected database does not match the explicit target.")
        connection.execute(text("SELECT pg_advisory_xact_lock(730310)"))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS configuration_schema_migrations (
                version VARCHAR(120) PRIMARY KEY,
                checksum VARCHAR(64) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        files = sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql"))
        known = {row.version: row.checksum for row in connection.execute(text(
            "SELECT version, checksum FROM configuration_schema_migrations"
        ))}
        if set(known) - {path.stem for path in files}:
            raise ValueError("Database has migrations unavailable in this release.")
        for path in files:
            # Stable checksums across Git LF/CRLF checkouts.
            content = path.read_text(encoding="utf-8").encode("utf-8")
            checksum = hashlib.sha256(content).hexdigest()
            if path.stem in known:
                if known[path.stem] != checksum:
                    raise ValueError("Applied migration checksum differs from source.")
                continue
            # Execute trusted versioned SQL as one parameter-free script. Let
            # PostgreSQL parse procedural bodies and quoted semicolons itself.
            connection.exec_driver_sql(content.decode("utf-8"), execution_options={"no_parameters": True})
            connection.execute(text(
                "INSERT INTO configuration_schema_migrations(version,checksum) "
                "VALUES (:version,:checksum)"
            ), {"version": path.stem, "checksum": checksum})
            applied.append(path.stem)
    return applied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-database", required=True)
    args = parser.parse_args()
    url = os.environ.get("REFACTOR_DATABASE_URL")
    if not url:
        parser.error("Set REFACTOR_DATABASE_URL explicitly.")
    engine = create_engine(url)
    try:
        print(json.dumps({"applied": apply_migrations(
            engine, expected_database=args.expected_database,
        )}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
