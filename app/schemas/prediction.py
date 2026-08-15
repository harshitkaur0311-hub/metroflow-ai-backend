from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict

from app.enums.prediction_type import PredictionType


class PredictionCreate(BaseModel):
    station_id: int
    predicted_count: int | None = None
    confidence: float = 0
    prediction_type: PredictionType = PredictionType.CROWD
    predicted_value: float = 0
    target_datetime: datetime | None = None
    model_version: str | None = None


class PredictionResponse(BaseModel):
    id: int
    station_id: int
    predicted_count: int | None = None
    confidence: float
    prediction_type: PredictionType
    predicted_value: float
    target_datetime: datetime | None = None
    model_version: str | None = None
    model_config = ConfigDict(
        from_attributes=True
    )


# --- Request/response shapes used by the AI Prediction Module endpoints ---

class CrowdPredictionRequest(BaseModel):
    station_id: int
    target_datetime: datetime | None = None


class DemandForecastRequest(BaseModel):
    station_id: int
    hours_ahead: int = 6


class DelayPredictionRequest(BaseModel):
    train_id: int
    station_id: int


class FrequencyRecommendationRequest(BaseModel):
    station_id: int
    is_peak_hour: bool = False


class SmartRecommendation(BaseModel):
    station_id: int
    title: str
    detail: str
    severity: str = "info"


# --- New: Predictive Maintenance (real predictive_maintenance.csv dataset) ---

class MaintenanceReadingRequest(BaseModel):
    train_id: int
    compressor_pressure_bar: float
    motor_current_amp: float
    oil_temperature_c: float
    vibration_amplitude_mm: float
    air_leakage_flow: float
    operating_hours: float


class MaintenanceResponse(BaseModel):
    train_id: int
    predicted_remaining_useful_life_hrs: float
    health_status: str
    model_version: str
