import math
import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.enums.journey_status import JourneyStatus
from app.models.crowd_log import CrowdLog
from app.models.journey import Journey
from app.models.station import Station
from app.services.crowd_service import get_latest_crowd, log_crowd_count
from app.schemas.crowd_log import CrowdLogCreate

BASE_FARE = 10.0
PER_KM_RATE = 2.0


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bump_station_crowd(db: Session, station_id: int, delta: int) -> None:
    station = db.get(Station, station_id)
    if not station:
        return
    latest = get_latest_crowd(db, station_id)
    new_count = max(0, (latest.current_count if latest else 0) + delta)
    log_crowd_count(db, CrowdLogCreate(station_id=station_id, current_count=new_count))


def check_in(db: Session, user_id: str, source_station_id: int, destination_station_id: int) -> Journey:
    source = db.get(Station, source_station_id)
    destination = db.get(Station, destination_station_id)
    if not source or not destination:
        raise HTTPException(status_code=404, detail="Source or destination station not found")
    if source_station_id == destination_station_id:
        raise HTTPException(status_code=400, detail="Source and destination must differ")

    journey = Journey(
        user_id=uuid.UUID(str(user_id)),
        source_station_id=source_station_id,
        destination_station_id=destination_station_id,
        checkin_time=datetime.utcnow(),
        status=JourneyStatus.ACTIVE,
    )
    db.add(journey)
    db.commit()
    db.refresh(journey)

    # Passenger enters the system at the source station.
    _bump_station_crowd(db, source_station_id, +1)
    return journey


def check_out(db: Session, user_id: str, journey_id: int) -> Journey:
    journey = db.get(Journey, journey_id)
    if not journey or str(journey.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="Active journey not found")
    if journey.status != JourneyStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Journey is not active")

    source = db.get(Station, journey.source_station_id)
    destination = db.get(Station, journey.destination_station_id)

    distance_km = haversine_km(
        source.latitude, source.longitude,
        destination.latitude, destination.longitude,
    )
    fare = round(BASE_FARE + distance_km * PER_KM_RATE, 2)

    journey.checkout_time = datetime.utcnow()
    journey.fare = fare
    journey.status = JourneyStatus.COMPLETED
    db.commit()
    db.refresh(journey)

    # FIX: checkout means the passenger has exited the system entirely
    # (walked out through the gate) - they should NOT be re-added to
    # the destination station's live crowd count. The previous version
    # did `-1` at source and `+1` at destination on every checkout,
    # which net out to zero system-wide, so the total passenger count
    # only ever went up (on check-in) and never actually came back
    # down on checkout. Now checkout is a clean -1 at the source only.
    _bump_station_crowd(db, journey.source_station_id, -1)
    return journey


def active_journey_for_user(db: Session, user_id: str) -> Journey | None:
    return (
        db.query(Journey)
        .filter(Journey.user_id == user_id, Journey.status == JourneyStatus.ACTIVE)
        .order_by(Journey.checkin_time.desc())
        .first()
    )
