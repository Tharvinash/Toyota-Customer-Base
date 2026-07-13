from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import json

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.requests import Request

from db import (
    CompetitorBPOutlet,
    CustomerCell,
    NonDealerWorkshop,
    ToyotaBPOutlet,
    ToyotaServiceOutlet,
    TrafficPoliceStation,
    get_db,
    init_db,
)
from map_utils import (
    MALAYSIA_BOUNDS,
    ensure_latlon,
    get_admin1_feature,
    normalize_state_name,
    geocode_location_with_details,
    geocode_multiple_locations,
    filter_by_radius,
    extract_bounding_box,
    extract_polygon_feature,
    rectangle_feature_from_bounds,
)


app = FastAPI(title="Selangor Map Backend")

# Init DB on startup (simple dev/local approach)
init_db()

# Use a path relative to this file so it works regardless of the working directory
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health", response_class=HTMLResponse)
def health() -> str:
    return "OK"


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(
        BASE_DIR / "static" / "favicon.ico",
        media_type="image/x-icon",
    )


@app.get("/api/master-data")
def get_master_data():
    """Return the master.json data for cascading dropdowns."""
    master_file = BASE_DIR / "data" / "master.json"
    if not master_file.exists():
        raise HTTPException(status_code=404, detail="Master data file not found")
    with open(master_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


@app.get("/api/search-filtered")
def search_filtered(
    state: Optional[str] = Query(None, description="State name"),
    city: Optional[str] = Query(None, description="City name"),
    postcode: Optional[str] = Query(None, description="Postcode"),
    db: Session = Depends(get_db),
):
    """
    Filter data by state, city, and/or postcode from the database.
    If a filter is not provided, all records for that level are returned.
    """
    customers_base = ensure_latlon(_query_to_df(db.query(CustomerCell)), state_filter=None)
    service_base = ensure_latlon(_query_to_df(db.query(ToyotaServiceOutlet)), state_filter=None)
    bp_base = ensure_latlon(_query_to_df(db.query(ToyotaBPOutlet)), state_filter=None)
    non_dealer_base = ensure_latlon(_query_to_df(db.query(NonDealerWorkshop)), state_filter=None)
    competitor_bp_base = ensure_latlon(_query_to_df(db.query(CompetitorBPOutlet)), state_filter=None)
    traffic_base = ensure_latlon(_query_to_df(db.query(TrafficPoliceStation)), state_filter=None)

    def filter_df(df: pd.DataFrame, state_val: Optional[str], city_val: Optional[str], postcode_val: Optional[str]) -> pd.DataFrame:
        """Filter DataFrame by state, city, and postcode."""
        result = df.copy()
        
        if state_val and "state" in result.columns:
            wanted_state = normalize_state_name(state_val) or state_val

            def canonical_state(value: Any) -> str:
                return (normalize_state_name(str(value)) or str(value)).strip().lower()

            state_series = result["state"].apply(canonical_state)
            result = result[state_series == wanted_state.lower()]
        
        if city_val and "city" in result.columns:
            result = result[result["city"].astype(str).str.strip().str.lower() == city_val.lower()]
        
        if postcode_val and "postcode" in result.columns:
            # Normalize postcode (remove spaces, handle string/numeric)
            postcode_norm = str(postcode_val).replace(" ", "").strip()
            result = result.copy()
            result["postcode_norm"] = result["postcode"].astype(str).str.replace(" ", "").str.strip()
            result = result[result["postcode_norm"] == postcode_norm]
            result = result.drop(columns=["postcode_norm"])
        
        return result

    customers_df = filter_df(customers_base, state, city, postcode)
    service_df = filter_df(service_base, state, city, postcode)
    bp_df = filter_df(bp_base, state, city, postcode)
    non_dealer_df = filter_df(non_dealer_base, state, city, postcode)
    competitor_bp_df = filter_df(competitor_bp_base, state, city, postcode)
    traffic_df = filter_df(traffic_base, state, city, postcode)

    def df_to_records(df: pd.DataFrame, layer_name: str):
        records: List[dict] = []
        if df.empty:
            return records

        for _, row in df.iterrows():
            label = (
                row.get("outlet_name")
                or row.get("station_name")
                or row.get("name")
                or row.get("city")
                or row.get("postcode")
                or layer_name
            )

            rec = {
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "label": str(label),
            }

            for col in ("address", "city", "state", "postcode", "phone", "email", "weight"):
                if col in df.columns and pd.notna(row.get(col)):
                    rec[col] = row[col]
            records.append(rec)
        return records

    # Build bounds from all points
    bounds_points = []
    for df in (customers_df, service_df, bp_df, non_dealer_df, competitor_bp_df, traffic_df):
        if not df.empty and {"lat", "lon"}.issubset(df.columns):
            bounds_points.extend(df[["lat", "lon"]].dropna().values.tolist())
    
    boundary = None
    if state:
        state_feature = get_admin1_feature(state)
        if state_feature:
            boundary = {
                "type": "polygon",
                "feature": state_feature,
            }

    if bounds_points and (state or city or postcode):
        lats = [p[0] for p in bounds_points]
        lons = [p[1] for p in bounds_points]
        bounds = [[min(lats), min(lons)], [max(lats), max(lons)]]
        boundary = boundary or {
            "type": "rectangle",
            "feature": rectangle_feature_from_bounds(
                bounds,
                properties={"display_name": f"{state or 'All States'}" + (f", {city}" if city else "") + (f", {postcode}" if postcode else "")},
            ),
        }

    return {
        "state": state,
        "city": city,
        "postcode": postcode,
        "boundary": boundary,
        "customers": df_to_records(customers_df, "customers"),
        "service": df_to_records(service_df, "service"),
        "bp": df_to_records(bp_df, "bp"),
        "non_dealer": df_to_records(non_dealer_df, "non_dealer"),
        "competitor_bp": df_to_records(competitor_bp_df, "competitor_bp"),
        "traffic": df_to_records(traffic_df, "traffic"),
    }


@app.get("/api/search-multi-state")
def search_multi_state(
    states: List[str] = Query(default=[], description="State names"),
    db: Session = Depends(get_db),
):
    """
    Filter data by multiple states only. City and postcode are intentionally
    excluded so this endpoint can power the multi-state comparison tab.
    """
    raw_states: List[str] = []
    for state_value in states:
        raw_states.extend([part.strip() for part in state_value.split(",") if part.strip()])

    canonical_states: List[str] = []
    seen_states = set()
    for state_value in raw_states:
        canonical = normalize_state_name(state_value)
        if not canonical:
            raise HTTPException(
                status_code=400,
                detail=f"'{state_value}' is not a recognized Malaysian state or federal territory.",
            )
        if canonical.lower() not in seen_states:
            seen_states.add(canonical.lower())
            canonical_states.append(canonical)

    if not canonical_states:
        raise HTTPException(status_code=400, detail="Please select at least one state.")

    state_lowers = [state.lower() for state in canonical_states]

    customers_base = ensure_latlon(_query_to_df(db.query(CustomerCell)), state_filter=None)
    service_base = ensure_latlon(_query_to_df(db.query(ToyotaServiceOutlet)), state_filter=None)
    bp_base = ensure_latlon(_query_to_df(db.query(ToyotaBPOutlet)), state_filter=None)
    non_dealer_base = ensure_latlon(_query_to_df(db.query(NonDealerWorkshop)), state_filter=None)
    competitor_bp_base = ensure_latlon(_query_to_df(db.query(CompetitorBPOutlet)), state_filter=None)
    traffic_base = ensure_latlon(_query_to_df(db.query(TrafficPoliceStation)), state_filter=None)

    customers_df = _filter_df_by_states(customers_base, state_lowers)
    service_df = _filter_df_by_states(service_base, state_lowers)
    bp_df = _filter_df_by_states(bp_base, state_lowers)
    non_dealer_df = _filter_df_by_states(non_dealer_base, state_lowers)
    competitor_bp_df = _filter_df_by_states(competitor_bp_base, state_lowers)
    traffic_df = _filter_df_by_states(traffic_base, state_lowers)

    boundaries = []
    missing_boundaries = []
    for state_name in canonical_states:
        feature = get_admin1_feature(state_name)
        if feature:
            boundaries.append({"type": "polygon", "feature": feature})
        else:
            missing_boundaries.append(state_name)

    return {
        "states": canonical_states,
        "boundaries": boundaries,
        "missing_boundaries": missing_boundaries,
        "customers": _df_to_map_records(customers_df, "customers"),
        "service": _df_to_map_records(service_df, "service"),
        "bp": _df_to_map_records(bp_df, "bp"),
        "non_dealer": _df_to_map_records(non_dealer_df, "non_dealer"),
        "competitor_bp": _df_to_map_records(competitor_bp_df, "competitor_bp"),
        "traffic": _df_to_map_records(traffic_df, "traffic"),
    }


def _query_to_df(query) -> pd.DataFrame:
    rows = query.all()
    if not rows:
        return pd.DataFrame()
    # Convert ORM objects to dicts
    records = [
        {
            col: getattr(row, col)
            for col in row.__table__.columns.keys()
        }
        for row in rows
    ]
    return pd.DataFrame.from_records(records)


def _df_to_map_records(df: pd.DataFrame, layer_name: str) -> List[dict]:
    records: List[dict] = []
    if df.empty:
        return records

    for _, row in df.iterrows():
        label = (
            row.get("outlet_name")
            or row.get("station_name")
            or row.get("name")
            or row.get("city")
            or row.get("postcode")
            or layer_name
        )

        rec = {
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "label": str(label),
        }

        for col in ("address", "city", "state", "postcode", "phone", "email", "weight"):
            if col in df.columns and pd.notna(row.get(col)):
                rec[col] = row[col]
        records.append(rec)
    return records


MAX_SEARCH_TERMS = 10

MALAYSIAN_STATE_LOOKUP: Dict[str, str] = {
    "johor": "Johor",
    "kedah": "Kedah",
    "kelantan": "Kelantan",
    "melaka": "Melaka",
    "malacca": "Melaka",
    "negeri sembilan": "Negeri Sembilan",
    "pahang": "Pahang",
    "penang": "Pulau Pinang",
    "pulau pinang": "Pulau Pinang",
    "perak": "Perak",
    "perlis": "Perlis",
    "sabah": "Sabah",
    "sarawak": "Sarawak",
    "selangor": "Selangor",
    "terengganu": "Terengganu",
    "kuala lumpur": "Kuala Lumpur",
    "wilayah persekutuan kuala lumpur": "Kuala Lumpur",
    "wp kuala lumpur": "Kuala Lumpur",
    "labuan": "Labuan",
    "wilayah persekutuan labuan": "Labuan",
    "wp labuan": "Labuan",
    "putrajaya": "Putrajaya",
    "wilayah persekutuan putrajaya": "Putrajaya",
    "wp putrajaya": "Putrajaya",
}


def _normalize_text(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned.endswith(", malaysia"):
        cleaned = cleaned[:-10].strip()
    cleaned = cleaned.replace(".", " ")
    cleaned = cleaned.replace("-", " ")
    return " ".join(cleaned.split())


def _normalize_state_name(raw: str) -> Optional[str]:
    normalized = _normalize_text(raw)
    return MALAYSIAN_STATE_LOOKUP.get(normalized)


def _parse_search_terms(raw_terms: str) -> List[str]:
    terms = [t.strip() for t in raw_terms.split(",") if t.strip()]
    if not terms:
        raise HTTPException(status_code=400, detail="Please provide at least one search term.")
    if len(terms) > MAX_SEARCH_TERMS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_SEARCH_TERMS} search terms allowed per request.",
        )
    return terms


def _validate_search_terms(terms: List[str], search_type: str) -> List[Dict[str, str]]:
    validated: List[Dict[str, str]] = []
    for raw in terms:
        if search_type == "state":
            canonical = _normalize_state_name(raw)
            if not canonical:
                raise HTTPException(
                    status_code=400,
                    detail=f"'{raw}' is not a recognized Malaysian state or federal territory.",
                )
            validated.append(
                {
                    "raw": raw,
                    "geocode_query": f"{canonical}, Malaysia",
                    "display_name": canonical,
                    "state_lower": canonical.lower(),
                }
            )
        elif search_type == "postcode":
            digits = raw.strip().replace(" ", "")
            if not digits.isdigit() or len(digits) not in (4, 5):
                raise HTTPException(
                    status_code=400,
                    detail=f"Postcodes must be 4 or 5 digits: '{raw}'.",
                )
            validated.append(
                {
                    "raw": raw,
                    "geocode_query": digits,
                    "display_name": digits,
                }
            )
        else:  # area / township
            cleaned = raw.strip()
            if cleaned and cleaned[0].isdigit():
                raise HTTPException(
                    status_code=400,
                    detail=f"Area/Township names cannot start with a number: '{raw}'.",
                )
            validated.append(
                {
                    "raw": raw,
                    "geocode_query": cleaned,
                    "display_name": cleaned,
                }
            )
    return validated


def _filter_df_by_states(df: pd.DataFrame, states_lower: List[str]) -> pd.DataFrame:
    if df.empty or "state" not in df.columns:
        return df.iloc[0:0].copy()
    state_series = df["state"].apply(
        lambda value: (normalize_state_name(str(value)) or str(value)).strip().lower()
    )
    mask = state_series.isin(set(states_lower))
    return df.loc[mask].copy()


def _append_unique_records(
    target: List[Dict[str, Any]],
    seen: set,
    new_records: List[Dict[str, Any]],
) -> None:
    for rec in new_records:
        lat = float(rec.get("lat", 0.0))
        lon = float(rec.get("lon", 0.0))
        label = rec.get("label", "")
        postcode = rec.get("postcode", "")
        key = (round(lat, 6), round(lon, 6), label, postcode)
        if key not in seen:
            seen.add(key)
            target.append(rec)


def _compute_bounds_from_points(points: List[List[float]]) -> Optional[List[List[float]]]:
    if not points:
        return None
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def _build_boundary_payload(
    display_name: str,
    polygon_feature: Optional[Dict[str, Any]],
    admin_bounds: Optional[List[List[float]]],
    fallback_bounds: Optional[List[List[float]]],
    center: Tuple[float, float],
    search_type: str,
    radius_km: Optional[float],
) -> Optional[Dict[str, Any]]:
    if polygon_feature:
        return {"type": "polygon", "feature": polygon_feature}
    if admin_bounds:
        rect_feature = rectangle_feature_from_bounds(
            admin_bounds,
            properties={"display_name": display_name, "source": "nominatim-boundingbox"},
        )
        if rect_feature:
            return {"type": "rectangle", "feature": rect_feature}
    if fallback_bounds:
        rect_feature = rectangle_feature_from_bounds(
            fallback_bounds,
            properties={"display_name": display_name, "source": "data-extent"},
        )
        if rect_feature:
            return {"type": "rectangle", "feature": rect_feature}
    if search_type != "state" and radius_km:
        return {
            "type": "circle",
            "center": {"lat": center[0], "lon": center[1]},
            "radius_km": float(radius_km),
        }
    return None


@app.get("/", response_class=HTMLResponse)
def admin_home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "admin_home.html", {"request": request})


@app.get("/interactive-map", response_class=HTMLResponse)
def interactive_map(request: Request) -> HTMLResponse:
    """
    Render the interactive Leaflet-based map with search UI.
    """
    return templates.TemplateResponse(request, "interactive_map.html", {"request": request})


@app.get("/api/search")
def search_locations(
    term: str = Query(..., min_length=1, description="Location name, state, area/township, or postcode"),
    search_type: str = Query("area", description="Search type: state, area, or postcode"),
    radius_km: float | None = Query(10.0, gt=0, le=100, description="Search radius in kilometers (only for area/postcode)"),
    db: Session = Depends(get_db),
):
    """
    Search by state, area/township, or postcode using online geocoding (OpenStreetMap).
    Returns all nearby data: customers, outlet/workshop layers, and traffic police stations.
    """
    search_type = search_type.lower().strip()
    if search_type not in ["state", "area", "postcode"]:
        raise HTTPException(status_code=400, detail="search_type must be 'state', 'area', or 'postcode'")

    terms = _parse_search_terms(term)
    validated_terms = _validate_search_terms(terms, search_type)

    if search_type != "state":
        if radius_km is None or radius_km <= 0:
            raise HTTPException(status_code=400, detail="radius_km is required and must be greater than 0 for area/postcode searches")
    else:
        radius_km = None

    customers_base = ensure_latlon(_query_to_df(db.query(CustomerCell)), state_filter=None)
    service_base = ensure_latlon(_query_to_df(db.query(ToyotaServiceOutlet)), state_filter=None)
    bp_base = ensure_latlon(_query_to_df(db.query(ToyotaBPOutlet)), state_filter=None)
    non_dealer_base = ensure_latlon(_query_to_df(db.query(NonDealerWorkshop)), state_filter=None)
    competitor_bp_base = ensure_latlon(_query_to_df(db.query(CompetitorBPOutlet)), state_filter=None)
    traffic_base = ensure_latlon(_query_to_df(db.query(TrafficPoliceStation)), state_filter=None)

    def df_to_records(df: pd.DataFrame, layer_name: str):
        records: List[dict] = []
        if df.empty:
            return records

        for _, row in df.iterrows():
            label = (
                row.get("outlet_name")
                or row.get("station_name")
                or row.get("name")
                or row.get("city")
                or row.get("postcode")
                or layer_name
            )

            rec = {
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "label": str(label),
            }

            for col in ("address", "city", "state", "postcode", "phone", "email", "weight"):
                if col in df.columns and pd.notna(row.get(col)):
                    rec[col] = row[col]
            records.append(rec)
        return records

    aggregated_records: Dict[str, List[Dict[str, Any]]] = {
        "customers": [],
        "service": [],
        "bp": [],
        "non_dealer": [],
        "competitor_bp": [],
        "traffic": [],
    }
    seen_keys: Dict[str, set] = {key: set() for key in aggregated_records.keys()}

    boundaries: List[Dict[str, Any]] = []
    failed_terms: List[Dict[str, str]] = []

    for term_info in validated_terms:
        geocode_result = geocode_location_with_details(term_info["geocode_query"])
        if not geocode_result:
            failed_terms.append({"term": term_info["raw"], "reason": "Location not found"})
            continue

        center_lat = geocode_result["lat"]
        center_lon = geocode_result["lon"]
        display_name = geocode_result.get("display_name", term_info["display_name"])
        polygon_feature = (
            get_admin1_feature(term_info["display_name"])
            if search_type == "state"
            else None
        ) or extract_polygon_feature(geocode_result)
        admin_bounds = extract_bounding_box(geocode_result)

        if search_type == "state":
            state_lower = term_info["state_lower"]
            customers_df = _filter_df_by_states(customers_base, [state_lower])
            service_df = _filter_df_by_states(service_base, [state_lower])
            bp_df = _filter_df_by_states(bp_base, [state_lower])
            non_dealer_df = _filter_df_by_states(non_dealer_base, [state_lower])
            competitor_bp_df = _filter_df_by_states(competitor_bp_base, [state_lower])
            traffic_df = _filter_df_by_states(traffic_base, [state_lower])
        else:
            customers_df = filter_by_radius(customers_base, center_lat, center_lon, radius_km)
            service_df = filter_by_radius(service_base, center_lat, center_lon, radius_km)
            bp_df = filter_by_radius(bp_base, center_lat, center_lon, radius_km)
            non_dealer_df = filter_by_radius(non_dealer_base, center_lat, center_lon, radius_km)
            competitor_bp_df = filter_by_radius(competitor_bp_base, center_lat, center_lon, radius_km)
            traffic_df = filter_by_radius(traffic_base, center_lat, center_lon, radius_km)

        _append_unique_records(
            aggregated_records["customers"],
            seen_keys["customers"],
            df_to_records(customers_df, "customers"),
        )
        _append_unique_records(
            aggregated_records["service"],
            seen_keys["service"],
            df_to_records(service_df, "service"),
        )
        _append_unique_records(
            aggregated_records["bp"],
            seen_keys["bp"],
            df_to_records(bp_df, "bp"),
        )
        _append_unique_records(
            aggregated_records["non_dealer"],
            seen_keys["non_dealer"],
            df_to_records(non_dealer_df, "non_dealer"),
        )
        _append_unique_records(
            aggregated_records["competitor_bp"],
            seen_keys["competitor_bp"],
            df_to_records(competitor_bp_df, "competitor_bp"),
        )
        _append_unique_records(
            aggregated_records["traffic"],
            seen_keys["traffic"],
            df_to_records(traffic_df, "traffic"),
        )

        points: List[List[float]] = []
        for df in (customers_df, service_df, bp_df, non_dealer_df, competitor_bp_df, traffic_df):
            if not df.empty and {"lat", "lon"}.issubset(df.columns):
                points.extend(df[["lat", "lon"]].dropna().values.tolist())

        fallback_bounds = None if admin_bounds else _compute_bounds_from_points(points)

        if search_type == "state":
            boundary_payload = _build_boundary_payload(
                display_name,
                polygon_feature,
                admin_bounds,
                fallback_bounds,
                (center_lat, center_lon),
                search_type,
                radius_km,
            )
            boundary_admin = admin_bounds
            boundary_fallback = fallback_bounds
            boundary_radius = None
        else:
            boundary_payload = {
                "type": "circle",
                "center": {"lat": center_lat, "lon": center_lon},
                "radius_km": float(radius_km) if radius_km else None,
            }
            boundary_admin = None
            boundary_fallback = None
            boundary_radius = float(radius_km) if radius_km else None

        boundaries.append(
            {
                "term": term_info["raw"],
                "display_name": display_name,
                "center": {"lat": center_lat, "lon": center_lon},
                "radius_km": boundary_radius,
                "boundary": boundary_payload,
                "admin_bounds": boundary_admin,
                "fallback_bounds": boundary_fallback,
            }
        )

    if not boundaries:
        detail = "None of the locations were found."
        if failed_terms:
            detail = "None of the locations were found: " + ", ".join(ft["term"] for ft in failed_terms)
        raise HTTPException(status_code=404, detail=detail)

    return {
        "search_type": search_type,
        "radius_km": float(radius_km) if radius_km else None,
        "boundaries": boundaries,
        "failed_terms": failed_terms,
        "customers": aggregated_records["customers"],
        "service": aggregated_records["service"],
        "bp": aggregated_records["bp"],
        "non_dealer": aggregated_records["non_dealer"],
        "competitor_bp": aggregated_records["competitor_bp"],
        "traffic": aggregated_records["traffic"],
    }


@app.get("/api/search-multiple")
def search_multiple_locations(
    terms: str = Query(..., description="Comma-separated location names or postcodes"),
    radius_km: float = Query(10.0, gt=0, le=100, description="Search radius in kilometers"),
    db: Session = Depends(get_db),
):
    """
    Search by multiple location names / postcodes using OpenStreetMap Nominatim.
    Returns all nearby data within radius of ANY of the specified locations.
    """
    # Parse comma-separated terms
    term_list = [t.strip() for t in terms.split(",") if t.strip()]
    if not term_list:
        raise HTTPException(status_code=400, detail="Please provide at least one location.")
    
    if len(term_list) > 10:  # Limit to prevent abuse
        raise HTTPException(status_code=400, detail="Maximum 10 locations allowed per search.")

    # Geocode all locations (with rate limiting built-in)
    geocode_results = geocode_multiple_locations(term_list, delay_seconds=1.2)
    
    centers = [r for r in geocode_results if r["success"]]
    failed_terms = [r["term"] for r in geocode_results if not r["success"]]

    if not centers:
        raise HTTPException(
            status_code=404,
            detail=f"None of the locations were found: {', '.join(failed_terms)}"
        )

    # Load all database data
    customers_df = ensure_latlon(_query_to_df(db.query(CustomerCell)), state_filter=None)
    service_df = ensure_latlon(_query_to_df(db.query(ToyotaServiceOutlet)), state_filter=None)
    bp_df = ensure_latlon(_query_to_df(db.query(ToyotaBPOutlet)), state_filter=None)
    non_dealer_df = ensure_latlon(_query_to_df(db.query(NonDealerWorkshop)), state_filter=None)
    competitor_bp_df = ensure_latlon(_query_to_df(db.query(CompetitorBPOutlet)), state_filter=None)
    traffic_df = ensure_latlon(_query_to_df(db.query(TrafficPoliceStation)), state_filter=None)

    # Filter by radius around ANY of the centers
    def filter_by_multiple_radius(df: pd.DataFrame, centers_list: list, radius: float):
        if df.empty:
            return df.copy()
        
        # Create a mask for points within radius of ANY center
        mask = pd.Series([False] * len(df), index=df.index)
        
        for center in centers_list:
            center_df = filter_by_radius(df, center["lat"], center["lon"], radius)
            mask = mask | df.index.isin(center_df.index)
        
        return df.loc[mask].copy()

    customers_df = filter_by_multiple_radius(customers_df, centers, radius_km)
    service_df = filter_by_multiple_radius(service_df, centers, radius_km)
    bp_df = filter_by_multiple_radius(bp_df, centers, radius_km)
    non_dealer_df = filter_by_multiple_radius(non_dealer_df, centers, radius_km)
    competitor_bp_df = filter_by_multiple_radius(competitor_bp_df, centers, radius_km)
    traffic_df = filter_by_multiple_radius(traffic_df, centers, radius_km)

    def df_to_records(df: pd.DataFrame, layer_name: str):
        records: List[dict] = []
        if df.empty:
            return records

        for _, row in df.iterrows():
            label = (
                row.get("outlet_name")
                or row.get("station_name")
                or row.get("name")
                or row.get("city")
                or row.get("postcode")
                or layer_name
            )

            rec = {
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "label": str(label),
            }

            for col in ("address", "city", "state", "postcode", "phone", "email", "weight"):
                if col in df.columns and pd.notna(row.get(col)):
                    rec[col] = row[col]
            records.append(rec)
        return records

    return {
        "centers": [{"term": c["term"], "lat": c["lat"], "lon": c["lon"]} for c in centers],
        "failed_terms": failed_terms,
        "radius_km": float(radius_km),
        "customers": df_to_records(customers_df, "customers"),
        "service": df_to_records(service_df, "service"),
        "bp": df_to_records(bp_df, "bp"),
        "non_dealer": df_to_records(non_dealer_df, "non_dealer"),
        "competitor_bp": df_to_records(competitor_bp_df, "competitor_bp"),
        "traffic": df_to_records(traffic_df, "traffic"),
    }


@app.get("/admin/service-outlets", response_class=HTMLResponse)
def list_service_outlets(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    outlets = db.query(ToyotaServiceOutlet).order_by(ToyotaServiceOutlet.id).all()
    return templates.TemplateResponse(
        request,
        "service_outlets.html",
        {"request": request, "outlets": outlets},
    )


@app.post("/admin/service-outlets")
def create_service_outlet(
    request: Request,
    outlet_name: str = Form(...),
    address: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    postcode: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    phone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    outlet = ToyotaServiceOutlet(
        outlet_name=outlet_name,
        address=address,
        city=city,
        state=state,
        postcode=postcode,
        lat=lat,
        lon=lon,
        phone=phone,
        email=email,
    )
    db.add(outlet)
    db.commit()
    return RedirectResponse("/admin/service-outlets", status_code=303)


@app.get("/admin/service-outlets/{outlet_id}/edit", response_class=HTMLResponse)
def edit_service_outlet_form(
    outlet_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    outlet = db.get(ToyotaServiceOutlet, outlet_id)
    if not outlet:
        raise HTTPException(status_code=404, detail="Service outlet not found")
    return templates.TemplateResponse(
        request, "service_outlet_edit.html", {"request": request, "outlet": outlet}
    )


@app.post("/admin/service-outlets/{outlet_id}/edit")
def update_service_outlet(
    outlet_id: int,
    request: Request,
    outlet_name: str = Form(...),
    city: str = Form(""),
    state: str = Form(""),
    postcode: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    db: Session = Depends(get_db),
):
    outlet = db.get(ToyotaServiceOutlet, outlet_id)
    if not outlet:
        raise HTTPException(status_code=404, detail="Service outlet not found")

    outlet.outlet_name = outlet_name
    outlet.city = city
    outlet.state = state
    outlet.postcode = postcode
    outlet.lat = lat
    outlet.lon = lon
    db.commit()
    return RedirectResponse("/admin/service-outlets", status_code=303)


@app.get("/admin/bp-outlets", response_class=HTMLResponse)
def list_bp_outlets(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    outlets = db.query(ToyotaBPOutlet).order_by(ToyotaBPOutlet.id).all()
    return templates.TemplateResponse(
        request,
        "bp_outlets.html",
        {"request": request, "outlets": outlets},
    )


@app.post("/admin/bp-outlets")
def create_bp_outlet(
    request: Request,
    outlet_name: str = Form(...),
    address: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    postcode: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    phone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    outlet = ToyotaBPOutlet(
        outlet_name=outlet_name,
        address=address,
        city=city,
        state=state,
        postcode=postcode,
        lat=lat,
        lon=lon,
        phone=phone,
        email=email,
    )
    db.add(outlet)
    db.commit()
    return RedirectResponse("/admin/bp-outlets", status_code=303)


@app.get("/admin/bp-outlets/{outlet_id}/edit", response_class=HTMLResponse)
def edit_bp_outlet_form(
    outlet_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    outlet = db.get(ToyotaBPOutlet, outlet_id)
    if not outlet:
        raise HTTPException(status_code=404, detail="Body & Paint outlet not found")
    return templates.TemplateResponse(
        request,
        "bp_outlet_edit.html",
        {"request": request, "outlet": outlet},
    )


@app.post("/admin/bp-outlets/{outlet_id}/edit")
def update_bp_outlet(
    outlet_id: int,
    request: Request,
    outlet_name: str = Form(...),
    city: str = Form(""),
    state: str = Form(""),
    postcode: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    db: Session = Depends(get_db),
):
    outlet = db.get(ToyotaBPOutlet, outlet_id)
    if not outlet:
        raise HTTPException(status_code=404, detail="Body & Paint outlet not found")

    outlet.outlet_name = outlet_name
    outlet.city = city
    outlet.state = state
    outlet.postcode = postcode
    outlet.lat = lat
    outlet.lon = lon
    db.commit()
    return RedirectResponse("/admin/bp-outlets", status_code=303)


@app.get("/admin/non-dealer-workshops", response_class=HTMLResponse)
def list_non_dealer_workshops(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    outlets = db.query(NonDealerWorkshop).order_by(NonDealerWorkshop.id).all()
    return templates.TemplateResponse(
        request,
        "non_dealer_workshops.html",
        {"request": request, "outlets": outlets},
    )


@app.post("/admin/non-dealer-workshops")
def create_non_dealer_workshop(
    request: Request,
    outlet_name: str = Form(...),
    address: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    postcode: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    phone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    outlet = NonDealerWorkshop(
        outlet_name=outlet_name,
        address=address,
        city=city,
        state=state,
        postcode=postcode,
        lat=lat,
        lon=lon,
        phone=phone,
        email=email,
    )
    db.add(outlet)
    db.commit()
    return RedirectResponse("/admin/non-dealer-workshops", status_code=303)


@app.get("/admin/non-dealer-workshops/{outlet_id}/edit", response_class=HTMLResponse)
def edit_non_dealer_workshop_form(
    outlet_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    outlet = db.get(NonDealerWorkshop, outlet_id)
    if not outlet:
        raise HTTPException(status_code=404, detail="Non-dealer workshop not found")
    return templates.TemplateResponse(
        request,
        "non_dealer_workshop_edit.html",
        {"request": request, "outlet": outlet},
    )


@app.post("/admin/non-dealer-workshops/{outlet_id}/edit")
def update_non_dealer_workshop(
    outlet_id: int,
    request: Request,
    outlet_name: str = Form(...),
    city: str = Form(""),
    state: str = Form(""),
    postcode: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    db: Session = Depends(get_db),
):
    outlet = db.get(NonDealerWorkshop, outlet_id)
    if not outlet:
        raise HTTPException(status_code=404, detail="Non-dealer workshop not found")

    outlet.outlet_name = outlet_name
    outlet.city = city
    outlet.state = state
    outlet.postcode = postcode
    outlet.lat = lat
    outlet.lon = lon
    db.commit()
    return RedirectResponse("/admin/non-dealer-workshops", status_code=303)


@app.get("/admin/competitor-bp", response_class=HTMLResponse)
def list_competitor_bp_outlets(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    outlets = db.query(CompetitorBPOutlet).order_by(CompetitorBPOutlet.id).all()
    return templates.TemplateResponse(
        request,
        "competitor_bp_outlets.html",
        {"request": request, "outlets": outlets},
    )


@app.post("/admin/competitor-bp")
def create_competitor_bp_outlet(
    request: Request,
    outlet_name: str = Form(...),
    address: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    postcode: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    phone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    outlet = CompetitorBPOutlet(
        outlet_name=outlet_name,
        address=address,
        city=city,
        state=state,
        postcode=postcode,
        lat=lat,
        lon=lon,
        phone=phone,
        email=email,
    )
    db.add(outlet)
    db.commit()
    return RedirectResponse("/admin/competitor-bp", status_code=303)


@app.get("/admin/competitor-bp/{outlet_id}/edit", response_class=HTMLResponse)
def edit_competitor_bp_outlet_form(
    outlet_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    outlet = db.get(CompetitorBPOutlet, outlet_id)
    if not outlet:
        raise HTTPException(status_code=404, detail="Competitor B&P outlet not found")
    return templates.TemplateResponse(
        request,
        "competitor_bp_outlet_edit.html",
        {"request": request, "outlet": outlet},
    )


@app.post("/admin/competitor-bp/{outlet_id}/edit")
def update_competitor_bp_outlet(
    outlet_id: int,
    request: Request,
    outlet_name: str = Form(...),
    city: str = Form(""),
    state: str = Form(""),
    postcode: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    db: Session = Depends(get_db),
):
    outlet = db.get(CompetitorBPOutlet, outlet_id)
    if not outlet:
        raise HTTPException(status_code=404, detail="Competitor B&P outlet not found")

    outlet.outlet_name = outlet_name
    outlet.city = city
    outlet.state = state
    outlet.postcode = postcode
    outlet.lat = lat
    outlet.lon = lon
    db.commit()
    return RedirectResponse("/admin/competitor-bp", status_code=303)


@app.get("/admin/traffic-stations", response_class=HTMLResponse)
def list_traffic_stations(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    stations = db.query(TrafficPoliceStation).order_by(TrafficPoliceStation.id).all()
    return templates.TemplateResponse(
        request,
        "traffic_stations.html",
        {"request": request, "stations": stations},
    )


@app.post("/admin/traffic-stations")
def create_traffic_station(
    request: Request,
    station_name: str = Form(...),
    address: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    postcode: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    phone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    station = TrafficPoliceStation(
        station_name=station_name,
        address=address,
        city=city,
        state=state,
        postcode=postcode,
        lat=lat,
        lon=lon,
        phone=phone,
        email=email,
    )
    db.add(station)
    db.commit()
    return RedirectResponse("/admin/traffic-stations", status_code=303)


@app.get("/admin/traffic-stations/{station_id}/edit", response_class=HTMLResponse)
def edit_traffic_station_form(
    station_id: int, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    station = db.get(TrafficPoliceStation, station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Traffic station not found")
    return templates.TemplateResponse(
        request,
        "traffic_station_edit.html",
        {"request": request, "station": station},
    )


@app.post("/admin/traffic-stations/{station_id}/edit")
def update_traffic_station(
    station_id: int,
    request: Request,
    station_name: str = Form(...),
    city: str = Form(""),
    state: str = Form(""),
    postcode: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    db: Session = Depends(get_db),
):
    station = db.get(TrafficPoliceStation, station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Traffic station not found")

    station.station_name = station_name
    station.city = city
    station.state = state
    station.postcode = postcode
    station.lat = lat
    station.lon = lon
    db.commit()
    return RedirectResponse("/admin/traffic-stations", status_code=303)


@app.get("/admin/customers/upload", response_class=HTMLResponse)
def upload_customers_form(request: Request) -> HTMLResponse:
    return upload_csv_form(request)


@app.get("/admin/upload-csv", response_class=HTMLResponse)
def upload_csv_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "customers_upload.html",
        _upload_template_context(request),
    )


def _clean_customer_upload_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _parse_customer_upload_float(value: Any, field_name: str, line_number: int) -> float:
    text = _clean_customer_upload_text(value).replace(",", "")
    if not text:
        raise ValueError(f"Line {line_number}: {field_name} is required.")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(
            f"Line {line_number}: {field_name} must be numeric, got {value!r}."
        ) from exc


def _normalize_customer_upload_state(value: Any, line_number: int) -> str:
    text = _clean_customer_upload_text(value)
    if not text:
        raise ValueError(f"Line {line_number}: state is required.")
    canonical = normalize_state_name(text)
    if not canonical:
        raise ValueError(
            f"Line {line_number}: state must be a full Malaysian state or federal "
            f"territory name, got {text!r}."
        )
    return canonical


def _validate_customer_upload_coordinates(lat: float, lon: float, line_number: int) -> None:
    south, west = MALAYSIA_BOUNDS[0]
    north, east = MALAYSIA_BOUNDS[1]
    if not (south <= lat <= north and west <= lon <= east):
        raise ValueError(
            f"Line {line_number}: lat/lon must be within Malaysia bounds "
            f"({south} to {north}, {west} to {east}), got {lat}, {lon}."
        )


CSV_UPLOAD_CONFIGS: Dict[str, Dict[str, Any]] = {
    "service_outlets": {
        "label": "Service Outlets",
        "model": ToyotaServiceOutlet,
        "name_column": "outlet_name",
        "required_columns": ["outlet_name", "city", "state", "postcode", "lat", "lon"],
        "optional_columns": ["address", "phone", "email"],
        "sample": {
            "outlet_name": "Toyota Example Service Centre",
            "address": "Lot 1, Jalan Example",
            "city": "Shah Alam",
            "state": "Selangor",
            "postcode": "40000",
            "lat": "3.0738",
            "lon": "101.5183",
            "phone": "03-1234 5678",
            "email": "service@example.com",
        },
    },
    "body_paint": {
        "label": "Body and Paint",
        "model": ToyotaBPOutlet,
        "name_column": "outlet_name",
        "required_columns": ["outlet_name", "city", "state", "postcode", "lat", "lon"],
        "optional_columns": ["address", "phone", "email"],
        "sample": {
            "outlet_name": "Toyota Example Body & Paint",
            "address": "Lot 2, Jalan Workshop",
            "city": "Klang",
            "state": "Selangor",
            "postcode": "41000",
            "lat": "3.0449",
            "lon": "101.4456",
            "phone": "03-2345 6789",
            "email": "bp@example.com",
        },
    },
    "non_dealer_workshops": {
        "label": "Non-Dealer Workshops",
        "model": NonDealerWorkshop,
        "name_column": "outlet_name",
        "required_columns": ["outlet_name", "city", "state", "postcode", "lat", "lon"],
        "optional_columns": ["address", "phone", "email"],
        "sample": {
            "outlet_name": "Example Independent Workshop",
            "address": "12, Jalan Industri",
            "city": "Petaling Jaya",
            "state": "Selangor",
            "postcode": "46000",
            "lat": "3.1073",
            "lon": "101.6067",
            "phone": "03-3456 7890",
            "email": "workshop@example.com",
        },
    },
    "competitor_bp": {
        "label": "Competitor B&P",
        "model": CompetitorBPOutlet,
        "name_column": "outlet_name",
        "required_columns": ["outlet_name", "city", "state", "postcode", "lat", "lon"],
        "optional_columns": ["address", "phone", "email"],
        "sample": {
            "outlet_name": "Example Competitor Body & Paint",
            "address": "8, Jalan Paint",
            "city": "Kajang",
            "state": "Selangor",
            "postcode": "43000",
            "lat": "2.9935",
            "lon": "101.7874",
            "phone": "03-4567 8901",
            "email": "competitor@example.com",
        },
    },
    "traffic_stations": {
        "label": "Traffic Stations",
        "model": TrafficPoliceStation,
        "name_column": "station_name",
        "required_columns": ["station_name", "city", "state", "postcode", "lat", "lon"],
        "optional_columns": ["address", "phone", "email"],
        "sample": {
            "station_name": "Balai Polis Trafik Example",
            "address": "Jalan Polis",
            "city": "Kuala Lumpur",
            "state": "Kuala Lumpur",
            "postcode": "50560",
            "lat": "3.1569",
            "lon": "101.7020",
            "phone": "03-5678 9012",
            "email": "traffic@example.com",
        },
    },
    "customer_density": {
        "label": "Customer Density",
        "model": CustomerCell,
        "name_column": None,
        "required_columns": ["state", "city", "postcode", "lat", "lon", "weight"],
        "optional_columns": [],
        "sample": {
            "state": "Selangor",
            "city": "Ampang",
            "postcode": "68000",
            "lat": "3.16648",
            "lon": "101.748344",
            "weight": "6265",
        },
    },
}


def _upload_config_views() -> List[Dict[str, Any]]:
    views: List[Dict[str, Any]] = []
    for key, config in CSV_UPLOAD_CONFIGS.items():
        columns = [*config["required_columns"], *config["optional_columns"]]
        views.append(
            {
                "key": key,
                "label": config["label"],
                "required_columns": config["required_columns"],
                "optional_columns": config["optional_columns"],
                "columns": columns,
                "sample": config["sample"],
                "sample_csv": ",".join(columns)
                + "\n"
                + ",".join(str(config["sample"].get(column, "")) for column in columns),
            }
        )
    return views


def _upload_template_context(
    request: Request,
    selected_dataset: str = "customer_density",
    success: Optional[str] = None,
    error: Optional[Dict[str, Any]] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "request": request,
        "upload_configs": _upload_config_views(),
        "selected_dataset": selected_dataset,
        "success": success,
        "error": error,
        "summary": summary,
    }


def _prepare_customer_upload_rows(df: pd.DataFrame) -> Tuple[List[dict], List[str]]:
    required_cols = {"state", "city", "postcode", "lat", "lon", "weight"}
    missing = required_cols - set(df.columns)
    if missing:
        return [], [f"Missing columns in CSV: {', '.join(sorted(missing))}"]
    if df.empty:
        return [], ["The CSV has no data rows."]

    prepared_rows: List[dict] = []
    errors: List[str] = []

    for idx, row in df.iterrows():
        line_number = idx + 2
        try:
            state = _normalize_customer_upload_state(row.get("state"), line_number)
            city = _clean_customer_upload_text(row.get("city"))
            postcode = _clean_customer_upload_text(row.get("postcode"))
            if not city:
                raise ValueError(f"Line {line_number}: city is required.")
            if not postcode:
                raise ValueError(f"Line {line_number}: postcode is required.")
            lat = _parse_customer_upload_float(row.get("lat"), "lat", line_number)
            lon = _parse_customer_upload_float(row.get("lon"), "lon", line_number)
            _validate_customer_upload_coordinates(lat, lon, line_number)

            prepared_rows.append(
                {
                    "state": state,
                    "city": city,
                    "postcode": postcode,
                    "lat": lat,
                    "lon": lon,
                    "weight": _parse_customer_upload_float(
                        row.get("weight"), "weight", line_number
                    ),
                }
            )
        except ValueError as exc:
            errors.append(str(exc))

    return prepared_rows, errors


def _prepare_location_upload_rows(
    df: pd.DataFrame,
    config: Dict[str, Any],
) -> Tuple[List[dict], List[str]]:
    required_cols = set(config["required_columns"])
    missing = required_cols - set(df.columns)
    if missing:
        return [], [f"Missing columns in CSV: {', '.join(sorted(missing))}"]
    if df.empty:
        return [], ["The CSV has no data rows."]

    prepared_rows: List[dict] = []
    errors: List[str] = []
    name_column = config["name_column"]

    for idx, row in df.iterrows():
        line_number = idx + 2
        try:
            name = _clean_customer_upload_text(row.get(name_column))
            state = _normalize_customer_upload_state(row.get("state"), line_number)
            city = _clean_customer_upload_text(row.get("city"))
            postcode = _clean_customer_upload_text(row.get("postcode"))
            if not name:
                raise ValueError(f"Line {line_number}: {name_column} is required.")
            if not city:
                raise ValueError(f"Line {line_number}: city is required.")
            if not postcode:
                raise ValueError(f"Line {line_number}: postcode is required.")
            lat = _parse_customer_upload_float(row.get("lat"), "lat", line_number)
            lon = _parse_customer_upload_float(row.get("lon"), "lon", line_number)
            _validate_customer_upload_coordinates(lat, lon, line_number)

            prepared_row = {
                name_column: name,
                "address": _clean_customer_upload_text(row.get("address")),
                "city": city,
                "state": state,
                "postcode": postcode,
                "lat": lat,
                "lon": lon,
                "phone": _clean_customer_upload_text(row.get("phone")),
                "email": _clean_customer_upload_text(row.get("email")),
            }
            prepared_rows.append(prepared_row)
        except ValueError as exc:
            errors.append(str(exc))

    return prepared_rows, errors


def _prepare_csv_upload_rows(
    df: pd.DataFrame,
    dataset: str,
) -> Tuple[List[dict], List[str]]:
    if dataset == "customer_density":
        return _prepare_customer_upload_rows(df)
    config = CSV_UPLOAD_CONFIGS[dataset]
    return _prepare_location_upload_rows(df, config)


def _customer_upload_summary(previous_count: int, prepared_rows: List[dict]) -> dict:
    states = sorted({row["state"] for row in prepared_rows})
    total_weight = sum(row["weight"] for row in prepared_rows)
    return {
        "previous_count": previous_count,
        "new_count": len(prepared_rows),
        "rows_replaced": previous_count,
        "states": states,
        "state_count": len(states),
        "city_count": len({(row["state"], row["city"]) for row in prepared_rows}),
        "postcode_count": len({row["postcode"] for row in prepared_rows}),
        "total_weight": total_weight,
        "total_weight_text": f"{total_weight:,.0f}",
    }


def _csv_upload_summary(dataset: str, previous_count: int, prepared_rows: List[dict]) -> dict:
    config = CSV_UPLOAD_CONFIGS[dataset]
    summary = {
        "dataset": dataset,
        "dataset_label": config["label"],
        "previous_count": previous_count,
        "new_count": len(prepared_rows),
        "rows_replaced": previous_count,
        "states": sorted({row["state"] for row in prepared_rows if row.get("state")}),
        "state_count": len({row["state"] for row in prepared_rows if row.get("state")}),
        "city_count": len(
            {(row.get("state"), row.get("city")) for row in prepared_rows if row.get("city")}
        ),
        "postcode_count": len({row["postcode"] for row in prepared_rows if row.get("postcode")}),
        "changed_table": config["model"].__tablename__,
    }
    if dataset == "customer_density":
        total_weight = sum(row["weight"] for row in prepared_rows)
        summary["total_weight"] = total_weight
        summary["total_weight_text"] = f"{total_weight:,.0f}"
    return summary


@app.post("/admin/customers/upload")
async def upload_customers_csv(
    request: Request,
    file: UploadFile = File(...),
    dataset: str = Form("customer_density"),
    db: Session = Depends(get_db),
):
    return await upload_csv(request=request, file=file, dataset=dataset, db=db)


@app.post("/admin/upload-csv")
async def upload_csv(
    request: Request,
    file: UploadFile = File(...),
    dataset: str = Form("customer_density"),
    db: Session = Depends(get_db),
):
    if dataset not in CSV_UPLOAD_CONFIGS:
        return templates.TemplateResponse(
            request,
            "customers_upload.html",
            _upload_template_context(
                request,
                selected_dataset="customer_density",
                error={
                    "message": "Please choose a valid data type before uploading.",
                    "details": [],
                },
            ),
            status_code=400,
        )

    if not file.filename.lower().endswith(".csv"):
        return templates.TemplateResponse(
            request,
            "customers_upload.html",
            _upload_template_context(
                request,
                selected_dataset=dataset,
                error={
                    "message": "Please upload a CSV file.",
                    "details": [],
                },
            ),
            status_code=400,
        )

    content = await file.read()
    try:
        df = pd.read_csv(pd.io.common.BytesIO(content), dtype=str)
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "customers_upload.html",
            _upload_template_context(
                request,
                selected_dataset=dataset,
                error={
                    "message": "The CSV could not be read.",
                    "details": [str(exc)],
                },
            ),
            status_code=400,
        )

    df.columns = [c.strip().lower() for c in df.columns]
    prepared_rows, errors = _prepare_csv_upload_rows(df, dataset)
    if errors:
        return templates.TemplateResponse(
            request,
            "customers_upload.html",
            _upload_template_context(
                request,
                selected_dataset=dataset,
                error={
                    "message": (
                        "The CSV was not uploaded because some rows need to be fixed. "
                        "No database changes were made."
                    ),
                    "details": errors[:20],
                    "hidden_count": max(len(errors) - 20, 0),
                },
            ),
            status_code=400,
        )

    config = CSV_UPLOAD_CONFIGS[dataset]
    model = config["model"]
    previous_count = db.query(model).count()
    db.query(model).delete()

    for row in prepared_rows:
        db.add(model(**row))
    db.commit()

    return templates.TemplateResponse(
        request,
        "customers_upload.html",
        _upload_template_context(
            request,
            selected_dataset=dataset,
            success=f"{file.filename} uploaded successfully for {config['label']}.",
            summary=_csv_upload_summary(dataset, previous_count, prepared_rows),
        ),
    )



