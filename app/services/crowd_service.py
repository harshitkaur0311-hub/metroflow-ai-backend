
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.enums.crowd_level import CrowdLevel
from app.models.crowd_log import CrowdLog
from app.models.station import Station
from app.schemas.crowd_log import CrowdLogCreate
from app.utils.geo import cities_for_state

def log_crowd_count(db: Session, payload: CrowdLogCreate) -> CrowdLog:
    station = db.get(Station, payload.station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    ratio = payload.current_count / station.capacity if station.capacity else 0
    level = payload.crowd_level or CrowdLevel.from_ratio(ratio)

    log = CrowdLog(
        station_id=payload.station_id,
        current_count=payload.current_count,
        crowd_level=level,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

def get_latest_crowd(db: Session, station_id: int) -> CrowdLog | None:
    return (
        db.query(CrowdLog)
        .filter(CrowdLog.station_id == station_id)
        .order_by(CrowdLog.created_at.desc())
        .first()
    )

def get_station_wise_snapshot(db: Session, state: str | None = None) -> list[dict]:
    query = db.query(Station).filter(Station.is_active.is_(True))
    cities = cities_for_state(state)
    if cities:
        query = query.filter(Station.city.in_(cities))
    stations = query.all()
    snapshot = []
    for station in stations:
        latest = get_latest_crowd(db, station.id)
        snapshot.append({
            "station_id": station.id,
            "station_name": station.station_name,
            "capacity": station.capacity,
            "current_count": latest.current_count if latest else 0,
            "crowd_level": latest.crowd_level if latest else CrowdLevel.LOW,
            "occupancy_ratio": round((latest.current_count / station.capacity), 3)
            if latest and station.capacity else 0,
            "last_updated": latest.created_at if latest else None,
        })
    return snapshot

def get_heatmap(db: Session, state: str | None = None, limit: int | None = None) -> list[dict]:
    snapshot = get_station_wise_snapshot(db, state)
    stations_by_id = {s.id: s for s in db.query(Station).all()}
    heatmap = []
    for entry in snapshot:
        station = stations_by_id.get(entry["station_id"])
        if not station:
            continue
        if station.latitude is None or station.longitude is None:
            continue
        if station.latitude == 0 and station.longitude == 0:
            continue
        heatmap.append({
            **entry,
            "latitude": station.latitude,
            "longitude": station.longitude,
        })
    if limit is not None:
        heatmap.sort(key=lambda h: h.get("occupancy_ratio") or 0, reverse=True)
        heatmap = heatmap[:limit]
    return heatmap

def get_congested_stations(
    db: Session,
    min_level: CrowdLevel = CrowdLevel.HIGH,
    state: str | None = None,
) -> list[dict]:
    order = [CrowdLevel.LOW, CrowdLevel.MODERATE, CrowdLevel.HIGH, CrowdLevel.CRITICAL]
    threshold_index = order.index(min_level)
    snapshot = get_station_wise_snapshot(db, state)
    return [
        s for s in snapshot
        if order.index(s["crowd_level"]) >= threshold_index
    ]

def get_inflow_outflow(db: Session, station_id: int, hours: int = 24) -> dict:
    since = datetime.utcnow() - timedelta(hours=hours)
    logs = (
        db.query(CrowdLog)
        .filter(CrowdLog.station_id == station_id, CrowdLog.created_at >= since)
        .order_by(CrowdLog.created_at.asc())
        .all()
    )

    inflow = 0
    outflow = 0
    previous_count = None
    for log in logs:
        if previous_count is not None:
            delta = log.current_count - previous_count
            if delta > 0:
                inflow += delta
            else:
                outflow += abs(delta)
        previous_count = log.current_count

    return {
        "station_id": station_id,
        "window_hours": hours,
        "inflow": inflow,
        "outflow": outflow,
        "samples": len(logs),
    }

def get_station_analytics(db: Session, station_id: int) -> dict:
    since = datetime.utcnow() - timedelta(hours=24)
    stats = (
        db.query(
            func.avg(CrowdLog.current_count),
            func.max(CrowdLog.current_count),
            func.min(CrowdLog.current_count),
            func.count(CrowdLog.id),
        )
        .filter(CrowdLog.station_id == station_id, CrowdLog.created_at >= since)
        .first()
    )
    avg_count, max_count, min_count, sample_count = stats

    return {
        "station_id": station_id,
        "average_count_24h": round(avg_count, 1) if avg_count else 0,
        "peak_count_24h": max_count or 0,
        "min_count_24h": min_count or 0,
        "samples": sample_count or 0,
    }
