from __future__ import annotations

from typing import List
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
from map_builder import build_map
from map_utils import ensure_latlon, geocode_location, filter_by_radius


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


@app.get("/map", response_class=HTMLResponse)
def map_view(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    customers_df = _query_to_df(db.query(CustomerCell))
    service_df = _query_to_df(db.query(ToyotaServiceOutlet))
    bp_df = _query_to_df(db.query(ToyotaBPOutlet))
    traffic_df = _query_to_df(db.query(TrafficPoliceStation))

    m = build_map(customers_df, service_df, bp_df, traffic_df)
    html = m.get_root().render()
    
    # Inject viewport meta tag and mobile CSS if not present
    if 'name="viewport"' not in html:
        # Insert viewport meta tag after charset meta
        html = html.replace(
            '<meta http-equiv="content-type"',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes" />\n    <meta http-equiv="content-type"'
        )
    
    # Add mobile-specific CSS
    mobile_css = """
    <style>
        /* Mobile responsive fixes */
        @media (max-width: 768px) {
            .leaflet-control-layers {
                font-size: 12px !important;
            }
            .leaflet-control-zoom {
                font-size: 18px !important;
            }
            .leaflet-popup-content-wrapper {
                max-width: 250px !important;
                font-size: 12px !important;
            }
            .leaflet-control-minimap {
                width: 150px !important;
                height: 150px !important;
            }
        }
        /* Ensure map container is visible on mobile */
        .leaflet-container {
            touch-action: pan-x pan-y !important;
            -webkit-tap-highlight-color: transparent !important;
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
        }
        /* Ensure full height on mobile */
        html, body {
            height: 100% !important;
            width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
        }
        /* Ensure map div is visible */
        #map {
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            height: 100% !important;
            width: 100% !important;
        }
    </style>
    """
    
    # Insert mobile CSS before closing head tag
    if '</head>' in html:
        html = html.replace('</head>', mobile_css + '\n</head>')
    else:
        # If no head tag, insert at the beginning
        html = mobile_css + html
    
    return templates.TemplateResponse("static_map.html", {"request": request, "map_html": html})


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
    term: str = Query(..., min_length=1, description="Location name or postcode"),
    radius_km: float = Query(10.0, gt=0, le=100, description="Search radius in kilometers"),
    db: Session = Depends(get_db),
):
    """
    Search by location name / postcode using online geocoding (OpenStreetMap).
    Returns all nearby data: customers, service outlets, BP outlets, and traffic police stations.
    """
    # Get coordinates from internet geocoding service (NOT from your database)
    center = geocode_location(term)
    if center is None:
        raise HTTPException(
            status_code=404, 
            detail=f"Location '{term}' not found. Please try a different location name or postcode."
        )

    center_lat, center_lon = center

    # Now filter your database results by radius around the geocoded location
    customers_df = ensure_latlon(_query_to_df(db.query(CustomerCell)))
    service_df = ensure_latlon(_query_to_df(db.query(ToyotaServiceOutlet)))
    bp_df = ensure_latlon(_query_to_df(db.query(ToyotaBPOutlet)))
    traffic_df = ensure_latlon(_query_to_df(db.query(TrafficPoliceStation)))

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

    return {
        "center": {"lat": center_lat, "lon": center_lon},
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



