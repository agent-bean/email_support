"""Initialize checkpoint tables only on a verified owned test database."""

import argparse
import asyncio
import sys
from pathlib import Path

from email_support.storage.postgres.checkpoints import setup_checkpoints

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.test_database import DatabaseLifecycle, run_migrations  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owned-database", required=True)
    args = parser.parse_args()
    lifecycle = DatabaseLifecycle.from_environment()
    database = args.owned_database
    lifecycle.backup_database(database, "before-checkpoint-migration")
    database_url = lifecycle.target_url(database)
    run_migrations(database_url)

    async def backup() -> None:
        await asyncio.to_thread(
            lifecycle.backup_database, database, "before-checkpoint-setup"
        )

    asyncio.run(setup_checkpoints(database_url, backup))
    print("Checkpoint schema initialized on verified owned test target.")


if __name__ == "__main__":
    main()
