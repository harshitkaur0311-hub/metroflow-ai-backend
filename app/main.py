import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.v1 import (
    admin,
    alerts,
    analytics,
    authentication,
    checkin,
    checkout,
    crowd,
    health,
    meta,
    prediction,
    schedule,
    station,
    trains,
    users,
)
from app.core.config import settings
from app.database.session import SessionLocal
from app.simulator.scheduler import (
    start_simulator,
    start_train_tracker,
    stop_simulator,
    stop_train_tracker,
)
from app.websocket.manager import manager

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

@asynccontextmanager
async def lifespan(app: FastAPI):
    manager.bind_loop(asyncio.get_running_loop())

    if settings.ENABLE_SIMULATOR:
        start_simulator(SessionLocal, settings.SIMULATOR_INTERVAL_SECONDS)
    if settings.ENABLE_TRAIN_TRACKING:
        start_train_tracker(SessionLocal, settings.TRAIN_TRACK_INTERVAL_SECONDS)
    yield
    if settings.ENABLE_SIMULATOR:
        stop_simulator()
    if settings.ENABLE_TRAIN_TRACKING:
        stop_train_tracker()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[] if settings.cors_origins_list == ["*"] else settings.cors_origins_list,
    allow_origin_regex=".*" if settings.cors_origins_list == ["*"] else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

app.include_router(health.router, prefix=API_PREFIX)
app.include_router(authentication.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(station.router, prefix=API_PREFIX)
app.include_router(trains.router, prefix=API_PREFIX)
app.include_router(crowd.router, prefix=API_PREFIX)
app.include_router(checkin.router, prefix=API_PREFIX)
app.include_router(checkout.router, prefix=API_PREFIX)
app.include_router(schedule.router, prefix=API_PREFIX)
app.include_router(prediction.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(alerts.router, prefix=API_PREFIX)
app.include_router(meta.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)

@app.get("/")
def home():
    return {
        "message": "MetroFlow Backend Running",
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }

@app.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
