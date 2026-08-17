"""Milestone 2 - AI Prediction Module API.

Crowd prediction models, passenger demand forecasting, traffic
pattern analysis, smart recommendations. Every route requires a
logged-in user and is rate-limited (20/minute per IP) since these all
run an ML model - unauthenticated/unlimited access to compute-heavy
endpoints is an easy way to overload the server.
"""
from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.session import get_db
from app.models.user_profile import UserProfile
from app.schemas.prediction import (
    CrowdPredictionRequest,
    DelayPredictionRequest,
    DemandForecastRequest,
    FrequencyRecommendationRequest,
    MaintenanceReadingRequest,
    MaintenanceResponse,
    PredictionResponse,
    SmartRecommendation,
)
from app.services import prediction_service

router = APIRouter(
    prefix="/predictions",
    tags=["AI Prediction"]
)

limiter = Limiter(key_func=get_remote_address)


@router.post("/crowd", response_model=PredictionResponse)
@limiter.limit("20/minute")
def predict_crowd(
    request: Request,
    payload: CrowdPredictionRequest,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    """Crowd prediction models: passenger density estimation."""
    return prediction_service.forecast_crowd(db, payload.station_id, payload.target_datetime)


@router.post("/demand", response_model=list[PredictionResponse])
@limiter.limit("20/minute")
def forecast_demand(
    request: Request,
    payload: DemandForecastRequest,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    """Passenger demand forecasting, hour-by-hour."""
    return prediction_service.forecast_demand(db, payload.station_id, payload.hours_ahead)


@router.post("/delay", response_model=PredictionResponse)
@limiter.limit("20/minute")
def predict_delay(
    request: Request,
    payload: DelayPredictionRequest,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    """Delay impact prediction."""
    return prediction_service.forecast_delay(db, payload.train_id, payload.station_id)


@router.post("/frequency", response_model=PredictionResponse)
@limiter.limit("20/minute")
def recommend_frequency(
    request: Request,
    payload: FrequencyRecommendationRequest,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    """Train frequency recommendations / resource utilization optimization."""
    return prediction_service.recommend_train_frequency(db, payload.station_id, payload.is_peak_hour)


@router.get("/traffic-pattern/{station_id}")
@limiter.limit("20/minute")
def traffic_pattern(
    request: Request,
    station_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    """Traffic pattern analysis: 24h predicted demand curve."""
    return prediction_service.traffic_pattern_analysis(db, station_id)


@router.get("/recommendations/{station_id}", response_model=list[SmartRecommendation])
@limiter.limit("20/minute")
def recommendations(
    request: Request,
    station_id: int,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    """Smart recommendations combining crowd, delay and frequency predictions."""
    return prediction_service.smart_recommendations(db, station_id)


@router.post("/maintenance", response_model=MaintenanceResponse)
@limiter.limit("20/minute")
def predict_maintenance(
    request: Request,
    payload: MaintenanceReadingRequest,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    """New: Predictive maintenance - remaining useful life of a train from
    its current sensor readings (real predictive_maintenance.csv model)."""
    readings = payload.model_dump(exclude={"train_id"})
    return prediction_service.predict_maintenance(payload.train_id, readings)
