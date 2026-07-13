from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db import (
    BASE_DIR,
    DATABASE_URL,
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


def _default_database_url() -> str:
    return DATABASE_URL


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _rows_as_dicts(session: Session, model) -> list[dict]:
    return [dict(row.__dict__, _sa_instance_state=None) for row in session.scalars(select(model))]


def export_tables(database_url: str, output_dir: Path, models: Iterable = TABLE_MODELS) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
    )
    counts: dict[str, int] = {}
    with Session(engine) as session:
        for model in models:
            table_name = model.__tablename__
            rows = _rows_as_dicts(session, model)
            for row in rows:
                row.pop("_sa_instance_state", None)
            df = pd.DataFrame(rows, columns=[column.name for column in model.__table__.columns])
            df.to_csv(output_dir / f"{table_name}.csv", index=False)
            counts[table_name] = len(df)
    engine.dispose()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Export database tables to timestamped CSV backups.")
    parser.add_argument(
        "--database-url",
        default=_default_database_url(),
        help="SQLAlchemy database URL. Defaults to the local SQLite DB.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BASE_DIR / "backups" / f"db_csv_backup_{_timestamp()}",
        help="Directory where backup CSV files will be written.",
    )
    args = parser.parse_args()

    database_url = args.database_url
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    counts = export_tables(database_url, args.output_dir)
    print(f"Backup written to: {args.output_dir}")
    for table_name, count in counts.items():
        print(f"{table_name}: {count}")


if __name__ == "__main__":
    main()
