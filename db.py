from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import (
    Column,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./selangor_map.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class ToyotaServiceOutlet(Base):
    __tablename__ = "toyota_service_outlets"

    id = Column(Integer, primary_key=True, index=True)
    outlet_name = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    postcode = Column(String(20), nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)


class ToyotaBPOutlet(Base):
    __tablename__ = "toyota_bp_outlets"

    id = Column(Integer, primary_key=True, index=True)
    outlet_name = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    postcode = Column(String(20), nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)


class TrafficPoliceStation(Base):
    __tablename__ = "traffic_police_stations"

    id = Column(Integer, primary_key=True, index=True)
    station_name = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    postcode = Column(String(20), nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)


class CustomerCell(Base):
    """
    Optional table mirroring the aggregated customer CSV used for the heatmap.
    This is populated only via CSV upload; there is no per-row editing in the UI.
    """

    __tablename__ = "customer_cells"

    id = Column(Integer, primary_key=True, index=True)
    state = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    postcode = Column(String(20), nullable=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    weight = Column(Float, nullable=True)


def init_db() -> None:
    """
    Create all tables. Call this once at startup (for local/dev),
    or run migrations in a more advanced setup.
    """

    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """
    FastAPI-friendly dependency for getting a DB session.
    In plain scripts you can use SessionLocal() directly.
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



