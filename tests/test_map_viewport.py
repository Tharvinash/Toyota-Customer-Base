from __future__ import annotations

import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
MAP_TEMPLATE_PATH = BASE_DIR / "templates" / "interactive_map.html"


class InteractiveMapViewportTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = MAP_TEMPLATE_PATH.read_text(encoding="utf-8")

    def test_only_selected_states_use_a_tile_mask(self) -> None:
        self.assertIn('map.createPane("stateMaskPane")', self.template)
        self.assertIn("stateTileMaskLayer", self.template)
        self.assertNotIn("countryMaskPane", self.template)
        self.assertNotIn("countryTileMaskLayer", self.template)

    def test_map_is_restricted_to_malaysia_bounds_and_minimum_zoom(self) -> None:
        self.assertIn("maxBounds: malaysiaBounds", self.template)
        self.assertIn("maxBoundsViscosity: 1.0", self.template)
        self.assertIn("map.setMinZoom(minimumZoom)", self.template)

    def test_all_runtime_fit_bounds_calls_use_the_viewport_guard(self) -> None:
        self.assertIn("function applyMapViewport", self.template)
        self.assertIn("function clampBoundsToMalaysia", self.template)
        self.assertEqual(self.template.count("map.fitBounds("), 1)

    def test_resize_and_fullscreen_refresh_the_active_viewport(self) -> None:
        self.assertIn("function refreshActiveViewport", self.template)
        self.assertIn("function invalidateMapAfterFullscreenChange", self.template)
        self.assertGreaterEqual(
            self.template.count("refreshActiveViewport();"),
            5,
        )


if __name__ == "__main__":
    unittest.main()
