"""Milestone 2 - AI Prediction Module: delay prediction inference."""
import os
from datetime import datetime
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

from app.ai_engine.prediction.crowd_predictor import predict_crowd

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "saved_models", "delay_model.pkl")


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


def predict_delay(station_id: int, target_datetime: datetime | None = None) -> dict:
    dt = target_datetime or datetime.utcnow()
    hour = dt.hour
    day_of_week = dt.weekday()
    is_weekend = 1 if day_of_week in (5, 6) else 0
    is_peak_hour = 1 if (8 <= hour <= 11 or 17 <= hour <= 20) else 0

    crowd = predict_crowd(station_id, dt)
    passenger_count = crowd["predicted_count"]

    bundle = _load_model()

    if bundle is not None:
        model = bundle["model"]
        features = pd.DataFrame(
            [[station_id, hour, day_of_week, is_weekend, is_peak_hour, passenger_count]],
            columns=bundle["features"],
        )
        predicted_delay = float(model.predict(features)[0])
        model_version = "random_forest_v1"
    else:
        predicted_delay = max(0.0, (passenger_count / 1000) * 4)
        model_version = "heuristic_fallback"

    return {
        "station_id": station_id,
        "target_datetime": dt,
        "predicted_delay_minutes": round(max(0.0, predicted_delay), 1),
        "based_on_predicted_crowd": passenger_count,
        "model_version": model_version,
    }
