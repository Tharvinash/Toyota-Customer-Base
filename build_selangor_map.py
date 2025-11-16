import pandas as pd
import numpy as np
import folium
from folium.plugins import (
    HeatMap,
    MarkerCluster,
    Fullscreen,
    MiniMap,
    MousePosition,
    MeasureControl,
)
from pathlib import Path

# ---------- SETTINGS ----------
DATA_DIR = Path(__file__).parent
STATE = "Selangor"
OUTPUT_HTML = DATA_DIR / "selangor_map.html"

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

from map_builder import build_map


# ----------------- MAIN -----------------
def main():
    log(f"Running from folder: {DATA_DIR}")
    log(f"CSV files present: {[p.name for p in DATA_DIR.glob('*.csv')]}")

    customers = load_csv("customers.csv")
    service = load_csv("toyota_service_outlets.csv")
    bp = load_csv("toyota_bp_outlets.csv")
    traffic_police = load_csv("traffic_police_stations.csv")

    m = build_map(customers, service, bp, traffic_police)

    m.save(str(OUTPUT_HTML))
    log(f"✅ Map saved to: {OUTPUT_HTML}")

if __name__ == "__main__":
    main()
