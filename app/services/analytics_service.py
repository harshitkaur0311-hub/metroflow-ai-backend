
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.crowd_log import CrowdLog
from app.models.prediction import Prediction
from app.models.station import Station
from app.models.train_schedule import TrainSchedule
from app.utils.geo import cities_for_state


def traffic_analysis_report(db: Session, hours: int = 24, state: str | None = None) -> dict:
    since = datetime.utcnow() - timedelta(hours=hours)
    cities = cities_for_state(state)

    per_station_query = (
        db.query(
            CrowdLog.station_id,
            func.avg(CrowdLog.current_count).label("avg_count"),
            func.max(CrowdLog.current_count).label("peak_count"),
        )
        .filter(CrowdLog.created_at >= since)
    )
    if cities:
        per_station_query = per_station_query.join(
            Station, Station.id == CrowdLog.station_id
        ).filter(Station.city.in_(cities))
    per_station = per_station_query.group_by(CrowdLog.station_id).all()

    station_query = db.query(Station)
    if cities:
        station_query = station_query.filter(Station.city.in_(cities))
    stations = {s.id: s.station_name for s in station_query.all()}

    report_rows = [
        {
            "station_id": row.station_id,
            "station_name": stations.get(row.station_id, "Unknown"),
            "average_count": round(row.avg_count, 1) if row.avg_count else 0,
            "peak_count": row.peak_count or 0,
        }
        for row in per_station
    ]

    busiest = max(report_rows, key=lambda r: r["peak_count"], default=None)
    delayed_query = db.query(TrainSchedule).filter(TrainSchedule.delay_minutes > 0)
    if cities:
        delayed_query = delayed_query.join(
            Station, Station.id == TrainSchedule.station_id
        ).filter(Station.city.in_(cities))
    total_delayed = delayed_query.count()

    return {
        "window_hours": hours,
        "stations": sorted(report_rows, key=lambda r: r["peak_count"], reverse=True),
        "busiest_station": busiest,
        "currently_delayed_schedules": total_delayed,
        "generated_at": datetime.utcnow(),
    }


def prediction_insights(db: Session, limit: int = 20, state: str | None = None) -> list[Prediction]:
    query = db.query(Prediction)
    cities = cities_for_state(state)
    if cities:
        query = query.join(Station, Station.id == Prediction.station_id).filter(
            Station.city.in_(cities)
        )
    return query.order_by(Prediction.created_at.desc()).limit(limit).all()


def operational_monitoring_summary(db: Session, state: str | None = None) -> dict:
    cities = cities_for_state(state)

    station_query = db.query(Station).filter(Station.is_active.is_(True))
    schedule_query = db.query(TrainSchedule)
    delayed_query = db.query(TrainSchedule).filter(TrainSchedule.delay_minutes > 0)
    if cities:
        station_query = station_query.filter(Station.city.in_(cities))
        schedule_query = schedule_query.join(
            Station, Station.id == TrainSchedule.station_id
        ).filter(Station.city.in_(cities))
        delayed_query = delayed_query.join(
            Station, Station.id == TrainSchedule.station_id
        ).filter(Station.city.in_(cities))

    total_stations = station_query.count()
    total_schedules = schedule_query.count()
    delayed = delayed_query.count()

    return {
        "active_stations": total_stations,
        "total_scheduled_trips": total_schedules,
        "currently_delayed": delayed,
        "on_time_rate": round(1 - (delayed / total_schedules), 3) if total_schedules else 1.0,
    }
