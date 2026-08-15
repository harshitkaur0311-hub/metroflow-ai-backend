from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai_engine.prediction.crowd_predictor import predict_crowd
from app.ai_engine.prediction.delay_predictor import predict_delay
from app.ai_engine.prediction.frequency_predictor import recommend_frequency
from app.enums.crowd_level import CrowdLevel
from app.enums.prediction_type import PredictionType
from app.models.prediction import Prediction
from app.models.station import Station


def _save_prediction(
    db: Session,
    station_id: int,
    prediction_type: PredictionType,
    predicted_value: float,
    confidence: float,
    target_datetime: datetime,
    model_version: str,
) -> Prediction:
    record = Prediction(
        station_id=station_id,
        prediction_type=prediction_type,
        predicted_value=predicted_value,
        predicted_count=round(predicted_value) if prediction_type in (
            PredictionType.CROWD, PredictionType.DEMAND
        ) else None,
        confidence=confidence,
        target_datetime=target_datetime,
        model_version=model_version,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _require_station(db: Session, station_id: int) -> Station:
    station = db.get(Station, station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    return station


def forecast_crowd(db: Session, station_id: int, target_datetime: datetime | None = None) -> Prediction:
    """Crowd prediction models."""
    _require_station(db, station_id)
    result = predict_crowd(station_id, target_datetime)
    return _save_prediction(
        db,
        station_id=station_id,
        prediction_type=PredictionType.CROWD,
        predicted_value=result["predicted_count"],
        confidence=result["confidence"],
        target_datetime=result["target_datetime"],
        model_version=result["model_version"],
    )


def forecast_demand(db: Session, station_id: int, hours_ahead: int = 6) -> list[Prediction]:
    """Passenger demand forecasting: hour-by-hour for the next N hours."""
    _require_station(db, station_id)
    now = datetime.utcnow()
    predictions = []
    for i in range(1, hours_ahead + 1):
        target = now + timedelta(hours=i)
        result = predict_crowd(station_id, target)
        record = _save_prediction(
            db,
            station_id=station_id,
            prediction_type=PredictionType.DEMAND,
            predicted_value=result["predicted_count"],
            confidence=result["confidence"],
            target_datetime=result["target_datetime"],
            model_version=result["model_version"],
        )
        predictions.append(record)
    return predictions


def forecast_delay(db: Session, train_id: int, station_id: int) -> Prediction:
    """Delay impact prediction, feeding the Scheduling Management Module."""
    _require_station(db, station_id)
    result = predict_delay(station_id)
    return _save_prediction(
        db,
        station_id=station_id,
        prediction_type=PredictionType.DELAY,
        predicted_value=result["predicted_delay_minutes"],
        confidence=0.7,
        target_datetime=result["target_datetime"],
        model_version=result["model_version"],
    )


def recommend_train_frequency(db: Session, station_id: int, is_peak_hour: bool = False) -> Prediction:
    """Train frequency recommendations / resource utilization optimization."""
    _require_station(db, station_id)
    target = datetime.utcnow()
    if is_peak_hour:
        target = target.replace(hour=9)  # nudge into a known peak window
    result = recommend_frequency(station_id, target)
    return _save_prediction(
        db,
        station_id=station_id,
        prediction_type=PredictionType.FREQUENCY,
        predicted_value=result["recommended_frequency_minutes"],
        confidence=0.75,
        target_datetime=result["target_datetime"],
        model_version=result["model_version"],
    )


def traffic_pattern_analysis(db: Session, station_id: int) -> dict:
    """Traffic pattern analysis: 24h predicted demand curve for a station."""
    _require_station(db, station_id)
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    curve = []
    for hour in range(24):
        target = now.replace(hour=hour)
        result = predict_crowd(station_id, target)
        curve.append({
            "hour": hour,
            "predicted_count": result["predicted_count"],
            "is_peak_hour": 8 <= hour <= 11 or 17 <= hour <= 20,
        })

    peak = max(curve, key=lambda c: c["predicted_count"])
    trough = min(curve, key=lambda c: c["predicted_count"])

    return {
        "station_id": station_id,
        "hourly_forecast": curve,
        "peak_hour": peak["hour"],
        "peak_predicted_count": peak["predicted_count"],
        "quietest_hour": trough["hour"],
    }


def smart_recommendations(db: Session, station_id: int) -> list[dict]:
    """Smart recommendations combining crowd + delay + frequency predictions."""
    crowd = predict_crowd(station_id)
    delay = predict_delay(station_id)
    frequency = recommend_frequency(station_id)

    recommendations = []

    if crowd["predicted_count"] > 800:
        recommendations.append({
            "station_id": station_id,
            "title": "High crowd expected",
            "detail": f"Predicted ~{crowd['predicted_count']} passengers. "
                      f"Consider deploying additional staff and opening extra gates.",
            "severity": "warning",
        })

    if delay["predicted_delay_minutes"] > 3:
        recommendations.append({
            "station_id": station_id,
            "title": "Delay risk",
            "detail": f"Model predicts ~{delay['predicted_delay_minutes']} min of delay "
                      f"driven by current congestion levels.",
            "severity": "warning",
        })

    recommendations.append({
        "station_id": station_id,
        "title": "Frequency suggestion",
        "detail": f"Recommended train interval: {frequency['recommended_frequency_minutes']} min "
                  f"({'peak' if frequency['is_peak_hour'] else 'off-peak'} slot).",
        "severity": "info",
    })

    if not recommendations:
        recommendations.append({
            "station_id": station_id,
            "title": "Normal operations",
            "detail": "No anomalies detected; current schedule and staffing look adequate.",
            "severity": "info",
        })

    return recommendations


# --- New: Predictive Maintenance (real predictive_maintenance.csv dataset) ---
# Train-based, not station-based, so it doesn't use the Prediction table
# (which requires a station_id) - this stays a stateless inference call,
# same lightweight pattern as the other ai_engine predictors.

def predict_maintenance(train_id: int, readings: dict) -> dict:
    """Predictive maintenance: remaining useful life for a train from its
    current sensor readings."""
    from app.ai_engine.prediction.maintenance_predictor import predict_remaining_life

    result = predict_remaining_life(readings)
    return {
        "train_id": train_id,
        "predicted_remaining_useful_life_hrs": result["predicted_remaining_useful_life_hrs"],
        "health_status": result["health_status"],
        "model_version": result["model_version"],
    }
    