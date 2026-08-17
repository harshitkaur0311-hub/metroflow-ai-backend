
import json
import urllib.request
import uuid
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.enums.user_role import UserRole
from app.models.user_profile import UserProfile

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/me", auto_error=False)


@lru_cache(maxsize=1)
def _fetch_jwks() -> dict:
    with urllib.request.urlopen(settings.supabase_jwks_url, timeout=5) as resp:
        return json.loads(resp.read())


def _decode_supabase_token(token: str) -> dict:
    try:
        if settings.SUPABASE_JWT_SECRET:
            # Legacy HS256 project.
            return jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
        jwks = _fetch_jwks()
        return jwt.decode(
            token,
            jwks,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Supabase session token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not verify session (auth service unreachable). Please try again.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _get_or_create_profile_by_email(db: Session, email: str) -> UserProfile:
    """TEMPORARY dev bypass (settings.AUTH_DISABLED=True): no Supabase
    token to read a `sub` UUID from, so derive a stable UUID from the
    email itself - the same email always maps to the same profile row."""
    email = email.strip().lower()
    user_id = uuid.uuid5(uuid.NAMESPACE_DNS, email)

    user = db.get(UserProfile, user_id)
    if user:
        return user

    user = UserProfile(
        id=user_id,
        email=email,
        full_name=email.split("@")[0],
        role=UserRole.PASSENGER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _get_or_create_profile(db: Session, payload: dict) -> UserProfile:
    """First request after a Supabase sign-up: create the matching
    user_profiles row. Every request after that just reads it."""
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject claim")

    try:
        user_id = uuid.UUID(str(user_id))
    except ValueError:
        raise HTTPException(status_code=401, detail="Token subject is not a valid UUID")

    user = db.get(UserProfile, user_id)
    if user:
        return user

    metadata = payload.get("user_metadata") or {}

    
    raw_email = payload.get("email")
    email = raw_email.strip().lower() if raw_email else None

    phone = payload.get("phone") or metadata.get("phone")

    full_name = (
        metadata.get("full_name")
        or metadata.get("name")
        or (email or "").split("@")[0]
        or phone
        or "MetroFlow User"
    )

    user = UserProfile(
        id=user_id,
        email=email,
        full_name=full_name,
        username=metadata.get("username") or None,
        phone=phone,
        avatar_url=metadata.get("avatar_url") or metadata.get("picture"),
        role=UserRole.PASSENGER,  # default; promote via set_user_role.py or an admin
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserProfile:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if settings.AUTH_DISABLED:
        # TEMPORARY: no real Supabase session / OTP verification - the
        # frontend sends the email the user typed on the login form as
        # the bearer token as-is (see src/lib/axios.ts on the frontend).
        user = _get_or_create_profile_by_email(db, token)
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is disabled")
        return user

    payload = _decode_supabase_token(token)
    user = _get_or_create_profile(db, payload)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    return user


def require_roles(*roles: UserRole):
    """Dependency factory for role-based access control.

    Usage: Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))
    """

    def _dependency(current_user: UserProfile = Depends(get_current_user)) -> UserProfile:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return _dependency
