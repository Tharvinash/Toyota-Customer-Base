from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db import (
    BASE_DIR,
    DEFAULT_SQLITE_PATH,
    Base,
    CompetitorBPOutlet,
    CustomerCell,
    NonDealerWorkshop,
    ToyotaBPOutlet,
    ToyotaServiceOutlet,
    TrafficPoliceStation,
)
from scripts.export_db_csv_backup import export_tables


TABLE_MODELS = [
    ToyotaServiceOutlet,
    ToyotaBPOutlet,
    NonDealerWorkshop,
    CompetitorBPOutlet,
    TrafficPoliceStation,
    CustomerCell,
]


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def default_sqlite_url() -> str:
    return f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def make_engine(database_url: str):
    database_url = normalize_database_url(database_url)
    return create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
        pool_pre_ping=not database_url.startswith("sqlite"),
    )


def table_count(session: Session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def read_table_rows(session: Session, model) -> list[dict]:
    rows = []
    columns = [column.name for column in model.__table__.columns]
    for item in session.scalars(select(model).order_by(model.id)):
        rows.append({column: getattr(item, column) for column in columns})
    return rows


def reset_postgres_sequence(session: Session, model) -> None:
    table_name = model.__tablename__
    session.execute(
        text(
            "SELECT setval("
            "pg_get_serial_sequence(:table_name, 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table_name}), 1), "
            f"(SELECT MAX(id) FROM {table_name}) IS NOT NULL"
            ")"
        ),
        {"table_name": table_name},
    )


def migrate(source_url: str, target_url: str, replace_target: bool) -> dict[str, dict[str, int]]:
    source_engine = make_engine(source_url)
    target_engine = make_engine(target_url)
    Base.metadata.create_all(bind=target_engine)

    report: dict[str, dict[str, int]] = {}
    try:
        with Session(source_engine) as source_session, Session(target_engine) as target_session:
            target_counts = {
                model.__tablename__: table_count(target_session, model) for model in TABLE_MODELS
            }
            non_empty_targets = {
                table_name: count for table_name, count in target_counts.items() if count > 0
            }
            if non_empty_targets and not replace_target:
                details = ", ".join(
                    f"{table_name}={count}" for table_name, count in non_empty_targets.items()
                )
                raise RuntimeError(
                    "Target database already has data. Re-run with --replace-target "
                    f"after confirming you have a backup. Existing rows: {details}"
                )

            if replace_target:
                for model in reversed(TABLE_MODELS):
                    target_session.query(model).delete()
                target_session.flush()

            for model in TABLE_MODELS:
                table_name = model.__tablename__
                rows = read_table_rows(source_session, model)
                if rows:
                    target_session.bulk_insert_mappings(model, rows)
                inserted_count = table_count(target_session, model)
                source_count = len(rows)
                report[table_name] = {
                    "source_count": source_count,
                    "target_count": inserted_count,
                }
                if source_count != inserted_count:
                    raise RuntimeError(
                        f"Count mismatch for {table_name}: source={source_count}, "
                        f"target={inserted_count}"
                    )

            if target_engine.dialect.name == "postgresql":
                for model in TABLE_MODELS:
                    reset_postgres_sequence(target_session, model)

            target_session.commit()
    except Exception:
        target_engine.dispose()
        source_engine.dispose()
        raise

    target_engine.dispose()
    source_engine.dispose()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate the local SQLite app database into PostgreSQL."
    )
    parser.add_argument(
        "--source-database-url",
        default=default_sqlite_url(),
        help="Source SQLAlchemy URL. Defaults to data/selangor_map.db.",
    )
    parser.add_argument(
        "--target-database-url",
        default=os.getenv("POSTGRES_DATABASE_URL") or os.getenv("DATABASE_URL"),
        help="Target PostgreSQL URL. Can also be set with POSTGRES_DATABASE_URL.",
    )
    parser.add_argument(
        "--replace-target",
        action="store_true",
        help="Delete existing rows in target tables before migration.",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=BASE_DIR / "backups" / f"pre_postgres_migration_{timestamp()}",
        help="CSV backup directory for the source database.",
    )
    args = parser.parse_args()

    if not args.target_database_url:
        raise SystemExit(
            "Missing target database URL. Pass --target-database-url or set POSTGRES_DATABASE_URL."
        )

    target_url = normalize_database_url(args.target_database_url)
    if not target_url.startswith("postgresql://"):
        raise SystemExit("Target database URL must be PostgreSQL.")

    print("Creating source CSV backup before migration...")
    backup_counts = export_tables(args.source_database_url, args.backup_dir)
    print(f"Backup written to: {args.backup_dir}")
    for table_name, count in backup_counts.items():
        print(f"backup {table_name}: {count}")

    print("Migrating SQLite data into PostgreSQL...")
    report = migrate(args.source_database_url, target_url, args.replace_target)
    print("Migration validation passed.")
    for table_name, counts in report.items():
        print(
            f"{table_name}: source={counts['source_count']} "
            f"target={counts['target_count']}"
        )


if __name__ == "__main__":
    main()
