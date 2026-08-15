from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.station import Station
from app.models.train import Train
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
