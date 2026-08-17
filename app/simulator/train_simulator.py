"""Live train position tracking - no real GPS/CCTV feed exists (see
the platform spec), so this simulates motion instead. Unlike the old
LiveTrainMap behaviour ("illustrative", frozen on the next scheduled
station), every active train here actually keeps moving along its
real scheduled station route, back and forth, and its position is
persisted + pushed over the `train_position` websocket event every
tick - the same pattern Ola/Uber use for a car icon crawling along a
road, just simulated instead of real GPS.

A delayed train (per its current TrainSchedule.delay_minutes) moves
proportionally slower, so the map visibly shows *why* it's late.
"""
import asyncio
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.station import Station
from app.models.train import Train
from app.models.train_location import TrainLocation
from app.models.train_schedule import TrainSchedule
from app.websocket.events import TRAIN_POSITION
from app.websocket.manager import manager

# In-memory per-train animation state: {train_id: {"index": int, "direction": 1|-1}}
# progress_ratio itself is persisted on the TrainLocation row so a
# restart doesn't jump trains back to the start.
_train_state: dict[int, dict] = {}


def _routes_and_delays_for(db: Session, train_ids: list[int]) -> tuple[dict[int, list[int]], dict[int, int]]:
    """Batch version of what used to be two separate per-train queries
    (_ordered_station_route + _current_delay_minutes) run inside the
    per-train loop in track_tick - that was an N+1 query pattern: for
    10 active trains it meant 20+ round-trips to the DB every single
    tick. This fetches every schedule row for every active train in
    ONE query, then builds both the route list and the worst-delay
    lookup in plain Python, so track_tick makes a fixed, small number
    of queries no matter how many trains are active."""
    if not train_ids:
        return {}, {}

    schedules = (
        db.query(TrainSchedule)
        .filter(TrainSchedule.train_id.in_(train_ids))
        .order_by(TrainSchedule.train_id, TrainSchedule.arrival_time)
        .all()
    )

    routes: dict[int, list[int]] = {tid: [] for tid in train_ids}
    worst_delay: dict[int, int] = {tid: 0 for tid in train_ids}

    for s in schedules:
        route = routes[s.train_id]
        if not route or route[-1] != s.station_id:
            route.append(s.station_id)
        if s.delay_minutes and s.delay_minutes > worst_delay[s.train_id]:
            worst_delay[s.train_id] = s.delay_minutes

    return routes, worst_delay


def _locations_for(db: Session, train_ids: list[int], first_station: dict[int, int]) -> dict[int, TrainLocation]:
    """Batch version of the old per-train _get_or_create_location -
    one query to load every existing TrainLocation row for the active
    trains, then create any missing ones."""
    if not train_ids:
        return {}

    existing = (
        db.query(TrainLocation)
        .filter(TrainLocation.train_id.in_(train_ids))
        .all()
    )
    by_train = {loc.train_id: loc for loc in existing}

    for tid in train_ids:
        if tid not in by_train and tid in first_station:
            loc = TrainLocation(
                train_id=tid,
                station_id=first_station[tid],
                next_station_id=first_station[tid],
                progress_ratio=0.0,
                status="at_station",
            )
            db.add(loc)
            by_train[tid] = loc

    db.flush()
    return by_train


def _track_tick_sync(db: Session) -> list[dict]:
    """All the actual DB/CPU work for one tick, as a plain sync
    function - see the matching note in live_simulator._simulate_tick_sync
    for why this needs to run off the event loop via asyncio.to_thread()
    rather than directly inside an `async def`."""
    trains = db.query(Train).filter(Train.is_active.is_(True)).all()
    train_ids = [t.id for t in trains]
    updates: list[dict] = []

    tick_seconds = settings.TRAIN_TRACK_INTERVAL_SECONDS
    segment_seconds = max(1, settings.TRAIN_SEGMENT_SECONDS)

    routes, worst_delay = _routes_and_delays_for(db, train_ids)
    first_station = {tid: r[0] for tid, r in routes.items() if len(r) >= 2}
    locations = _locations_for(db, train_ids, first_station)

    # Batch-load every station these trains might reference, instead
    # of a db.get(Station, ...) per from/to station inside the loop.
    all_station_ids = {sid for route in routes.values() for sid in route}
    stations_by_id = {
        s.id: s
        for s in db.query(Station).filter(Station.id.in_(all_station_ids)).all()
    } if all_station_ids else {}

    for train in trains:
        route = routes.get(train.id, [])
        if len(route) < 2:
            continue

        state = _train_state.setdefault(train.id, {"index": 0, "direction": 1})
        loc = locations.get(train.id)
        if loc is None:
            continue

        # Keep the animation state's "index" in sync with route[] in
        # case the schedule changed since the last tick.
        if loc.station_id in route:
            state["index"] = route.index(loc.station_id)

        delay_minutes = worst_delay.get(train.id, 0)
        # Every 10 min of delay roughly halves the effective speed.
        speed_factor = 1.0 / (1.0 + delay_minutes / 10.0)
        step = (tick_seconds / segment_seconds) * speed_factor

        progress = (loc.progress_ratio or 0.0) + step
        index = state["index"]
        direction = state["direction"]

        if progress >= 1.0:
            progress = 0.0
            index += direction
            if index >= len(route) - 1:
                index = len(route) - 1
                direction = -1
            elif index <= 0:
                index = 0
                direction = 1
            state["index"] = index
            state["direction"] = direction

        from_station_id = route[index]
        to_index = max(0, min(len(route) - 1, index + direction))
        to_station_id = route[to_index]

        loc.station_id = from_station_id
        loc.next_station_id = to_station_id
        loc.progress_ratio = progress
        loc.status = "at_station" if progress == 0.0 and from_station_id == to_station_id else "in_transit"

        from_station = stations_by_id.get(from_station_id)
        to_station = stations_by_id.get(to_station_id)

        updates.append({
            "train_id": train.id,
            "train_number": train.train_number,
            "from_station_id": from_station_id,
            "from_station_name": from_station.station_name if from_station else None,
            "to_station_id": to_station_id,
            "to_station_name": to_station.station_name if to_station else None,
            "progress_ratio": round(progress, 4),
            "delay_minutes": delay_minutes,
            "status": "Delayed" if delay_minutes > 0 else "Running",
        })

    if updates:
        db.commit()

    return updates


async def track_tick(db: Session) -> list[dict]:
    """Runs the sync tick body on a worker thread, then broadcasts the
    result over the WebSocket from the event loop itself."""
    updates = await asyncio.to_thread(_track_tick_sync, db)
    if updates:
        await manager.broadcast(
            TRAIN_POSITION,
            {"updates": updates, "timestamp": datetime.utcnow().isoformat()},
        )
    return updates


async def run_forever(session_factory, interval_seconds: int = 3) -> None:
    """Background loop: call once at startup with
    `asyncio.create_task(run_forever(SessionLocal))`."""
    while True:
        db = session_factory()
        try:
            await track_tick(db)
        except Exception as exc:  # noqa: BLE001 - never let one bad tick kill the loop
            print(f"[train_simulator] tick failed, will retry next interval: {exc}")
        finally:
            db.close()
        await asyncio.sleep(interval_seconds)
