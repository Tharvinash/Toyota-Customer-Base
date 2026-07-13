from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Float, Integer, create_engine, func, select, text
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db import (  # noqa: E402
    Base,
    CompetitorBPOutlet,
    CustomerCell,
    NonDealerWorkshop,
    ToyotaBPOutlet,
    ToyotaServiceOutlet,
    TrafficPoliceStation,
)


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


def make_engine(database_url: str):
    database_url = normalize_database_url(database_url)
    return create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
        pool_pre_ping=not database_url.startswith("sqlite"),
    )


def clean_value(value: Any, column) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

    if isinstance(column.type, Integer):
        return int(float(value))
    if isinstance(column.type, Float):
        return float(value)
    return str(value) if value is not None else None


def load_csv_rows(csv_path: Path, model) -> list[dict[str, Any]]:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    columns = {column.name: column for column in model.__table__.columns}
    rows: list[dict[str, Any]] = []

    for _, source_row in df.iterrows():
        row: dict[str, Any] = {}
        for column_name, column in columns.items():
            if column_name in source_row:
                row[column_name] = clean_value(source_row[column_name], column)
        rows.append(row)

    return rows


def table_count(session: Session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


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


def import_backup(backup_dir: Path, database_url: str, replace_target: bool) -> dict[str, int]:
    engine = make_engine(database_url)
    Base.metadata.create_all(bind=engine)
    report: dict[str, int] = {}

    with Session(engine) as session:
        existing = {
            model.__tablename__: table_count(session, model)
            for model in TABLE_MODELS
        }
        non_empty = {table: count for table, count in existing.items() if count > 0}
        if non_empty and not replace_target:
            details = ", ".join(f"{table}={count}" for table, count in non_empty.items())
            raise RuntimeError(
                "Target database already has data. Re-run with --replace-target "
                f"if you want to replace it. Existing rows: {details}"
            )

        if replace_target:
            for model in reversed(TABLE_MODELS):
                session.query(model).delete()
            session.flush()

        for model in TABLE_MODELS:
            table_name = model.__tablename__
            csv_path = backup_dir / f"{table_name}.csv"
            if not csv_path.exists():
                raise FileNotFoundError(f"Missing backup CSV: {csv_path}")

            rows = load_csv_rows(csv_path, model)
            if rows:
                session.bulk_insert_mappings(model, rows)
            report[table_name] = len(rows)

        if engine.dialect.name == "postgresql":
            for model in TABLE_MODELS:
                reset_postgres_sequence(session, model)

        session.commit()

    engine.dispose()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Import app table CSV backups into a database.")
    parser.add_argument("backup_dir", type=Path, help="Directory containing table CSV backup files.")
    parser.add_argument(
        "--database-url",
        default=os.getenv("POSTGRES_DATABASE_URL") or os.getenv("DATABASE_URL"),
        help="Target SQLAlchemy database URL. Can also be set with POSTGRES_DATABASE_URL.",
    )
    parser.add_argument(
        "--replace-target",
        action="store_true",
        help="Delete existing rows in target tables before importing.",
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("Missing database URL. Pass --database-url or set POSTGRES_DATABASE_URL.")

    report = import_backup(args.backup_dir, args.database_url, args.replace_target)
    print("Import complete.")
    for table_name, count in report.items():
        print(f"{table_name}: {count}")


if __name__ == "__main__":
    main()
