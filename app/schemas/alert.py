from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict

from app.enums.alert_type import AlertType


class AlertCreate(BaseModel):
    station_id: int
    alert_type: AlertType
    message: str
    # When True (default), an email is dispatched in the background to
    # every active user with an email on file - plus an explicit copy
    # to whoever raised the alert.
    notify_email: bool = True
    # When True (default), an SMS is dispatched the same way, to every
    # active user who has a phone number on file (i.e. signed up with
    # one, or logged in via phone/OTP). Independent of notify_email -
    # a user with only an email gets only the email, a user with only
    # a phone gets only the SMS, a user with both gets both.
    notify_sms: bool = True
    # Optional "expected back by" time for delay/maintenance alerts,
    # e.g. "service resumes by 9:00 PM". Shown on the alert card and
    # included in the email/SMS body. Both notify flags are persisted
    # on the Alert row so resolve_alert() can re-notify the same
    # audience on the same channels later without the caller having to
    # repeat them.
    available_until: datetime | None = None


class AlertResolve(BaseModel):
    # Whether resolving this alert should re-notify users that the
    # issue is over. Defaults to True. When True, the SAME channels
    # (email/SMS) used when the alert was originally raised are used
    # again - there's no separate notify_email/notify_sms toggle here
    # on purpose, so a "delay" alert someone only texted about doesn't
    # suddenly start emailing everyone on resolution.
    notify_on_resolve: bool = True


class AlertResponse(BaseModel):
    id: int
    station_id: int
    alert_type: AlertType
    message: str
    is_resolved: bool
    resolved_at: datetime | None
    available_until: datetime | None
    notify_email: bool
    notify_sms: bool
    created_at: datetime
    model_config = ConfigDict(
        from_attributes=True
    )
