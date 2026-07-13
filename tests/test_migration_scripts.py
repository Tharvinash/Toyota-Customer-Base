from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db import Base, CustomerCell, ToyotaServiceOutlet
from scripts.export_db_csv_backup import export_tables
from scripts.migrate_sqlite_to_postgres import migrate


class MigrationScriptTests(unittest.TestCase):
    def _sqlite_url(self, path: Path) -> str:
        return f"sqlite:///{path.as_posix()}"

    def _seed_source(self, database_url: str) -> None:
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        with Session(engine) as session:
            session.add(
                ToyotaServiceOutlet(
                    id=7,
                    outlet_name="Source Service Centre",
                    city="Shah Alam",
                    state="Selangor",
                    postcode="40000",
                    lat=3.0738,
                    lon=101.5183,
                )
            )
            session.add(
                CustomerCell(
                    id=11,
                    state="Selangor",
                    city="Ampang",
                    postcode="68000",
                    lat=3.16648,
                    lon=101.748344,
                    weight=6265,
                )
            )
            session.commit()
        engine.dispose()

    def test_export_tables_writes_csv_backups(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_url = self._sqlite_url(root / "source.db")
            backup_dir = root / "backup"
            self._seed_source(source_url)

            counts = export_tables(source_url, backup_dir)

            self.assertEqual(counts["toyota_service_outlets"], 1)
            self.assertEqual(counts["customer_cells"], 1)
            service_backup = pd.read_csv(backup_dir / "toyota_service_outlets.csv")
            self.assertEqual(service_backup.loc[0, "outlet_name"], "Source Service Centre")

    def test_migrate_copies_rows_and_preserves_ids(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_url = self._sqlite_url(root / "source.db")
            target_url = self._sqlite_url(root / "target.db")
            self._seed_source(source_url)

            report = migrate(source_url, target_url, replace_target=False)

            self.assertEqual(report["toyota_service_outlets"]["source_count"], 1)
            self.assertEqual(report["toyota_service_outlets"]["target_count"], 1)
            engine = create_engine(target_url, connect_args={"check_same_thread": False})
            with Session(engine) as session:
                service = session.get(ToyotaServiceOutlet, 7)
                customer = session.get(CustomerCell, 11)
                self.assertIsNotNone(service)
                self.assertEqual(service.outlet_name, "Source Service Centre")
                self.assertIsNotNone(customer)
                self.assertEqual(customer.weight, 6265)
            engine.dispose()

    def test_migrate_refuses_to_overwrite_non_empty_target_without_flag(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_url = self._sqlite_url(root / "source.db")
            target_url = self._sqlite_url(root / "target.db")
            self._seed_source(source_url)
            self._seed_source(target_url)

            with self.assertRaisesRegex(RuntimeError, "Target database already has data"):
                migrate(source_url, target_url, replace_target=False)


if __name__ == "__main__":
    unittest.main()
