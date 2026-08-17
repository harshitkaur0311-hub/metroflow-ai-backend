from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.station import Station
from app.models.train import Train
from app.models.train_location import TrainLocation
from app.models.train_schedule import TrainSchedule
from app.schemas.train import TrainCreate, TrainUpdate
from app.utils.geo import cities_for_state


def list_trains(db: Session, state: str | None = None) -> list[Train]:
    cities = cities_for_state(state)
    if not cities:
        return db.query(Train).order_by(Train.train_number).all()

    return (
        db.query(Train)
        .join(TrainSchedule, TrainSchedule.train_id == Train.id)
        .join(Station, Station.id == TrainSchedule.station_id)
        .filter(Station.city.in_(cities))
        .distinct()
        .order_by(Train.train_number)
        .all()
    )


def get_train(db: Session, train_id: int) -> Train:
    train = db.get(Train, train_id)
    if not train:
        raise HTTPException(status_code=404, detail="Train not found")
    return train


def create_train(db: Session, payload: TrainCreate) -> Train:
    existing = db.query(Train).filter(Train.train_number == payload.train_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Train number already exists")

    train = Train(**payload.model_dump())
    db.add(train)
    db.commit()
    db.refresh(train)
    return train


def update_train(db: Session, train_id: int, payload: TrainUpdate) -> Train:
    train = get_train(db, train_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(train, field, value)
    db.commit()
    db.refresh(train)
    return train


def _current_delay_minutes(db: Session, train_id: int) -> int:
    worst = (
        db.query(TrainSchedule)
        .filter(TrainSchedule.train_id == train_id)
        .order_by(TrainSchedule.delay_minutes.desc())
        .first()
    )
    return worst.delay_minutes if worst else 0


def list_live_positions(db: Session, state: str | None = None) -> list[dict]:
    """Initial-load snapshot for the live train map - one entry per
    train currently being tracked (see app/simulator/train_simulator.py).
    The frontend fetches this once on mount, then the `train_position`
    websocket event keeps every entry updated without a refetch."""
    trains = list_trains(db, state)
    train_ids = {t.id for t in trains}

    locations = (
        db.query(TrainLocation)
        .filter(TrainLocation.train_id.in_(train_ids))
        .all()
        if train_ids else []
    )
    trains_by_id = {t.id: t for t in trains}

    results = []
    for loc in locations:
        train = trains_by_id.get(loc.train_id)
        if not train:
            continue
        from_station = db.get(Station, loc.station_id)
        to_station = db.get(Station, loc.next_station_id) if loc.next_station_id else from_station
        delay_minutes = _current_delay_minutes(db, train.id)
        results.append({
            "train_id": train.id,
            "train_number": train.train_number,
            "from_station_id": loc.station_id,
            "from_station_name": from_station.station_name if from_station else None,
            "to_station_id": loc.next_station_id or loc.station_id,
            "to_station_name": to_station.station_name if to_station else None,
            "progress_ratio": loc.progress_ratio or 0.0,
            "delay_minutes": delay_minutes,
            "status": "Delayed" if delay_minutes > 0 else "Running",
        })
    return results
