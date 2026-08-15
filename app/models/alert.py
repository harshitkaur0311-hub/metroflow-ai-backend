from datetime import datetime

from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import String

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.enums.alert_type import AlertType
from app.mixins.timestamp import TimestampMixin


class Alert(TimestampMixin, Base):

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)

    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id")
    )

    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType)
    )

    message: Mapped[str] = mapped_column(
        String(500)
    )

    # Who raised it (admin/operator) - Milestone 1 "role-based access
    # control" tie-in. Nullable so system-generated alerts (future
    # automated overcrowding/delay triggers) don't need a user. Typed
    # to match user_profiles.id (postgresql UUID) exactly.
    created_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id"),
        nullable=True,
    )

    is_resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Admin-set "expected back by" time for delay/maintenance alerts,
    # e.g. "service resumes by 9:00 PM". Purely informational - shown
    # in the alert card and included in the email/SMS body. Nullable
    # because most alerts (overcrowding, emergency, info) don't have a
    # known resolution time.
    available_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Which channels were actually requested at creation time - stored
    # (not just accepted as a create-time flag) so that resolve_alert
    # can re-notify the same audience on the same channels without the
    # caller having to remember/re-specify them.
    notify_email: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    notify_sms: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    station = relationship("Station")
    creator = relationship("UserProfile")