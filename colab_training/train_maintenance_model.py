"""Real-data integration - Predictive Maintenance model training.

Trains a RandomForestRegressor to predict a train's
remaining_useful_life_hrs from its current sensor readings, using the
REAL datasets/predictive_maintenance.csv file directly (no synthetic
data was ever used for this model).

Standalone script - meant to be run in Google Colab (see
train_metroflow_models_colab.ipynb in this same folder), or locally
with `python colab_training/train_maintenance_model.py` from the backend
repo root if you prefer. It has NO dependency on the `app` package - it
never runs as part of `uvicorn app.main:app`, so it never costs you CPU
just from running the backend.
"""
import os

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

FEATURES = [
    "compressor_pressure_bar",
    "motor_current_amp",
    "oil_temperature_c",
    "vibration_amplitude_mm",
    "air_leakage_flow",
    "operating_hours",
]
TARGET = "remaining_useful_life_hrs"

MODEL_DIR = os.path.join(os.path.dirname(__file__), "output")
MODEL_PATH = os.path.join(MODEL_DIR, "maintenance_model.pkl")
DATASET_PATH = os.path.join(os.path.dirname(__file__), "..", "datasets", "predictive_maintenance.csv")


def load_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATASET_PATH)
    # Defensive cleaning, mirrors what's already verified clean in
    # app/database/seed_real_data.py's sibling checks: no nulls/negatives
    # expected, but guard anyway in case of a re-export.
    df = df.dropna(subset=FEATURES + [TARGET])
    for col in FEATURES + [TARGET]:
        df = df[df[col] >= 0]
    return df


def train() -> dict:
    df = load_dataset()
    X = df[FEATURES]
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = RandomForestRegressor(n_estimators=80, max_depth=10, random_state=42)
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES}, MODEL_PATH)

    return {"mae": mae, "model_path": MODEL_PATH, "samples": len(df)}


if __name__ == "__main__":
    metrics = train()
    print(f"Maintenance model trained. MAE={metrics['mae']:.2f} hrs, saved to {metrics['model_path']} ({metrics['samples']} samples)")
