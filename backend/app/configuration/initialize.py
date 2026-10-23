"""Explicit development bootstrap/legacy upgrades; never invoked by startup."""

import argparse
import json


def initialize_development():
    from app.settings import settings

    if settings.environment != "development":
        raise ValueError("Development initialization requires APP_ENV=development.")
    from app.db import engine

    if engine.dialect.name == "sqlite" and engine.url.database not in {
        None,
        ":memory:",
    }:
        from pathlib import Path

        Path(engine.url.database).expanduser().resolve().parent.mkdir(
            parents=True, exist_ok=True
        )
    from app.configuration.bootstrap import seed
    from app.profile_variants import seed_profile_variants
    from app.enum_aliases import seed_enum_aliases
    from app.transaction_flows import seed_transaction_flows
    from app.account_opening_seed import seed_account_opening
    from app.account_opening_official import seed_official_account_rules
    from app.spider_config import seed_spider
    from app.extraction_quality import seed_quality

    seed()
    for upgrade in (
        seed_profile_variants,
        seed_enum_aliases,
        seed_transaction_flows,
        seed_account_opening,
        seed_official_account_rules,
        seed_spider,
        seed_quality,
    ):
        upgrade()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-database", required=True)
    args = parser.parse_args()
    from app.db import engine

    if engine.url.database != args.expected_database:
        parser.error("Connected database does not match the explicit target.")
    initialize_development()
    print(json.dumps({"initialized": True, "automatic_startup_upgrades": False}))


if __name__ == "__main__":
    main()
