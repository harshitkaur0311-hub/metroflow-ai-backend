
import argparse
import os

import pandas as pd

from app.database.init_db import create_tables
from app.database.session import SessionLocal
from app.enums.day_type import DayType
from app.models.alert import Alert
from app.models.crowd_log import CrowdLog
from app.models.journey import Journey
from app.models.line_station import LineStation
from app.models.metro_line import MetroLine
from app.models.prediction import Prediction
from app.models.station import Station
from app.models.train import Train
from app.models.train_location import TrainLocation
from app.models.train_schedule import TrainSchedule

DEFAULT_DATASET_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "datasets")
LINE_COLORS = ["#1E88E5", "#8E24AA", "#E53935", "#00897B", "#6A1B9A", "#F4511E"]
NAMED_LINE_COLORS = {
    "yellow": "#EAB308",
    "blue": "#2563EB",
    "red": "#DC2626",
    "green": "#16A34A",
    "violet": "#7C3AED",
    "magenta": "#DB2777",
    "pink": "#EC4899",
    "grey": "#6B7280",
    "gray": "#6B7280",
    "purple": "#9333EA",
    "orange": "#EA580C",
    "aqua": "#06B6D4",
}


def _color_for_line(line_name: str, fallback_index: int) -> str:
    lowered = line_name.lower()
    for keyword, color in NAMED_LINE_COLORS.items():
        if keyword in lowered:
            return color
    return LINE_COLORS[fallback_index % len(LINE_COLORS)]


def _norm_key(city: str, name: str) -> tuple[str, str]:
    return city.strip().lower(), name.strip().lower()


def _load_csvs(dataset_dir: str) -> dict[str, pd.DataFrame]:
    paths = {
        "passenger_flow": os.path.join(dataset_dir, "passenger_flow.csv"),
        "stations": os.path.join(dataset_dir, "stations.csv"),
        "train_operations": os.path.join(dataset_dir, "train_operations.csv"),
        "predictive_maintenance": os.path.join(dataset_dir, "predictive_maintenance.csv"),
    }
    missing = [name for name, p in paths.items() if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(
            f"Missing CSV(s) in {dataset_dir}: {', '.join(missing)}.csv - "
            f"copy your 4 real CSVs there first (or pass --dir)."
        )
    return {name: pd.read_csv(p) for name, p in paths.items()}


def _clean_stations(stations_raw: pd.DataFrame) -> pd.DataFrame:
    stations = stations_raw.rename(
        columns={"City": "city", "Station": "station_name", "Line": "line",
                 "Latitude": "latitude", "Longitude": "longitude"}
    ).copy()

    # Basic cleaning: strip whitespace, drop exact duplicates, drop any
    # row missing a required field (shouldn't happen on the real file,
    # but keep the script safe against a re-export with gaps).
    for col in ["city", "station_name", "line"]:
        stations[col] = stations[col].astype(str).str.strip()
    stations = stations.drop_duplicates(subset=["city", "station_name"])
    stations = stations.dropna(subset=["city", "station_name", "line", "latitude", "longitude"])

    stations = stations.reset_index(drop=True)
    stations["_csv_order"] = stations.index

    stations = stations.sort_values(["city", "line", "station_name"]).reset_index(drop=True)
    stations["station_id"] = stations.index + 1
    return stations


def _clean_passenger_flow(passenger_flow: pd.DataFrame, station_id_map: dict) -> pd.DataFrame:
    df = passenger_flow.copy()
    df["station_name"] = df["station_name"].astype(str).str.strip()
    df["city"] = df["city"].astype(str).str.strip()
    df["_key"] = df.apply(lambda r: _norm_key(r["city"], r["station_name"]), axis=1)
    df["station_id"] = df["_key"].map(station_id_map)
    before = len(df)
    df = df.dropna(subset=["station_id", "entries", "exits"])
    dropped = before - len(df)
    if dropped:
        print(f"passenger_flow: dropped {dropped} row(s) that didn't match a known station")
    df["station_id"] = df["station_id"].astype(int)
    df["entries"] = df["entries"].clip(lower=0)
    df["exits"] = df["exits"].clip(lower=0)
    return df


def _clean_train_operations(train_ops: pd.DataFrame, station_id_map: dict) -> pd.DataFrame:
    tdf = train_ops.copy()
    tdf["station_name"] = tdf["station_name"].astype(str).str.strip()
    tdf["city"] = tdf["city"].astype(str).str.strip()
    tdf["_key"] = tdf.apply(lambda r: _norm_key(r["city"], r["station_name"]), axis=1)
    tdf["station_id"] = tdf["_key"].map(station_id_map)
    before = len(tdf)
    tdf = tdf.dropna(subset=["station_id"])
    dropped = before - len(tdf)
    if dropped:
        print(f"train_operations: dropped {dropped} row(s) that didn't match a known station")
    tdf["station_id"] = tdf["station_id"].astype(int)
    tdf["delay_reason"] = tdf["delay_reason"].fillna("None")
    tdf["delay_arrival_min"] = tdf["delay_arrival_min"].fillna(0).clip(lower=0)
    tdf["scheduled_arrival"] = pd.to_datetime(tdf["scheduled_arrival"])
    tdf["scheduled_departure"] = pd.to_datetime(tdf["scheduled_departure"])
    return tdf


def seed(dataset_dir: str = DEFAULT_DATASET_DIR, reset: bool = False) -> None:
    create_tables()
    db = SessionLocal()

    try:
        if reset:
            print("--reset: clearing existing station/line/train schedule/crowd data...")
            db.query(Journey).delete()
            db.query(Prediction).delete()
            db.query(TrainLocation).delete()
            db.query(Alert).delete()
            db.query(CrowdLog).delete()
            db.query(TrainSchedule).delete()
            db.query(LineStation).delete()
            db.query(MetroLine).delete()
            db.query(Station).delete()
            db.query(Train).delete()
            db.commit()
        elif db.query(Station).count() > 0:
            print("Database already has stations - pass --reset to wipe and reseed with real data.")
            return

        raw = _load_csvs(dataset_dir)
        stations_df = _clean_stations(raw["stations"])
        station_id_map = dict(
            zip(
                stations_df.apply(lambda r: _norm_key(r["city"], r["station_name"]), axis=1),
                stations_df["station_id"],
            )
        )

        # --- Stations (real, one row per real station across 12 cities) ---
        station_rows = []
        for _, row in stations_df.iterrows():
            code = "".join(ch for ch in row["city"].upper() if ch.isalpha())[:3] + f"{int(row['station_id']):03d}"
            station_rows.append(Station(
                station_code=code,
                station_name=row["station_name"],
                city=row["city"],
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                is_interchange=False,
                capacity=5000,
            ))
        db.add_all(station_rows)
        db.flush()  # assign real DB ids

        db_station_by_ordinal = dict(zip(stations_df["station_id"], station_rows))

        line_keys = stations_df[["city", "line"]].drop_duplicates().reset_index(drop=True)
        line_by_key: dict[tuple[str, str], MetroLine] = {}
        for i, (_, lrow) in enumerate(line_keys.iterrows()):
            city_slug = "".join(ch for ch in lrow["city"].upper() if ch.isalpha())[:3]
            line_slug = "".join(ch for ch in lrow["line"].upper() if ch.isalpha())[:4]
            line = MetroLine(
                line_code=f"{city_slug}-{line_slug}-{i}",
                line_name=f"{lrow['city']} Metro - {lrow['line']}",
                color=_color_for_line(lrow["line"], i),
            )
            db.add(line)
            line_by_key[(lrow["city"], lrow["line"])] = line
        db.flush()

        for _, srow in stations_df.iterrows():
            line = line_by_key[(srow["city"], srow["line"])]
            same_line_stations = stations_df[
                (stations_df["city"] == srow["city"]) & (stations_df["line"] == srow["line"])
            ].sort_values("_csv_order").reset_index(drop=True)
            order = int(same_line_stations.index[same_line_stations["station_id"] == srow["station_id"]][0]) + 1
            db.add(LineStation(
                line_id=line.id,
                station_id=db_station_by_ordinal[srow["station_id"]].id,
                station_order=order,
                distance_from_previous=2.5 if order > 1 else 0,
            ))
        train_ids = sorted(set(raw["predictive_maintenance"]["train_id"].astype(str).str.strip()) |
                            set(raw["train_operations"]["train_id"].astype(str).str.strip()))
        train_by_number: dict[str, Train] = {}
        for train_number in train_ids:
            train = Train(train_number=train_number, capacity=1200)
            db.add(train)
            train_by_number[train_number] = train
        db.flush()

        ops_df = _clean_train_operations(raw["train_operations"], station_id_map)
        schedule_rows = []
        for _, orow in ops_df.iterrows():
            train = train_by_number.get(str(orow["train_id"]).strip())
            db_station = db_station_by_ordinal.get(int(orow["station_id"]))
            if not train or not db_station:
                continue
            is_weekend = int(orow["scheduled_arrival"].weekday() >= 5)
            hour = orow["scheduled_arrival"].hour
            is_peak = 8 <= hour <= 11 or 17 <= hour <= 20
            schedule_rows.append(TrainSchedule(
                train_id=train.id,
                station_id=db_station.id,
                arrival_time=orow["scheduled_arrival"].time(),
                departure_time=orow["scheduled_departure"].time(),
                platform_number=(int(orow["station_sequence"]) % 2) + 1,
                day_type=DayType.WEEKEND if is_weekend else DayType.WEEKDAY,
                is_peak_hour=bool(is_peak),
                frequency_minutes=5 if is_peak else 12,
                delay_minutes=int(round(orow["delay_arrival_min"])),
            ))
        db.add_all(schedule_rows)

        flow_df = _clean_passenger_flow(raw["passenger_flow"], station_id_map)
        flow_df["passenger_count"] = flow_df["entries"] + flow_df["exits"]
        recent_avg = flow_df.groupby("station_id")["passenger_count"].mean()

        crowd_rows = []
        for ordinal, db_station in db_station_by_ordinal.items():
            avg_count = recent_avg.get(ordinal, db_station.capacity * 0.2)
            crowd_rows.append(CrowdLog(
                station_id=db_station.id,
                current_count=int(min(avg_count, db_station.capacity)),
            ))
        db.add_all(crowd_rows)

        db.commit()
        print(
            f"Seeded {len(station_rows)} real stations across "
            f"{stations_df['city'].nunique()} cities, {len(line_by_key)} lines, "
            f"{len(train_by_number)} trains, {len(schedule_rows)} real schedule "
            f"entries (from train_operations.csv), and {len(crowd_rows)} crowd "
            f"snapshots (from passenger_flow.csv averages).\n"
            f"Station IDs are ordinal 1..{len(station_rows)} in city/line/name "
            f"order - matches Step 5 of the Colab training notebook, so a\n"
            f"prediction for station_id=N here means the same real station."
        )

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=DEFAULT_DATASET_DIR, help="Folder containing the 4 CSVs")
    parser.add_argument("--reset", action="store_true", help="Wipe existing station/line/schedule/crowd data first")
    args = parser.parse_args()
    seed(dataset_dir=args.dir, reset=args.reset)
