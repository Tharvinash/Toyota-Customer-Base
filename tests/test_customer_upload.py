from __future__ import annotations

import asyncio
import html as html_lib
from io import BytesIO
import unittest

import pandas as pd
from starlette.datastructures import UploadFile
from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import (
    Base,
    CompetitorBPOutlet,
    CustomerCell,
    NonDealerWorkshop,
    ToyotaBPOutlet,
    ToyotaServiceOutlet,
    TrafficPoliceStation,
)
from main import _customer_upload_summary, _prepare_customer_upload_rows, CSV_UPLOAD_CONFIGS
from main import upload_customers_csv


class CustomerUploadTests(unittest.TestCase):
    def test_prepare_customer_upload_rows_normalizes_full_state_names_and_numbers(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "state": "Kuala Lumpur",
                    "city": "Pandan Indah",
                    "postcode": "55100",
                    "lat": "3.133892",
                    "lon": "101.7516751",
                    "weight": "3,210",
                },
                {
                    "state": "Selangor",
                    "city": "Kajang",
                    "postcode": "43000",
                    "lat": "2.993518",
                    "lon": "101.787407",
                    "weight": "10449",
                },
            ]
        )

        rows, errors = _prepare_customer_upload_rows(df)

        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["state"], "Kuala Lumpur")
        self.assertEqual(rows[0]["weight"], 3210.0)
        self.assertEqual(rows[1]["state"], "Selangor")
        self.assertEqual(rows[1]["weight"], 10449.0)

        summary = _customer_upload_summary(previous_count=168, prepared_rows=rows)
        self.assertEqual(summary["new_count"], 2)
        self.assertEqual(summary["rows_replaced"], 168)
        self.assertEqual(summary["states"], ["Kuala Lumpur", "Selangor"])
        self.assertEqual(summary["total_weight_text"], "13,659")

    def test_prepare_customer_upload_rows_rejects_state_codes(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "state": "KUL",
                    "city": "Pandan Indah",
                    "postcode": "55100",
                    "lat": "3.133892",
                    "lon": "101.7516751",
                    "weight": "3210",
                }
            ]
        )

        rows, errors = _prepare_customer_upload_rows(df)

        self.assertEqual(rows, [])
        self.assertEqual(
            errors,
            [
                "Line 2: state must be a full Malaysian state or federal "
                "territory name, got 'KUL'."
            ],
        )

    def test_prepare_customer_upload_rows_reports_line_level_errors(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "state": "Kuala Lumpur",
                    "city": "Dang Wangi",
                    "postcode": "50560",
                    "lat": "Not",
                    "lon": "Found",
                    "weight": "675",
                }
            ]
        )

        rows, errors = _prepare_customer_upload_rows(df)

        self.assertEqual(rows, [])
        self.assertTrue(errors)
        self.assertIn("Line 2: lat must be numeric", errors[0])

    def test_prepare_customer_upload_rows_rejects_empty_csv(self) -> None:
        df = pd.DataFrame(columns=["state", "city", "postcode", "lat", "lon", "weight"])

        rows, errors = _prepare_customer_upload_rows(df)

        self.assertEqual(rows, [])
        self.assertEqual(errors, ["The CSV has no data rows."])

    def test_prepare_customer_upload_rows_rejects_coordinates_outside_malaysia(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "state": "Selangor",
                    "city": "Tropicana",
                    "postcode": "47410",
                    "lat": "39.3523692",
                    "lon": "-74.4445618",
                    "weight": "580",
                }
            ]
        )

        rows, errors = _prepare_customer_upload_rows(df)

        self.assertEqual(rows, [])
        self.assertTrue(errors)
        self.assertIn("Line 2: lat/lon must be within Malaysia bounds", errors[0])


class CustomerUploadPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.TestSessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
        session = self.TestSessionLocal()
        session.add(
            CustomerCell(
                state="Selangor",
                city="Existing City",
                postcode="40000",
                lat=3.0,
                lon=101.0,
                weight=100.0,
            )
        )
        session.commit()
        session.close()

    def _upload_csv(self, filename: str, csv: str, dataset: str = "customer_density"):
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/admin/customers/upload",
                "headers": [],
            }
        )
        upload = UploadFile(filename=filename, file=BytesIO(csv.encode("utf-8")))
        session = self.TestSessionLocal()
        try:
            return asyncio.run(upload_customers_csv(request, upload, dataset, session))
        finally:
            session.close()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_upload_page_shows_line_level_error(self) -> None:
        csv = (
            "state,city,postcode,lat,lon,weight\n"
            "Kuala Lumpur,Dang Wangi,50560,Not,Found,675\n"
        )

        response = self._upload_csv("bad.csv", csv)
        html = response.body.decode("utf-8")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Upload failed.", html)
        self.assertIn("No database changes were made.", html)
        self.assertIn("Line 2: lat must be numeric", html)
        self.assertIn("Upload CSV", html)

    def test_upload_page_shows_success_and_database_summary(self) -> None:
        csv = (
            "state,city,postcode,lat,lon,weight\n"
            "Kuala Lumpur,Pandan Indah,55100,3.133892,101.7516751,\"3,210\"\n"
            "Selangor,Kajang,43000,2.993518,101.787407,10449\n"
        )

        response = self._upload_csv("customers.csv", csv)
        html = response.body.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Upload successful.", html)
        self.assertIn("customers.csv uploaded successfully for Customer Density.", html)
        self.assertIn("Database Update Summary", html)
        self.assertIn("Customer Density", html)
        self.assertIn("Previous rows", html)
        self.assertIn("<td>1</td>", html)
        self.assertIn("Rows replaced", html)
        self.assertIn("New rows", html)
        self.assertIn("<td>2</td>", html)
        self.assertIn("States updated", html)
        self.assertIn("2 - Kuala Lumpur, Selangor", html)
        self.assertIn("Unique cities", html)
        self.assertIn("Unique postcodes", html)
        self.assertIn("Total customer density", html)
        self.assertIn("13,659", html)

    def test_upload_page_replaces_service_outlets_and_shows_summary(self) -> None:
        session = self.TestSessionLocal()
        session.add(
            ToyotaServiceOutlet(
                outlet_name="Old Service",
                city="Old City",
                state="Selangor",
                postcode="40000",
                lat=3.0,
                lon=101.0,
            )
        )
        session.commit()
        session.close()

        csv = (
            "outlet_name,address,city,state,postcode,lat,lon,phone,email\n"
            "New Service Centre,Lot 1,Shah Alam,Selangor,40000,3.0738,101.5183,03-1234,\n"
        )

        response = self._upload_csv("service.csv", csv, "service_outlets")
        html = response.body.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("service.csv uploaded successfully for Service Outlets.", html)
        self.assertIn("toyota_service_outlets", html)
        self.assertIn("Previous rows", html)
        self.assertIn("<td>1</td>", html)

        session = self.TestSessionLocal()
        services = session.query(ToyotaServiceOutlet).all()
        session.close()
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0].outlet_name, "New Service Centre")

    def test_upload_page_replaces_each_location_dataset_table(self) -> None:
        cases = [
            (
                "body_paint",
                ToyotaBPOutlet,
                "outlet_name,address,city,state,postcode,lat,lon,phone,email\n"
                "New BP,Lot 2,Klang,Selangor,41000,3.0449,101.4456,03-2345,\n",
                "New BP",
                "toyota_bp_outlets",
            ),
            (
                "non_dealer_workshops",
                NonDealerWorkshop,
                "outlet_name,address,city,state,postcode,lat,lon,phone,email\n"
                "Independent Workshop,Lot 3,Petaling Jaya,Selangor,46000,3.1073,101.6067,03-3456,\n",
                "Independent Workshop",
                "non_dealer_workshops",
            ),
            (
                "competitor_bp",
                CompetitorBPOutlet,
                "outlet_name,address,city,state,postcode,lat,lon,phone,email\n"
                "Competitor Paint,Lot 4,Kajang,Selangor,43000,2.9935,101.7874,03-4567,\n",
                "Competitor Paint",
                "competitor_bp_outlets",
            ),
            (
                "traffic_stations",
                TrafficPoliceStation,
                "station_name,address,city,state,postcode,lat,lon,phone,email\n"
                "Balai Trafik Test,Jalan Test,Kuala Lumpur,Kuala Lumpur,50560,3.1569,101.7020,03-5678,\n",
                "Balai Trafik Test",
                "traffic_police_stations",
            ),
        ]

        for dataset, model, csv, expected_name, table_name in cases:
            with self.subTest(dataset=dataset):
                response = self._upload_csv(f"{dataset}.csv", csv, dataset)
                html = response.body.decode("utf-8")

                self.assertEqual(response.status_code, 200)
                self.assertIn(html_lib.escape(CSV_UPLOAD_CONFIGS[dataset]["label"]), html)
                self.assertIn(table_name, html)

                session = self.TestSessionLocal()
                rows = session.query(model).all()
                session.close()
                self.assertEqual(len(rows), 1)
                name_column = CSV_UPLOAD_CONFIGS[dataset]["name_column"]
                self.assertEqual(getattr(rows[0], name_column), expected_name)

    def test_upload_page_rejects_missing_required_location_column_without_db_changes(self) -> None:
        csv = "city,state,postcode,lat,lon\nShah Alam,Selangor,40000,3.0738,101.5183\n"

        response = self._upload_csv("missing-name.csv", csv, "service_outlets")
        html = response.body.decode("utf-8")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing columns in CSV: outlet_name", html)
        session = self.TestSessionLocal()
        services = session.query(ToyotaServiceOutlet).all()
        session.close()
        self.assertEqual(services, [])

    def test_upload_page_rejects_invalid_dataset_without_db_changes(self) -> None:
        csv = (
            "state,city,postcode,lat,lon,weight\n"
            "Selangor,Ampang,68000,3.16648,101.748344,6265\n"
        )

        response = self._upload_csv("customers.csv", csv, "unknown_dataset")
        html = response.body.decode("utf-8")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Please choose a valid data type before uploading.", html)
        session = self.TestSessionLocal()
        customers = session.query(CustomerCell).all()
        session.close()
        self.assertEqual(len(customers), 1)


if __name__ == "__main__":
    unittest.main()
