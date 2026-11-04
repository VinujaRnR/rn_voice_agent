#!/usr/bin/env python3
"""
CLI runner for SQLite to MySQL 8.4 data migration.
Usage:
    python scripts/migrate_sqlite_to_mysql.py --dry-run
    python scripts/migrate_sqlite_to_mysql.py --db voice_assistant.db --devices data/devices.json
"""

import argparse
import asyncio
import json
import logging
import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.migrations.sqlite_to_mysql_migrator import SQLiteToMySQLMigrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("migration_cli")


def parse_args():
    parser = argparse.ArgumentParser(description="Migrate RN Voice Agent SQLite data to MySQL 8.4")
    parser.add_argument("--db", default="voice_assistant.db", help="Path to SQLite database file")
    parser.add_argument("--devices", default="data/devices.json", help="Path to devices.json file")
    parser.add_argument("--dry-run", action="store_true", help="Perform validation and transformation without committing")
    parser.add_argument("--quarantine", action="store_true", default=True, help="Quarantine records with invalid/missing owners")
    return parser.parse_args()


async def main():
    args = parse_args()
    logger.info("Initializing SQLite to MySQL 8.4 migrator...")
    logger.info(f"Source SQLite: {args.db}")
    logger.info(f"Source Devices: {args.devices}")
    logger.info(f"Dry Run: {args.dry_run}")

    migrator = SQLiteToMySQLMigrator(
        sqlite_db_path=args.db,
        json_devices_path=args.devices,
        dry_run=args.dry_run,
        quarantine_unverified=args.quarantine
    )

    inv = migrator.inventory()
    logger.info(f"Pre-migration Inventory: {json.dumps(inv, indent=2)}")

    report = await migrator.run_migration()
    report_dict = report.to_dict()
    logger.info("=" * 60)
    logger.info("MIGRATION REPORT SUMMARY:")
    logger.info(json.dumps(report_dict, indent=2))
    logger.info("=" * 60)

    if report.errors:
        logger.error(f"Migration completed with {len(report.errors)} errors.")
        sys.exit(1)
    else:
        logger.info("Migration completed successfully with 0 errors!")


if __name__ == "__main__":
    asyncio.run(main())
