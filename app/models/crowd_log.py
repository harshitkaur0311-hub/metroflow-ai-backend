from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Integer

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.enums.crowd_level import CrowdLevel
from app.mixins.timestamp import TimestampMixin


class CrowdLog(TimestampMixin, Base):

    __tablename__ = "crowd_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id")
    )

    current_count: Mapped[int] = mapped_column(
        Integer
    )

    # Derived (current_count / station.capacity) bucket. Stored so
    # historical congestion trends and heatmaps don't need to be
    # recomputed against the station's capacity-at-the-time.
    crowd_level: Mapped[CrowdLevel] = mapped_column(
        Enum(CrowdLevel),
        default=CrowdLevel.LOW
    )

    station = relationship("Station")
