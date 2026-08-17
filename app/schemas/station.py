from pydantic import BaseModel
from pydantic import ConfigDict


class StationCreate(BaseModel):
    station_code: str
    station_name: str
    city: str
    latitude: float
    longitude: float
    is_interchange: bool = False
    capacity: int = 5000


class StationUpdate(BaseModel):
    station_name: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    is_interchange: bool | None = None
    is_active: bool | None = None
    capacity: int | None = None


class StationResponse(BaseModel):
    id: int
    station_code: str
    station_name: str
    city: str
    latitude: float
    longitude: float
    is_interchange: bool
    is_active: bool
    capacity: int
    # Real line name/color/physical-sequence, resolved from the
    # metro_lines/line_stations join in station_service.list_stations -
    # not columns on Station itself. None if a station has no line
    # assigned yet.
    line_name: str | None = None
    line_color: str | None = None
    station_order: int | None = None
    model_config = ConfigDict(
        from_attributes=True
    )