from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "MetroFlow AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # When True, SQLAlchemy prints every SQL query it runs to the
    # terminal. Keep this False for demos/screen-shares - turn it on
    # only when you're actually debugging a query.
    SQL_ECHO: bool = False

    DATABASE_URL: str

    # --- Supabase (Auth is fully delegated to Supabase now) ---
    SUPABASE_URL: str
    SUPABASE_KEY: str  # anon/publishable key (used by frontend, kept here for reference)

    # Project Settings -> API -> JWT Settings -> "JWT Secret" (legacy HS256 projects).
    # Leave empty if your Supabase project uses the newer asymmetric signing keys -
    # the backend will then verify tokens via the JWKS endpoint instead.
    SUPABASE_JWT_SECRET: str | None = None

    # Service role key (Project Settings -> API -> service_role). NEVER expose this
    # to the frontend. Only needed for admin scripts (e.g. set_user_role.py) that
    # must bypass Row Level Security. Optional - most endpoints don't need it.
    SUPABASE_SERVICE_ROLE_KEY: str | None = None

    # --- TEMPORARY dev bypass ---
    # When True, app/core/security.py skips real Supabase JWT/OTP
    # verification entirely and lets any email through (see
    # get_current_user). Keep False now that real Supabase auth works.
    AUTH_DISABLED: bool = False

    # --- CORS ---
    # Default changed from "*" to localhost only, since "*" combined
    # with allow_credentials=True is a real production risk (any site
    # can call the API using a logged-in user's cookies/token). Set
    # CORS_ORIGINS in your real .env to your actual frontend domain(s),
    # comma-separated - e.g. "https://metroflow.vercel.app".
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- AI Engine ---
    AI_MODELS_DIR: str = "app/ai_engine/saved_models"
    AI_DATASETS_DIR: str = "app/ai_engine/datasets"

    # --- Live Simulator (real-time operational monitoring demo) ---
    # Simulates real passengers checking in/out (POST /checkin, /checkout)
    # rather than just overwriting each station's count - see
    # app/simulator/live_simulator.py.
    # Default False: station occupancy stays static until an
    # admin/operator turns it on (see app/api/v1/admin.py) - matches
    # .env.example so behaviour is correct even if a real .env is
    # missing this line, instead of silently falling back to "on".
    ENABLE_SIMULATOR: bool = False
    SIMULATOR_INTERVAL_SECONDS: int = 3
    SIMULATOR_PASSENGER_POOL_SIZE: int = 40
    SIMULATOR_MAX_CHECKINS_PER_TICK: int = 6

    # --- Live Train Tracking (Ola/Uber-style moving position) ---
    # Moves every active train continuously back and forth along its
    # real scheduled station route and pushes a `train_position` event
    # over /ws/monitor every TRAIN_TRACK_INTERVAL_SECONDS - see
    # app/simulator/train_simulator.py. There's no real GPS feed, so
    # this is simulated motion, but unlike before it actually changes
    # every tick instead of being a static "next station" snapshot.
    ENABLE_TRAIN_TRACKING: bool = True
    # Must match NEXT_PUBLIC_TRAIN_TRACK_INTERVAL_SECONDS in the
    # frontend's .env.local - the glide animation there is timed to
    # exactly span the gap between two pushes from this interval. A
    # mismatch here (this used to default to 3 while the frontend
    # assumed 10) makes the train glide then freeze/jump instead of
    # moving continuously.
    TRAIN_TRACK_INTERVAL_SECONDS: int = 10
    # Simulated seconds to travel between two adjacent stations at
    # normal (non-delayed) speed.
    TRAIN_SEGMENT_SECONDS: int = 25

    # --- SMTP (Alert & Notification Module - email dispatch) ---
    # Works with Gmail (use an App Password, not your real password),
    # SendGrid SMTP relay, Mailgun, AWS SES SMTP, etc. Leave SMTP_HOST
    # blank in dev if you don't want to send real emails yet - alert
    # creation still works, dispatch just logs "SMTP not configured"
    # per recipient in notification_logs instead of raising an error.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str = "alerts@metroflow.app"
    SMTP_FROM_NAME: str = "MetroFlow Alerts"
    SMTP_USE_TLS: bool = True

    # --- Twilio (Alert & Notification Module - SMS dispatch, and the
    # SMS provider Supabase itself uses for phone/OTP login - see
    # Supabase Dashboard -> Authentication -> Providers -> Phone).
    # Same three values are used in both places: Supabase needs them
    # configured in ITS dashboard for OTP login to actually send an
    # SMS, and this backend needs them here in .env for alert SMS
    # dispatch. Leave blank in dev - alert SMS then logs "Twilio not
    # configured" per recipient instead of raising an error. ---
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_FROM_NUMBER: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.SUPABASE_URL}/auth/v1/.well-known/jwks.json"


settings = Settings()
