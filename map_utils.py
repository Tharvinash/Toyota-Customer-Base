import pandas as pd
import numpy as np
import folium
from folium.plugins import HeatMap, MarkerCluster, Fullscreen, MiniMap, MousePosition, MeasureControl
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List
import requests
import time

# ---------- SETTINGS ----------
DATA_DIR = Path(__file__).parent
STATE = "Selangor"
OUTPUT_HTML = DATA_DIR / "selangor_map.html"

# Approximate bounding box for Malaysia (Peninsular + East Malaysia)
# [south_lat, west_lon], [north_lat, east_lon]
MALAYSIA_BOUNDS = [
    [0.85, 99.5],
    [7.5, 119.5],
]

CITY_LOOKUP = {
    "Shah Alam": (3.0738, 101.5183),
    "Petaling Jaya": (3.1073, 101.6067),
    "Subang Jaya": (3.0432, 101.5806),
    "Klang": (3.0439, 101.4460),
    "Kajang": (2.9935, 101.7871),
    "Ampang": (3.1498, 101.7600),
    "Puchong": (3.0153, 101.6167),
    "Cyberjaya": (2.9226, 101.6507),
    "Sepang": (2.6930, 101.7490),
}


def log(msg: str):
    print(f"[INFO] {msg}")


# ----------------- DATA HELPERS -----------------
def load_csv(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    if not path.exists():
        log(f"{name} not found at {path}")
        return pd.DataFrame()
    log(f"Loading {name} ...")
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    log(f"{name} loaded: {len(df)} rows, columns={list(df.columns)}")
    return df


def ensure_latlon(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    if "state" in df.columns:
        before = len(df)
        df = df[df["state"].astype(str).str.strip().str.lower() == STATE.lower()].copy()
        log(f"Filtered to state={STATE}: {before} -> {len(df)} rows")

    for key in ["lat", "lon"]:
        if key not in df.columns:
            df[key] = ""

    if "city" in df.columns:
        for i, row in df.iterrows():
            lat, lon = row.get("lat", ""), row.get("lon", "")
            city = str(row.get("city", "")).strip()
            if (lat == "" or pd.isna(lat)) or (lon == "" or pd.isna(lon)):
                if city in CITY_LOOKUP:
                    df.at[i, "lat"] = CITY_LOOKUP[city][0]
                    df.at[i, "lon"] = CITY_LOOKUP[city][1]

    df["lat"] = pd.to_numeric(df.get("lat"), errors="coerce")
    df["lon"] = pd.to_numeric(df.get("lon"), errors="coerce")
    before_drop = len(df)
    df = df.dropna(subset=["lat", "lon"]).copy()
    log(f"Dropped rows missing coords: {before_drop} -> {len(df)} rows")
    return df


def make_bins_from_weights(weights: pd.Series, n_bins: int = 5):
    """
    Return (edges, labels) for n_bins quantile bins built from the REAL
    weights in the CSV (after the per-lat/lon sum).
    """
    w = np.asarray(weights, dtype=float)
    w = w[~np.isnan(w)]
    if len(w) == 0:
        return np.array([0, 1, 2, 3, 4, 5], dtype=float), ["0–1", "2–3", "4–5", "6–7", "8+"]

    edges = np.quantile(w, np.linspace(0, 1, n_bins + 1))

    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = np.nextafter(edges[i - 1], float("inf"))

    def fmt(x):
        return f"{int(round(x)):,}"

    labels = []
    for i in range(n_bins):
        a, b = edges[i], edges[i + 1]
        left = fmt(a) if i == 0 else fmt(np.floor(a) + 1)
        right = fmt(np.ceil(b))
        labels.append(f"{left}–{right}")

    return edges, labels


def add_legend_box(m: folium.Map, heat_labels: list[str]) -> None:
    """Bottom-right legend with icons + numeric heat ranges."""
    colors = ["#2b83ba", "#80bfab", "#ffffbf", "#fdae61", "#d7191c"]
    if len(heat_labels) != len(colors):
        if len(heat_labels) < len(colors):
            colors = colors[: len(heat_labels)]
        else:
            colors = colors + [colors[-1]] * (len(heat_labels) - len(colors))

    rows = "".join(
        f"""
        <div style="display:flex;align-items:center;margin:2px 0;">
          <span style="display:inline-block;width:18px;height:12px;
                       background:{c};border:1px solid #666;margin-right:8px;"></span>
          <span style="font-size:12px;">{lab}</span>
        </div>
        """
        for c, lab in zip(colors, heat_labels)
    )

    legend_html = f"""
    <div style="
      position:absolute;
      right: 12px;
      bottom: 20px;
      z-index: 9999;
      background: rgba(255,255,255,0.96);
      border: 1px solid #999;
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 14px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.12);
      min-width: 230px;">
      <div style="font-weight:600;margin-bottom:6px;">Legend</div>
      <div style="line-height:1.4;">
        <div><i class="fa fa-wrench" style="color:blue"></i>&nbsp; Toyota Service Outlets</div>
        <div><i class="fa fa-car"    style="color:green"></i>&nbsp; Toyota Body &amp; Paint</div>
        <div><i class="fa fa-road"   style="color:red"></i>&nbsp; Traffic Police Stations</div>
      </div>
      <hr style="margin:8px 0;">
      <div style="font-weight:600;margin-bottom:4px;">Customer Density</div>
      {rows}
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))


def _haversine_array(
    lat: np.ndarray,
    lon: np.ndarray,
    center_lat: float,
    center_lon: float,
) -> np.ndarray:
    """
    Vectorized haversine distance (in km) between each (lat, lon)
    and a single center point.
    """
    R = 6371.0  # Earth radius in km

    lat = np.radians(lat.astype(float))
    lon = np.radians(lon.astype(float))
    clat = np.radians(float(center_lat))
    clon = np.radians(float(center_lon))

    dlat = lat - clat
    dlon = lon - clon

    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat) * np.cos(clat) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(a))
    return R * c


def filter_by_radius(
    df: pd.DataFrame,
    center_lat: float,
    center_lon: float,
    radius_km: float,
) -> pd.DataFrame:
    """
    Return only rows within radius_km of (center_lat, center_lon).
    Assumes df has numeric 'lat' and 'lon' columns.
    """
    if df.empty or "lat" not in df.columns or "lon" not in df.columns:
        return df.copy()

    lat = df["lat"].to_numpy(dtype=float)
    lon = df["lon"].to_numpy(dtype=float)
    dists = _haversine_array(lat, lon, center_lat, center_lon)

    mask = dists <= float(radius_km)
    return df.loc[mask].copy()


def geocode_location(term: str) -> Optional[Tuple[float, float]]:
    """
    Use OpenStreetMap Nominatim to geocode a location name or postcode.
    Returns (lat, lon) if found, None otherwise.
    
    This gets coordinates directly from the internet, not from your database.
    """
    result = geocode_location_with_details(term)
    if result:
        return (result["lat"], result["lon"])
    return None


def geocode_location_with_details(term: str) -> Optional[dict]:
    """
    Use OpenStreetMap Nominatim to geocode a location name or postcode.
    Returns dict with 'lat', 'lon', 'boundingbox', and 'display_name' if found, None otherwise.
    
    This gets coordinates and boundary information directly from the internet.
    """
    term = (term or "").strip()
    if not term:
        return None

    # OpenStreetMap Nominatim (free, no API key needed)
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": term,
        "format": "json",
        "limit": 1,
        "countrycodes": "my",  # Restrict to Malaysia (optional, remove if you want worldwide)
        "addressdetails": 1,
        "polygon_geojson": 1,  # Request polygon geometry when available
    }
    headers = {
        "User-Agent": "SelangorMapApp/1.0"  # Required by Nominatim usage policy
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        if not data or len(data) == 0:
            return None
            
        # Get the first result
        result = data[0]
        lat = float(result["lat"])
        lon = float(result["lon"])
        boundingbox = result.get("boundingbox", [])
        display_name = result.get("display_name", term)
        polygon_geojson = result.get("geojson")
        
        log(f"Geocoded '{term}' -> ({lat}, {lon})")
        return {
            "lat": lat,
            "lon": lon,
            "boundingbox": boundingbox,
            "display_name": display_name,
            "polygon_geojson": polygon_geojson,
            "polygon_feature": geojson_feature_from_polygon(
                polygon_geojson,
                properties={"display_name": display_name},
            ),
            "raw_result": result
        }
    except Exception as e:
        log(f"[ERROR] Geocoding failed for '{term}': {e}")
        return None


def extract_bounding_box(geocode_result: dict) -> Optional[List[List[float]]]:
    """
    Extract bounding box from geocoding result and convert to Leaflet bounds format.
    Returns [[south_lat, west_lon], [north_lat, east_lon]] or None if not available.
    """
    if not geocode_result or "boundingbox" not in geocode_result:
        return None
    
    bbox = geocode_result["boundingbox"]
    if not bbox or len(bbox) != 4:
        return None
    
    try:
        # Nominatim boundingbox format: [south_lat, north_lat, west_lon, east_lon]
        south_lat = float(bbox[0])
        north_lat = float(bbox[1])
        west_lon = float(bbox[2])
        east_lon = float(bbox[3])
        
        # Convert to Leaflet bounds format: [[south_lat, west_lon], [north_lat, east_lon]]
        return [[south_lat, west_lon], [north_lat, east_lon]]
    except (ValueError, IndexError) as e:
        log(f"[ERROR] Failed to parse bounding box: {e}")
        return None


def geojson_feature_from_polygon(
    polygon: Optional[Dict[str, Any]],
    properties: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Wrap a raw polygon/multipolygon geometry (lon/lat) into a GeoJSON Feature.
    """
    if not polygon or not isinstance(polygon, dict):
        return None
    geometry_type = polygon.get("type")
    if geometry_type not in {"Polygon", "MultiPolygon"}:
        return None
    coordinates = polygon.get("coordinates")
    if not coordinates:
        return None
    return {
        "type": "Feature",
        "properties": properties or {},
        "geometry": {
            "type": geometry_type,
            "coordinates": coordinates,
        },
    }


def rectangle_feature_from_bounds(
    bounds: Optional[List[List[float]]],
    properties: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Build a GeoJSON rectangle polygon Feature from [[south, west], [north, east]] bounds.
    """
    if not bounds or len(bounds) != 2:
        return None
    (south, west), (north, east) = bounds
    try:
        south = float(south)
        west = float(west)
        north = float(north)
        east = float(east)
    except (TypeError, ValueError):
        return None

    ring = [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
    ]
    return {
        "type": "Feature",
        "properties": properties or {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [ring],
        },
    }


def extract_polygon_feature(geocode_result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Convenience helper to extract a GeoJSON Feature from a full geocode result dict.
    """
    if not geocode_result:
        return None
    polygon = geocode_result.get("polygon_geojson")
    if not polygon and geocode_result.get("raw_result"):
        polygon = geocode_result["raw_result"].get("geojson")
    return geojson_feature_from_polygon(
        polygon,
        properties={"display_name": geocode_result.get("display_name", "")},
    )


def geocode_multiple_locations(terms: List[str], delay_seconds: float = 1.2) -> List[dict]:
    """
    Geocode multiple locations using OpenStreetMap Nominatim.
    Adds delays between requests to respect rate limits (1 req/sec).
    
    Args:
        terms: List of location names or postcodes to geocode
        delay_seconds: Delay between requests (default 1.2 to respect 1 req/sec limit)
    
    Returns:
        List of dicts with keys: 'term', 'lat', 'lon', 'success'
    """
    results = []
    
    log(f"Geocoding {len(terms)} location(s)...")
    
    for i, term in enumerate(terms):
        if i > 0:  # Don't delay before first request
            time.sleep(delay_seconds)  # Respect 1 request/second limit
        
        geocode_result = geocode_location_with_details(term)
        if geocode_result:
            results.append({
                "term": term,
                "lat": geocode_result["lat"],
                "lon": geocode_result["lon"],
                "boundingbox": geocode_result.get("boundingbox"),
                "display_name": geocode_result.get("display_name", term),
                "polygon_geojson": geocode_result.get("polygon_geojson"),
                "polygon_feature": geocode_result.get("polygon_feature"),
                "success": True
            })
            log(f"✓ Geocoded '{term}' -> ({geocode_result['lat']}, {geocode_result['lon']})")
        else:
            results.append({
                "term": term,
                "lat": None,
                "lon": None,
                "boundingbox": None,
                "display_name": None,
                "polygon_geojson": None,
                "polygon_feature": None,
                "success": False
            })
            log(f"✗ Failed to geocode '{term}'")
    
    successful = sum(1 for r in results if r["success"])
    log(f"Geocoding complete: {successful}/{len(terms)} successful")
    
    return results


def find_search_center(
    term: str,
    dfs: Dict[str, pd.DataFrame],
) -> Optional[Tuple[float, float]]:
    """
    Find a (lat, lon) center for a search term across multiple DataFrames.

    Looks in columns like postcode, city, outlet_name, station_name, name
    (case-insensitive). Returns the first matching row with valid coords,
    or None if no match.
    
    NOTE: This function is kept for backward compatibility but is no longer
    used by the main search endpoint. The search endpoint now uses geocode_location()
    to get coordinates from online services.
    """
    term = (term or "").strip()
    if not term:
        return None

    search_cols_priority = [
        "postcode",
        "city",
        "outlet_name",
        "station_name",
        "name",
    ]

    for df_name, df in dfs.items():
        if df.empty or "lat" not in df.columns or "lon" not in df.columns:
            continue

        for col in search_cols_priority:
            if col not in df.columns:
                continue

            mask = df[col].astype(str).str.contains(term, case=False, na=False)
            candidates = df[mask & df["lat"].notna() & df["lon"].notna()]

            if not candidates.empty:
                row = candidates.iloc[0]
                return float(row["lat"]), float(row["lon"])

    return None
