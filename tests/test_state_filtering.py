from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from db import (
    CompetitorBPOutlet,
    CustomerCell,
    NonDealerWorkshop,
    SessionLocal,
    ToyotaBPOutlet,
    ToyotaServiceOutlet,
    TrafficPoliceStation,
)
from main import search_filtered, search_multi_state
from map_utils import get_admin1_feature, normalize_state_name
from map_utils import MALAYSIA_BOUNDS


BASE_DIR = Path(__file__).resolve().parents[1]
MASTER_DATA_PATH = BASE_DIR / "data" / "master.json"

MODEL_TO_RESPONSE_KEY = (
    (CustomerCell, "customers"),
    (ToyotaServiceOutlet, "service"),
    (ToyotaBPOutlet, "bp"),
    (NonDealerWorkshop, "non_dealer"),
    (CompetitorBPOutlet, "competitor_bp"),
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
    return sum(
        1
        for row in rows
        if canonical_state(row.state) == canonical.lower() and has_valid_malaysia_coords(row)
    )


def has_valid_malaysia_coords(row) -> bool:
    if row.lat is None or row.lon is None:
        return False
    south, west = MALAYSIA_BOUNDS[0]
    north, east = MALAYSIA_BOUNDS[1]
    return south <= float(row.lat) <= north and west <= float(row.lon) <= east


def count_model_plotted_rows(db, model) -> int:
    return sum(1 for row in db.query(model).all() if has_valid_malaysia_coords(row))


def geojson_features_by_display_name(features: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        feature.get("properties", {}).get("display_name"): feature
        for feature in features
    }


def feature_polygons(feature: dict[str, Any]) -> list[list[list[float]]]:
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if geometry.get("type") == "Polygon":
        return [coordinates]
    if geometry.get("type") == "MultiPolygon":
        return coordinates
    return []


def ring_bounds(ring: list[list[float]]) -> tuple[float, float, float, float]:
    lons = [coord[0] for coord in ring]
    lats = [coord[1] for coord in ring]
    return min(lats), max(lats), min(lons), max(lons)


def bounds_area(bounds: tuple[float, float, float, float]) -> float:
    south, north, west, east = bounds
    return max(north - south, 0) * max(east - west, 0)


def bounds_overlap_ratio(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    south = max(a[0], b[0])
    north = min(a[1], b[1])
    west = max(a[2], b[2])
    east = min(a[3], b[3])
    overlap = bounds_area((south, north, west, east))
    smaller = min(bounds_area(a), bounds_area(b))
    return overlap / smaller if smaller else 0


def selangor_interior_hole_overlaps(feature: dict[str, Any], enclave: dict[str, Any]) -> list[float]:
    enclave_bounds = ring_bounds(feature_polygons(enclave)[0][0])
    overlaps: list[float] = []
    for polygon in feature_polygons(feature):
        for interior_ring in polygon[1:]:
            overlaps.append(bounds_overlap_ratio(ring_bounds(interior_ring), enclave_bounds))
    return overlaps


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

        for model, response_key in MODEL_TO_RESPONSE_KEY:
            self.assertEqual(
                len(result[response_key]),
                count_model_rows_for_state(self.db, model, "Pulau Pinang"),
            )

    def test_default_all_states_search_returns_all_plotted_rows(self) -> None:
        result = search_filtered(state=None, city=None, postcode=None, db=self.db)

        for model, response_key in MODEL_TO_RESPONSE_KEY:
            self.assertEqual(len(result[response_key]), count_model_plotted_rows(self.db, model))

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

        for model, response_key in MODEL_TO_RESPONSE_KEY:
            expected_count = sum(
                count_model_rows_for_state(self.db, model, state)
                for state in states
            )
            self.assertEqual(len(result[response_key]), expected_count)

    def test_multi_state_wp_kuala_lumpur_returns_kl_boundary_not_putrajaya(self) -> None:
        result = search_multi_state(states=["Selangor", "Wp Kuala Lumpur"], db=self.db)

        self.assertEqual(result["states"], ["Selangor", "Kuala Lumpur"])
        features = geojson_features_by_display_name(
            [boundary["feature"] for boundary in result["boundaries"]]
        )
        self.assertIn("Selangor", features)
        self.assertIn("Kuala Lumpur", features)
        self.assertNotIn("Putrajaya", features)
        self.assertEqual(result["missing_boundaries"], [])

    def test_multi_state_wp_putrajaya_returns_putrajaya_boundary_not_kl(self) -> None:
        result = search_multi_state(states=["Selangor", "Wp Putrajaya"], db=self.db)

        self.assertEqual(result["states"], ["Selangor", "Putrajaya"])
        features = geojson_features_by_display_name(
            [boundary["feature"] for boundary in result["boundaries"]]
        )
        self.assertIn("Selangor", features)
        self.assertIn("Putrajaya", features)
        self.assertNotIn("Kuala Lumpur", features)
        self.assertEqual(result["missing_boundaries"], [])

    def test_selangor_boundary_holes_match_kl_and_putrajaya_enclaves(self) -> None:
        selangor = get_admin1_feature("Selangor")
        kuala_lumpur = get_admin1_feature("Wp Kuala Lumpur")
        putrajaya = get_admin1_feature("Wp Putrajaya")

        self.assertIsNotNone(selangor)
        self.assertIsNotNone(kuala_lumpur)
        self.assertIsNotNone(putrajaya)

        selangor_polygons = feature_polygons(selangor)
        interior_ring_count = sum(max(len(polygon) - 1, 0) for polygon in selangor_polygons)
        self.assertGreaterEqual(interior_ring_count, 2)

        kl_overlaps = selangor_interior_hole_overlaps(selangor, kuala_lumpur)
        putrajaya_overlaps = selangor_interior_hole_overlaps(selangor, putrajaya)

        self.assertGreater(max(kl_overlaps), 0.65)
        self.assertGreater(max(putrajaya_overlaps), 0.65)

    def test_interactive_map_template_keeps_selected_nested_enclaves_visible(self) -> None:
        template = (BASE_DIR / "templates" / "interactive_map.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("function isNestedInsideSelectedRing", template)
        self.assertIn(
            ".filter((entry) => !isNestedInsideSelectedRing(entry, featureRings))",
            template,
        )


if __name__ == "__main__":
    unittest.main()
