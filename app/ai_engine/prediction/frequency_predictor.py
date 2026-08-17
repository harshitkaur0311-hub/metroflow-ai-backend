"""Milestone 2 - AI Prediction Module: train frequency recommendation
inference. Supports the Scheduling Management Module's "frequency
adjustment" workflow with a data-driven suggestion.
"""
import os
from datetime import datetime
from functools import lru_cache

import joblib
import pandas as pd

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "saved_models", "frequency_model.pkl")

MIN_FREQUENCY = 3
MAX_FREQUENCY = 15


@lru_cache(maxsize=1)
def _load_model():
    if not os.path.exists(MODEL_PATH):
        print(f"[{__name__}] no trained model at {MODEL_PATH} - using heuristic fallback")
        return None
    try:
        return joblib.load(MODEL_PATH)
    except Exception as exc:
        # A version mismatch (scikit-learn/numpy) or a corrupted .pkl
        # should degrade to the heuristic, not crash every prediction
        # request - this is what actually made the API keep working
        # even before/without a valid trained model.
        print(f"[{__name__}] failed to load {MODEL_PATH}: {exc!r} - using heuristic fallback")
        return None


def recommend_frequency(station_id: int, target_datetime: datetime | None = None) -> dict:
    dt = target_datetime or datetime.utcnow()
    hour = dt.hour
    day_of_week = dt.weekday()
    is_weekend = 1 if day_of_week in (5, 6) else 0
    is_peak_hour = 1 if (8 <= hour <= 11 or 17 <= hour <= 20) else 0

    bundle = _load_model()

    if bundle is not None:
        model = bundle["model"]
        features = pd.DataFrame(
            [[station_id, hour, day_of_week, is_weekend, is_peak_hour]],
            columns=bundle["features"],
        )
        recommended = float(model.predict(features)[0])
        model_version = "random_forest_v1"
    else:
        # Heuristic: shorter headway during peak hours.
        recommended = MIN_FREQUENCY + 2 if is_peak_hour else MAX_FREQUENCY - 2
        model_version = "heuristic_fallback"

    recommended = max(MIN_FREQUENCY, min(MAX_FREQUENCY, recommended))

    return {
        "station_id": station_id,
        "target_datetime": dt,
        "is_peak_hour": bool(is_peak_hour),
        "recommended_frequency_minutes": round(recommended, 1),
        "model_version": model_version,
    }
