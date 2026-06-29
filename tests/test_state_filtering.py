from __future__ import annotations

import json
import unittest
from pathlib import Path

from db import (
    CustomerCell,
    SessionLocal,
    ToyotaBPOutlet,
    ToyotaServiceOutlet,
    TrafficPoliceStation,
)
from main import search_filtered, search_multi_state
from map_utils import get_admin1_feature, normalize_state_name


BASE_DIR = Path(__file__).resolve().parents[1]
MASTER_DATA_PATH = BASE_DIR / "data" / "master.json"

MODEL_TO_RESPONSE_KEY = (
    (CustomerCell, "customers"),
    (ToyotaServiceOutlet, "service"),
    (ToyotaBPOutlet, "bp"),
    (TrafficPoliceStation, "traffic"),
)

STATE_ALIASES = {
    "Pulau Pinang": ["Pulau Pinang", "Penang"],
    "Melaka": ["Melaka", "Malacca"],
    "Kuala Lumpur": [
        "Kuala Lumpur",
        "Wilayah Persekutuan Kuala Lumpur",
        "WP Kuala Lumpur",
    ],
    "Labuan": ["Labuan", "Wilayah Persekutuan Labuan", "WP Labuan"],
    "Putrajaya": ["Putrajaya", "Wilayah Persekutuan Putrajaya", "WP Putrajaya"],
}


def master_states() -> list[str]:
    with open(MASTER_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [state["name"] for state in data["states"]]


def canonical_state(value: str | None) -> str:
    text = str(value or "").strip()
    return (normalize_state_name(text) or text).lower()


def count_model_rows_for_state(db, model, canonical: str) -> int:
    rows = db.query(model).all()
    return sum(1 for row in rows if canonical_state(row.state) == canonical.lower())


def assert_search_counts_match_db(
    test_case: unittest.TestCase,
    db,
    state_query: str,
    expected_canonical_state: str,
) -> None:
    result = search_filtered(state=state_query, city=None, postcode=None, db=db)

    for model, response_key in MODEL_TO_RESPONSE_KEY:
        expected_count = count_model_rows_for_state(db, model, expected_canonical_state)
        actual_count = len(result[response_key])
        test_case.assertEqual(
            actual_count,
            expected_count,
            (
                f"{state_query!r} should return {expected_count} {response_key} "
                f"rows for canonical state {expected_canonical_state!r}, got {actual_count}."
            ),
        )

    total_expected = sum(
        count_model_rows_for_state(db, model, expected_canonical_state)
        for model, _ in MODEL_TO_RESPONSE_KEY
    )
    total_actual = sum(len(result[response_key]) for _, response_key in MODEL_TO_RESPONSE_KEY)
    test_case.assertEqual(total_actual, total_expected)

    boundary = result.get("boundary") or {}
    test_case.assertEqual(boundary.get("type"), "polygon")
    feature = boundary.get("feature") or {}
    test_case.assertEqual(
        canonical_state(feature.get("properties", {}).get("display_name")),
        expected_canonical_state.lower(),
    )


class StateFilteringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.db.close()

    def test_every_master_state_matches_canonical_db_counts(self) -> None:
        missing_boundaries: list[str] = []

        for state in master_states():
            canonical = normalize_state_name(state) or state
            with self.subTest(state=state):
                if not get_admin1_feature(state):
                    missing_boundaries.append(state)
                assert_search_counts_match_db(self, self.db, state, canonical)

        self.assertEqual(missing_boundaries, [])

    def test_state_aliases_match_their_canonical_state_counts(self) -> None:
        for canonical, aliases in STATE_ALIASES.items():
            for alias in aliases:
                with self.subTest(canonical=canonical, alias=alias):
                    assert_search_counts_match_db(self, self.db, alias, canonical)

    def test_pulau_pinang_regression_returns_penang_csv_rows(self) -> None:
        result = search_filtered(state="Pulau Pinang", city=None, postcode=None, db=self.db)

        self.assertEqual(len(result["customers"]), 0)
        self.assertEqual(len(result["service"]), 5)
        self.assertEqual(len(result["bp"]), 3)
        self.assertEqual(len(result["traffic"]), 2)
        self.assertEqual(
            sum(len(result[key]) for key in ("customers", "service", "bp", "traffic")),
            10,
        )

    def test_default_all_states_search_returns_all_plotted_rows(self) -> None:
        result = search_filtered(state=None, city=None, postcode=None, db=self.db)

        for model, response_key in MODEL_TO_RESPONSE_KEY:
            self.assertEqual(len(result[response_key]), self.db.query(model).count())

        self.assertIsNone(result.get("boundary"))

    def test_multi_state_search_combines_canonical_state_counts(self) -> None:
        states = ["Pulau Pinang", "Kedah"]
        result = search_multi_state(states=states, db=self.db)

        self.assertEqual(result["states"], states)
        self.assertEqual(len(result["boundaries"]), 2)

        for model, response_key in MODEL_TO_RESPONSE_KEY:
            expected_count = sum(
                count_model_rows_for_state(self.db, model, state)
                for state in states
            )
            self.assertEqual(len(result[response_key]), expected_count)

        self.assertEqual(len(result["customers"]), 0)
        self.assertEqual(len(result["service"]), 9)
        self.assertEqual(len(result["bp"]), 7)
        self.assertEqual(len(result["traffic"]), 8)
        self.assertEqual(
            sum(len(result[key]) for key in ("customers", "service", "bp", "traffic")),
            24,
        )


if __name__ == "__main__":
    unittest.main()
