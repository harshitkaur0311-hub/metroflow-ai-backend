from datetime import datetime, time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.enums.day_type import DayType
from app.enums.schedule_status import ScheduleStatus
from app.models.station import Station
from app.models.train_schedule import TrainSchedule
from app.schemas.train_schedule import (
    DelayUpdate,
    FrequencyAdjustment,
    TrainScheduleCreate,
    TrainScheduleUpdate,
)
from app.utils.geo import cities_for_state


def _scope_to_state(query, state: str | None):
    """Joins in Station and filters to a state's cities, if requested."""
    cities = cities_for_state(state)
    if not cities:
        return query
    return query.join(Station, Station.id == TrainSchedule.station_id).filter(
        Station.city.in_(cities)
    )

# Default peak windows used for automatic peak-hour flagging.
PEAK_WINDOWS = [
    (time(8, 0), time(11, 0)),
    (time(17, 0), time(20, 0)),
]


def _is_peak(t: time) -> bool:
    return any(start <= t <= end for start, end in PEAK_WINDOWS)


def list_schedules(
    db: Session,
    station_id: int | None = None,
    train_id: int | None = None,
    day_type: DayType | None = None,
    state: str | None = None,
) -> list[TrainSchedule]:
    query = db.query(TrainSchedule)
    if station_id:
        query = query.filter(TrainSchedule.station_id == station_id)
    if train_id:
        query = query.filter(TrainSchedule.train_id == train_id)
    if day_type:
        query = query.filter(TrainSchedule.day_type == day_type)
    query = _scope_to_state(query, state)
    return query.order_by(TrainSchedule.arrival_time).all()


def get_schedule(db: Session, schedule_id: int) -> TrainSchedule:
    schedule = db.get(TrainSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


def create_schedule(db: Session, payload: TrainScheduleCreate) -> TrainSchedule:
    data = payload.model_dump()
    # Auto-detect peak hour unless caller explicitly set it.
    if not data.get("is_peak_hour"):
        data["is_peak_hour"] = _is_peak(data["arrival_time"])

    schedule = TrainSchedule(**data)
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def update_schedule(db: Session, schedule_id: int, payload: TrainScheduleUpdate) -> TrainSchedule:
    schedule = get_schedule(db, schedule_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    db.commit()
    db.refresh(schedule)
    return schedule


def handle_delay(db: Session, schedule_id: int, payload: DelayUpdate) -> TrainSchedule:
    """Delay handling workflow: records delay minutes and flips status."""
    schedule = get_schedule(db, schedule_id)
    schedule.delay_minutes = payload.delay_minutes
    schedule.status = ScheduleStatus.DELAYED if payload.delay_minutes > 0 else ScheduleStatus.ON_TIME

    if payload.delay_minutes > 0:
        base = datetime.combine(datetime.today(), schedule.arrival_time)
        delayed = base.replace(
            minute=(base.minute + payload.delay_minutes) % 60,
            hour=base.hour + (base.minute + payload.delay_minutes) // 60,
        )
        schedule.actual_arrival_time = delayed.time()

    db.commit()
    db.refresh(schedule)
    return schedule


def adjust_frequency(db: Session, schedule_id: int, payload: FrequencyAdjustment) -> TrainSchedule:
    """Frequency adjustment workflow (manual override of AI recommendation)."""
    schedule = get_schedule(db, schedule_id)
    schedule.frequency_minutes = payload.frequency_minutes
    if payload.is_peak_hour is not None:
        schedule.is_peak_hour = payload.is_peak_hour
    db.commit()
    db.refresh(schedule)
    return schedule


def peak_hour_schedules(
    db: Session,
    station_id: int | None = None,
    state: str | None = None,
) -> list[TrainSchedule]:
    """Peak-hour optimization view: schedules currently flagged as peak."""
    query = db.query(TrainSchedule).filter(TrainSchedule.is_peak_hour.is_(True))
    if station_id:
        query = query.filter(TrainSchedule.station_id == station_id)
    query = _scope_to_state(query, state)
    return query.order_by(TrainSchedule.arrival_time).all()


def delayed_schedules(
    db: Session,
    station_id: int | None = None,
    state: str | None = None,
) -> list[TrainSchedule]:
    query = db.query(TrainSchedule).filter(TrainSchedule.status == ScheduleStatus.DELAYED)
    if station_id:
        query = query.filter(TrainSchedule.station_id == station_id)
    query = _scope_to_state(query, state)
    return query.order_by(TrainSchedule.delay_minutes.desc()).all()
