from datetime import time

from sqlalchemy import Boolean
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Time

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.enums.day_type import DayType
from app.enums.schedule_status import ScheduleStatus
from app.mixins.timestamp import TimestampMixin


class TrainSchedule(TimestampMixin, Base):

    __tablename__ = "train_schedules"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    train_id: Mapped[int] = mapped_column(
        ForeignKey("trains.id")
    )

    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id")
    )

    arrival_time: Mapped[time]
    departure_time: Mapped[time]
    platform_number: Mapped[int]

    # --- Milestone 2: Scheduling Management Module ---

    day_type: Mapped[DayType] = mapped_column(
        Enum(DayType),
        default=DayType.WEEKDAY
    )

    is_peak_hour: Mapped[bool] = mapped_column(
        Boolean,
        default=False
    )

    # Planned headway (minutes between consecutive trains on this
    # station/line during this slot). Used by the frequency
    # optimization / adjustment workflow.
    frequency_minutes: Mapped[int] = mapped_column(
        Integer,
        default=10
    )

    status: Mapped[ScheduleStatus] = mapped_column(
        Enum(ScheduleStatus),
        default=ScheduleStatus.ON_TIME
    )

    # Delay handling: minutes of delay applied to this schedule entry.
    delay_minutes: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    # Actual (observed) arrival/departure once reported. Nullable until
    # real-time monitoring updates it.
    actual_arrival_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True
    )

    actual_departure_time: Mapped[time | None] = mapped_column(
        Time,
        nullable=True
    )

    train = relationship(
        "Train",
        back_populates="schedules"
    )

    station = relationship(
        "Station"
    )
