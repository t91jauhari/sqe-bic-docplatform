"""Offline compatibility check: never connects to a database or model provider.

Usage: python -m app.configuration.verify_snapshot /private/configurations.json
Input is a JSON array of {id, org, version, payload} exported from a backup.
Only aggregate counts are printed; payloads can contain sensitive information.
"""
import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .store import ConfigurationBase, compile_publication, import_publication


def verify(records: list[dict]) -> dict:
    engine = create_engine("sqlite://")
    ConfigurationBase.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            for record in records:
                publication = import_publication(
                    session, organization=record["org"], revision=record["version"],
                    source_config_id=record["id"], payload=record["payload"],
                )
                if compile_publication(session, publication) != record["payload"]:
                    raise ValueError("Historical configuration round-trip mismatch.")
            session.rollback()
        return {"checked": len(records), "mismatches": 0, "activated": False}
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    records = json.loads(args.snapshot.read_text(encoding="utf-8-sig"))
    if not isinstance(records, list) or not records:
        raise ValueError("A nonempty configuration snapshot array is required.")
    print(json.dumps(verify(records)))


if __name__ == "__main__":
    main()
