from __future__ import annotations

import pandas as pd

from map_utils import ensure_latlon, load_csv, log
from db import (
    CustomerCell,
    ToyotaBPOutlet,
    ToyotaServiceOutlet,
    TrafficPoliceStation,
    SessionLocal,
    init_db,
)


def clean_postcode(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text or None


def migrate_service(db):
    df = ensure_latlon(load_csv("toyota_service_outlets.csv"), state_filter=None)
    if df.empty:
        log("No service outlets to migrate.")
        return
    log(f"Migrating {len(df)} service outlets...")
    db.query(ToyotaServiceOutlet).delete()
    for _, r in df.iterrows():
        o = ToyotaServiceOutlet(
            outlet_name=r.get("outlet name") or r.get("name") or "",
            address=r.get("address"),
            city=r.get("city"),
            state=r.get("state"),
            postcode=clean_postcode(r.get("postcode")),
            lat=float(r.get("lat")),
            lon=float(r.get("lon")),
            phone=r.get("phone"),
            email=r.get("email"),
        )
        db.add(o)


def migrate_bp(db):
    df = ensure_latlon(load_csv("toyota_bp_outlets.csv"), state_filter=None)
    if df.empty:
        log("No BP outlets to migrate.")
        return
    log(f"Migrating {len(df)} BP outlets...")
    db.query(ToyotaBPOutlet).delete()
    for _, r in df.iterrows():
        o = ToyotaBPOutlet(
            outlet_name=r.get("outlet name") or r.get("name") or "",
            address=r.get("address"),
            city=r.get("city"),
            state=r.get("state"),
            postcode=clean_postcode(r.get("postcode")),
            lat=float(r.get("lat")),
            lon=float(r.get("lon")),
            phone=r.get("phone"),
            email=r.get("email"),
        )
        db.add(o)


def migrate_traffic(db):
    df = ensure_latlon(load_csv("traffic_police_stations.csv"), state_filter=None)
    if df.empty:
        log("No traffic stations to migrate.")
        return
    log(f"Migrating {len(df)} traffic stations...")
    db.query(TrafficPoliceStation).delete()
    for _, r in df.iterrows():
        s = TrafficPoliceStation(
            station_name=r.get("station_name") or r.get("name") or "",
            address=r.get("address"),
            city=r.get("city"),
            state=r.get("state"),
            postcode=clean_postcode(r.get("postcode")),
            lat=float(r.get("lat")),
            lon=float(r.get("lon")),
            phone=r.get("phone"),
            email=r.get("email"),
        )
        db.add(s)


def migrate_customers(db):
    df = load_csv("customers.csv")
    if df.empty:
        log("No customers to migrate.")
        return
    df = ensure_latlon(df, state_filter=None)
    if "weight" not in df.columns:
        df["weight"] = 1.0
    log(f"Migrating {len(df)} customer cells...")
    db.query(CustomerCell).delete()
    for _, r in df.iterrows():
        c = CustomerCell(
            state=r.get("state"),
            city=r.get("city"),
            postcode=clean_postcode(r.get("postcode")),
            lat=float(r.get("lat")),
            lon=float(r.get("lon")),
            weight=float(r.get("weight")),
        )
        db.add(c)


def main():
    init_db()
    db = SessionLocal()
    try:
        migrate_service(db)
        migrate_bp(db)
        migrate_traffic(db)
        migrate_customers(db)
        db.commit()
        log("Migration complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()


