import asyncio

from app.simulator.live_simulator import run_forever as run_crowd_forever
from app.simulator.train_simulator import run_forever as run_train_forever

_crowd_task: asyncio.Task | None = None
_train_task: asyncio.Task | None = None

def start_simulator(session_factory, interval_seconds: int = 30) -> None:
    global _crowd_task
    if _crowd_task is None or _crowd_task.done():
        _crowd_task = asyncio.create_task(run_crowd_forever(session_factory, interval_seconds))

def stop_simulator() -> None:
    global _crowd_task
    if _crowd_task is not None:
        _crowd_task.cancel()
        _crowd_task = None

def start_train_tracker(session_factory, interval_seconds: int = 3) -> None:
    global _train_task
    if _train_task is None or _train_task.done():
        _train_task = asyncio.create_task(run_train_forever(session_factory, interval_seconds))

def stop_train_tracker() -> None:
    global _train_task
    if _train_task is not None:
        _train_task.cancel()
        _train_task = None

def is_simulator_running() -> bool:
    return _crowd_task is not None and not _crowd_task.done()

def is_train_tracker_running() -> bool:
    return _train_task is not None and not _train_task.done()
