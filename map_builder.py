from __future__ import annotations

import folium
import numpy as np
import pandas as pd
from folium.plugins import (
    Fullscreen,
    HeatMap,
    MarkerCluster,
    MeasureControl,
    MiniMap,
    MousePosition,
)

from map_utils import ensure_latlon, make_bins_from_weights, add_legend_box, log, MALAYSIA_BOUNDS


def build_map(
    customers: pd.DataFrame,
    service: pd.DataFrame,
    bp: pd.DataFrame,
    traffic_police: pd.DataFrame,
) -> folium.Map:
    """
    Core map-building logic shared between the CLI script and the web backend.
    Takes pre-loaded DataFrames (from CSV or DB) with columns including
    lat/lon, and returns a Folium Map instance.
    """

    customers = ensure_latlon(customers)
    service = ensure_latlon(service)
    bp = ensure_latlon(bp)
    traffic_police = ensure_latlon(traffic_police)

    log(
        f"Rows after processing — customers:{len(customers)}, "
        f"service:{len(service)}, bp:{len(bp)}, traffic:{len(traffic_police)}"
    )

    # Base map + UI (center roughly on Malaysia, restrict view to Malaysia bounds)
    m = folium.Map(
        location=(4.5, 109.0),
        zoom_start=6,
        tiles=None,
        max_bounds=True,
    )
    folium.TileLayer("CartoDB Positron", name="Light").add_to(m)
    folium.TileLayer("CartoDB Voyager", name="Voyager (labels)").add_to(m)
    folium.TileLayer("CartoDB Dark_Matter", name="Dark").add_to(m)
    folium.TileLayer("OpenStreetMap", name="OSM").add_to(m)

    m.get_root().html.add_child(
        folium.Element(
            """
    <style>
      .leaflet-top.leaflet-left .leaflet-control-layers { margin-top: 60px; }
    </style>
    """
        )
    )

    Fullscreen().add_to(m)
    MiniMap(toggle_display=True, position="bottomleft").add_to(m)
    MousePosition(position="topright", prefix="Lat/Lon:").add_to(m)
    MeasureControl(position="bottomleft", primary_length_unit="kilometers").add_to(m)

    # Auto-fit
    bounds_pts = []
    for df in [customers, service, bp, traffic_police]:
        if not df.empty:
            bounds_pts += df[["lat", "lon"]].dropna().values.tolist()
    if bounds_pts:
        lats = [p[0] for p in bounds_pts]
        lons = [p[1] for p in bounds_pts]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], padding=(20, 20))

    # Finally, ensure the view is constrained to Malaysia only
    m.fit_bounds(MALAYSIA_BOUNDS)

    # Heatmap
    heat_labels = ["Low", "Med-Low", "Medium", "Med-High", "High"]
    if not customers.empty:
        if "weight" not in customers.columns:
            customers["weight"] = 1.0

        grouped = (
            customers.groupby(["lat", "lon"], as_index=False)["weight"]
            .sum()
            .rename(columns={"weight": "w"})
        )

        # Legend labels derived from REAL weights
        edges, heat_labels = make_bins_from_weights(grouped["w"], n_bins=5)

        # Normalized intensity for the heat layer
        p95 = np.percentile(grouped["w"], 95) if len(grouped) > 1 else grouped["w"].max()
        p95 = p95 if p95 > 0 else 1.0
        grouped["wn"] = (grouped["w"] / p95).clip(upper=1.0)

        gradient = {
            0.00: "#2b83ba",
            0.25: "#80bfab",
            0.50: "#ffffbf",
            0.75: "#fdae61",
            1.00: "#d7191c",
        }

        heat = HeatMap(
            grouped[["lat", "lon", "wn"]].values.tolist(),
            name="Customer Heatmap",
            radius=40,
            blur=20,
            min_opacity=0.75,
            max_zoom=18,
            gradient=gradient,
            scale_radius=False,
            use_local_extrema=False,
        ).add_to(m)

        # Keep heat strong when zooming in
        js = f"""
        <script>
        var _map = {m.get_name()};
        var _heat = {heat.get_name()};
        function _scaleHeat() {{
            var z = _map.getZoom();
            var r = Math.max(40, Math.min(150, 18 * (z - 6)));
            var b = Math.round(r * 0.8);
            if (_heat.setOptions) {{
                _heat.setOptions({{radius:r, blur:b, maxZoom:22}});
            }} else if (_heat._heat && _heat._heat._config) {{
                _heat._heat._config.radius = r;
                _heat._heat._config.blur = b;
                _heat.redraw();
            }}
        }}
        _map.on('zoomend', _scaleHeat); _scaleHeat();
        </script>
        """
        m.get_root().html.add_child(folium.Element(js))
    else:
        log("No customers to plot")

    # Legend
    add_legend_box(m, heat_labels)

    # Markers
    def add_markers(df: pd.DataFrame, name: str, icon: str, color: str):
        if df.empty:
            log(f"No rows for layer: {name}")
            return
        fg = folium.FeatureGroup(name=name, show=True)
        cluster = MarkerCluster(name=name).add_to(fg)
        for _, r in df.iterrows():
            tooltip = (
                r.get("outlet_name")
                or r.get("station_name")
                or r.get("name")
                or name
            )
            popup_lines = []
            for c in df.columns:
                val = r.get(c, "")
                if pd.notna(val) and str(val).strip() != "":
                    popup_lines.append(f"<b>{c.title()}</b>: {val}")
            popup_html = "<br>".join(popup_lines) if popup_lines else name
            folium.Marker(
                location=(r["lat"], r["lon"]),
                tooltip=str(tooltip),
                popup=folium.Popup(popup_html, max_width=350),
                icon=folium.Icon(icon=icon, prefix="fa", color=color),
            ).add_to(cluster)
        fg.add_to(m)
        log(f"Added layer: {name} ({len(df)} markers)")

    add_markers(service, "Toyota Service Outlets", icon="wrench", color="blue")
    add_markers(bp, "Toyota Body & Paint", icon="car", color="green")
    add_markers(traffic_police, "Traffic Police Stations", icon="road", color="red")

    folium.LayerControl(collapsed=False, position="topleft").add_to(m)

    return m



