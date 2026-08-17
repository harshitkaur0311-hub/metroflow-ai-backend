from pydantic import BaseModel
from pydantic import ConfigDict
from app.enums.train_status import TrainStatus


class TrainLiveResponse(BaseModel):
    """Current live position of one train - the initial-load snapshot
    that /ws/monitor's `train_position` events then keep updated in
    place, without a page refresh."""
    train_id: int
    train_number: str
    from_station_id: int
    from_station_name: str | None = None
    to_station_id: int
    to_station_name: str | None = None
    progress_ratio: float
    delay_minutes: int
    status: str


class TrainCreate(BaseModel):
    train_number: str
    capacity: int


class TrainUpdate(BaseModel):
    capacity: int | None = None
    status: TrainStatus | None = None
    is_active: bool | None = None


class TrainResponse(BaseModel):
    id: int
    train_number: str
    capacity: int
    status: TrainStatus
    is_active: bool
    model_config = ConfigDict(
        from_attributes=True
    )