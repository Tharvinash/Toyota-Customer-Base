from __future__ import annotations

from typing import List
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
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


app = FastAPI(title="Selangor Map Backend")

# Init DB on startup (simple dev/local approach)
init_db()

templates = Jinja2Templates(directory="templates")
static_dir = Path(__file__).parent / "static"
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
def map_view(db: Session = Depends(get_db)) -> HTMLResponse:
    customers_df = _query_to_df(db.query(CustomerCell))
    service_df = _query_to_df(db.query(ToyotaServiceOutlet))
    bp_df = _query_to_df(db.query(ToyotaBPOutlet))
    traffic_df = _query_to_df(db.query(TrafficPoliceStation))

    m = build_map(customers_df, service_df, bp_df, traffic_df)
    html = m.get_root().render()
    return HTMLResponse(content=html)


@app.get("/", response_class=HTMLResponse)
def admin_home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("admin_home.html", {"request": request})


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



