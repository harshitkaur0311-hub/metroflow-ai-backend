"""Mirrors Supabase's `auth.users` table 1:1 by id. Supabase owns the
actual credentials (email + password hash) in its own `auth` schema -
we never store a password here. This table only exists to attach
app-specific fields (role, phone, avatar) to a Supabase user id.

Rows are created lazily on first authenticated request - see
`app/core/security.py::_get_or_create_profile`.
"""
from sqlalchemy import Boolean
from sqlalchemy import Enum
from sqlalchemy import String

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.enums.user_role import UserRole
from app.mixins.timestamp import TimestampMixin


class UserProfile(TimestampMixin, Base):

    __tablename__ = "user_profiles"

    # Same UUID as the corresponding row in Supabase's auth.users table.
    # No local default - this is always set explicitly to that id.
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True
    )

    # Cached copy of the Supabase account email, kept in sync on each
    # login for convenience (e.g. admin listing users). Not used for
    # authentication - Supabase is the source of truth.
    email: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True
    )

    full_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False
    )

    # Optional, set at signup - purely a display handle (not used for
    # login; Supabase auth is always by email, phone, or Google). Not
    # enforced unique at the DB level on purpose: two people picking
    # the same handle shouldn't block either of their signups from
    # completing - this is a profile label, not a login credential.
    username: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    avatar_url: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole),
        default=UserRole.PASSENGER
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )

    journeys = relationship(
        "Journey",
        back_populates="user"
    )
