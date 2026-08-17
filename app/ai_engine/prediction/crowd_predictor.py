"""Milestone 2 - AI Prediction Module: crowd prediction inference.

Loads the trained RandomForest model if present; otherwise falls back
to a deterministic heuristic curve so the API keeps working even
before `train_crowd_model.py` has been run (e.g. fresh deploy).
"""
import os
from datetime import datetime
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "saved_models", "crowd_model.pkl")


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


def _heuristic(hour: int, is_weekend: int) -> float:
    morning_peak = np.exp(-((hour - 9) ** 2) / 4) * 900
    evening_peak = np.exp(-((hour - 18.5) ** 2) / 5) * 950
    base = 150 + morning_peak + evening_peak
    if is_weekend:
        base *= 0.55
    return float(base)


def predict_crowd(
    station_id: int,
    target_datetime: datetime | None = None,
    light: bool = False,
) -> dict:
    """light=True skips the per-tree confidence pass (walking every
    tree in the RandomForest separately) and only returns
    predicted_count. Used by the live simulator, which calls this once
    per station every tick just to *weight* random check-ins and never
    reads `confidence` at all - running the full forest-vote loop
    there was pure wasted CPU that added up across every station on
    every tick. The real /prediction/crowd API endpoint (where a user
    actually sees confidence) still calls this with light=False."""
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
        predicted_count = float(model.predict(features)[0])
        if light:
            confidence = None
        else:
            # Approximate confidence from the spread across the forest's
            # trees. (individual trees inside the forest are fit without
            # feature names, so use .values here, not the named DataFrame.)
            tree_preds = [t.predict(features.values)[0] for t in model.estimators_]
            confidence = float(max(0.0, 1 - (np.std(tree_preds) / (np.mean(tree_preds) + 1e-6))))
        model_version = "random_forest_v1"
    else:
        predicted_count = _heuristic(hour, is_weekend)
        confidence = None if light else 0.5
        model_version = "heuristic_fallback"

    return {
        "station_id": station_id,
        "target_datetime": dt,
        "predicted_count": round(predicted_count),
        "confidence": None if confidence is None else round(min(confidence, 0.99), 3),
        "model_version": model_version,
    }
