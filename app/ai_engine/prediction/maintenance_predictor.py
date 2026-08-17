"""New (real-data) module - Predictive Maintenance.

Not part of the original 3-model spec, added because a real
predictive_maintenance.csv dataset (per-train sensor readings) was
provided. Predicts a train's remaining useful life (hours) from its
current sensor readings, using the same "load a trained .pkl, fall
back to a heuristic if it isn't there yet" pattern as
crowd_predictor.py / delay_predictor.py / frequency_predictor.py, so
the API keeps working even before maintenance_model.pkl exists.
"""
import os
from functools import lru_cache

import joblib
import pandas as pd

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "saved_models", "maintenance_model.pkl")

FEATURES = [
    "compressor_pressure_bar",
    "motor_current_amp",
    "oil_temperature_c",
    "vibration_amplitude_mm",
    "air_leakage_flow",
    "operating_hours",
]

# Thresholds for turning a predicted-hours number into a human status,
# roughly matched to the maintenance_status distribution seen in the
# real dataset (most trains are Healthy; Warning/Critical are rare).
CRITICAL_BELOW_HRS = 200
WARNING_BELOW_HRS = 600


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


def _heuristic(readings: dict) -> float:
    """Rough fallback before maintenance_model.pkl has been trained:
    penalize high pressure/temperature/vibration relative to typical
    healthy operating ranges."""
    pressure_penalty = max(0, readings["compressor_pressure_bar"] - 9.0) * 150
    temp_penalty = max(0, readings["oil_temperature_c"] - 55) * 20
    vibration_penalty = max(0, readings["vibration_amplitude_mm"] - 0.6) * 800
    hours_penalty = readings["operating_hours"] * 0.3
    remaining = 3500 - pressure_penalty - temp_penalty - vibration_penalty - hours_penalty
    return max(0.0, remaining)


def predict_remaining_life(readings: dict) -> dict:
    """`readings` must have all keys in FEATURES (see
    MaintenanceReadingRequest in app/schemas/prediction.py)."""
    bundle = _load_model()

    if bundle is not None:
        model = bundle["model"]
        features = pd.DataFrame(
            [[readings[f] for f in bundle["features"]]],
            columns=bundle["features"],
        )
        predicted_hours = float(model.predict(features)[0])
        model_version = "random_forest_v1"
    else:
        predicted_hours = _heuristic(readings)
        model_version = "heuristic_fallback"

    predicted_hours = max(0.0, predicted_hours)

    if predicted_hours < CRITICAL_BELOW_HRS:
        status = "critical"
    elif predicted_hours < WARNING_BELOW_HRS:
        status = "warning"
    else:
        status = "healthy"

    return {
        "predicted_remaining_useful_life_hrs": round(predicted_hours, 1),
        "health_status": status,
        "model_version": model_version,
    }
