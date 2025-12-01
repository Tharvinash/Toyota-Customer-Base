from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.requests import Request

from db import (
    CustomerCell,
    ToyotaBPOutlet,
    ToyotaServiceOutlet,
    TrafficPoliceStation,
    get_db,
    init_db,
)
from map_utils import (
    ensure_latlon,
    geocode_location,
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


@app.get("/", response_class=HTMLResponse)
def admin_home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("admin_home.html", {"request": request})


@app.get("/interactive-map", response_class=HTMLResponse)
def interactive_map(request: Request) -> HTMLResponse:
    """
    Render the interactive Leaflet-based map with search UI.
    """
    return templates.TemplateResponse("interactive_map.html", {"request": request})


@app.get("/api/search")
def search_locations(
    term: str = Query(..., min_length=1, description="Location name, state, area/township, or postcode"),
    search_type: str = Query("area", description="Search type: state, area, or postcode"),
    radius_km: float | None = Query(10.0, gt=0, le=100, description="Search radius in kilometers (only for area/postcode)"),
    db: Session = Depends(get_db),
):
    """
    Search by state, area/township, or postcode using online geocoding (OpenStreetMap).
    Returns all nearby data: customers, service outlets, BP outlets, and traffic police stations.
    """
    search_type = search_type.lower().strip()
    if search_type not in ["state", "area", "postcode"]:
        raise HTTPException(status_code=400, detail="search_type must be 'state', 'area', or 'postcode'")

    # Validate radius for area/postcode searches
    if search_type != "state":
        if radius_km is None or radius_km <= 0:
            raise HTTPException(status_code=400, detail="radius_km is required and must be greater than 0 for area/postcode searches")

    # Get coordinates and boundaries from internet geocoding service
    geocode_result = geocode_location_with_details(term)
    if geocode_result is None:
        raise HTTPException(
            status_code=404, 
            detail=f"Location '{term}' not found. Please try a different location name, state, area, or postcode."
        )

    center_lat = geocode_result["lat"]
    center_lon = geocode_result["lon"]
    display_name = geocode_result.get("display_name", term)
    polygon_feature = extract_polygon_feature(geocode_result)
    admin_bounds = extract_bounding_box(geocode_result)

    # Load all database data
    customers_df = ensure_latlon(_query_to_df(db.query(CustomerCell)))
    service_df = ensure_latlon(_query_to_df(db.query(ToyotaServiceOutlet)))
    bp_df = ensure_latlon(_query_to_df(db.query(ToyotaBPOutlet)))
    traffic_df = ensure_latlon(_query_to_df(db.query(TrafficPoliceStation)))

    # Filter data based on search type
    if search_type == "state":
        # Normalize state name for matching (remove common suffixes, case-insensitive)
        normalized_term = term.strip().lower()
        # Remove "Malaysia" suffix if present
        if normalized_term.endswith(", malaysia"):
            normalized_term = normalized_term[:-10].strip()
        
        # Filter by state column (case-insensitive, partial match)
        def filter_by_state(df: pd.DataFrame) -> pd.DataFrame:
            if df.empty or "state" not in df.columns:
                return df.copy()
            state_col = df["state"].astype(str).str.strip().str.lower()
            # Try exact match first
            mask = state_col == normalized_term
            # If no exact match, try contains match
            if not mask.any():
                mask = state_col.str.contains(normalized_term, case=False, na=False)
            return df[mask].copy()
        
        customers_df = filter_by_state(customers_df)
        service_df = filter_by_state(service_df)
        bp_df = filter_by_state(bp_df)
        traffic_df = filter_by_state(traffic_df)
        
        # No radius filtering for state search
        radius_km = None
    else:
        # Area or postcode search: apply radius filtering
        customers_df = filter_by_radius(customers_df, center_lat, center_lon, radius_km)
        service_df = filter_by_radius(service_df, center_lat, center_lon, radius_km)
        bp_df = filter_by_radius(bp_df, center_lat, center_lon, radius_km)
        traffic_df = filter_by_radius(traffic_df, center_lat, center_lon, radius_km)

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

    # Calculate fallback bounds from filtered data if no bounding box available
    fallback_bounds = None
    if not admin_bounds:
        all_points = []
        for df in [customers_df, service_df, bp_df, traffic_df]:
            if not df.empty and "lat" in df.columns and "lon" in df.columns:
                all_points.extend(df[["lat", "lon"]].dropna().values.tolist())
        
        if all_points:
            lats = [p[0] for p in all_points]
            lons = [p[1] for p in all_points]
            fallback_bounds = [[min(lats), min(lons)], [max(lats), max(lons)]]

    boundary_payload: Optional[Dict[str, Any]] = None
    if polygon_feature:
        boundary_payload = {"type": "polygon", "feature": polygon_feature}
    elif admin_bounds:
        rect_feature = rectangle_feature_from_bounds(
            admin_bounds,
            properties={
                "display_name": display_name,
                "source": "nominatim-boundingbox",
            },
        )
        if rect_feature:
            boundary_payload = {"type": "rectangle", "feature": rect_feature}
    elif fallback_bounds:
        rect_feature = rectangle_feature_from_bounds(
            fallback_bounds,
            properties={
                "display_name": display_name,
                "source": "data-extent",
            },
        )
        if rect_feature:
            boundary_payload = {"type": "rectangle", "feature": rect_feature}

    if not boundary_payload and search_type != "state" and radius_km:
        boundary_payload = {
            "type": "circle",
            "center": {"lat": center_lat, "lon": center_lon},
            "radius_km": float(radius_km),
        }

    return {
        "search_type": search_type,
        "center": {"lat": center_lat, "lon": center_lon},
        "radius_km": float(radius_km) if radius_km else None,
        "admin_boundaries": admin_bounds,
        "fallback_bounds": fallback_bounds,
        "boundary": boundary_payload,
        "customers": df_to_records(customers_df, "customers"),
        "service": df_to_records(service_df, "service"),
        "bp": df_to_records(bp_df, "bp"),
        "traffic": df_to_records(traffic_df, "traffic"),
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
    customers_df = ensure_latlon(_query_to_df(db.query(CustomerCell)))
    service_df = ensure_latlon(_query_to_df(db.query(ToyotaServiceOutlet)))
    bp_df = ensure_latlon(_query_to_df(db.query(ToyotaBPOutlet)))
    traffic_df = ensure_latlon(_query_to_df(db.query(TrafficPoliceStation)))

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
        "traffic": df_to_records(traffic_df, "traffic"),
    }


@app.get("/admin/service-outlets", response_class=HTMLResponse)
def list_service_outlets(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    outlets = db.query(ToyotaServiceOutlet).order_by(ToyotaServiceOutlet.id).all()
    return templates.TemplateResponse(
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


@app.get("/admin/bp-outlets", response_class=HTMLResponse)
def list_bp_outlets(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    outlets = db.query(ToyotaBPOutlet).order_by(ToyotaBPOutlet.id).all()
    return templates.TemplateResponse(
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


@app.get("/admin/traffic-stations", response_class=HTMLResponse)
def list_traffic_stations(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    stations = db.query(TrafficPoliceStation).order_by(TrafficPoliceStation.id).all()
    return templates.TemplateResponse(
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


@app.get("/admin/customers/upload", response_class=HTMLResponse)
def upload_customers_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("customers_upload.html", {"request": request})


@app.post("/admin/customers/upload")
async def upload_customers_csv(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    content = await file.read()
    df = pd.read_csv(pd.io.common.BytesIO(content))
    df.columns = [c.strip().lower() for c in df.columns]

    required_cols = {"state", "city", "postcode", "lat", "lon", "weight"}
    missing = required_cols - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing columns in CSV: {', '.join(sorted(missing))}",
        )

    # Clear existing customer_cells and replace with uploaded data
    db.query(CustomerCell).delete()
    db.commit()

    # Insert new rows
    for _, row in df.iterrows():
        cell = CustomerCell(
            state=row.get("state"),
            city=row.get("city"),
            postcode=str(row.get("postcode")) if pd.notna(row.get("postcode")) else None,
            lat=float(row.get("lat")),
            lon=float(row.get("lon")),
            weight=float(row.get("weight")) if pd.notna(row.get("weight")) else None,
        )
        db.add(cell)
    db.commit()

    return RedirectResponse("/", status_code=303)



