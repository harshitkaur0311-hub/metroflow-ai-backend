# MetroFlow AI - Backend

AI-powered metro crowd management and scheduling platform.
Status: **Milestone 1 (User Management, Crowd Monitoring) + Milestone 2
(Scheduling Management, AI Prediction) complete and tested.**

Authentication is fully delegated to **Supabase Auth** - this backend
never stores a password. It only verifies the JWT Supabase already
issued to the frontend and maps it to an app-level profile/role.

## Quick start

```bash
python -m venv venv
# Windows: venv\Scripts\Activate
# macOS/Linux: source venv/bin/activate

pip install -r requirements.txt
```

Fill in `.env`:
- `DATABASE_URL` - your Supabase Postgres connection string (already set)
- `SUPABASE_URL`, `SUPABASE_KEY` - from Project Settings -> API (already set)
- `SUPABASE_JWT_SECRET` - Project Settings -> API -> JWT Settings -> "JWT
  Secret". Leave blank if your project uses newer asymmetric signing
  keys; the backend then verifies tokens via the JWKS endpoint instead.

```bash
python -m app.database.init_db     # create tables
python -m app.database.seed        # demo stations/trains/schedules (no login created)

# OR, to load the real dataset (63 real stations/12 cities from
# datasets/*.csv) instead of the synthetic demo network:
python -m app.database.seed_real_data          # add --reset to replace an existing synthetic seed

# Sign up through the frontend (Supabase), then make yourself admin:
python -m app.database.set_user_role <your-email> admin

# AI models come pre-trained (app/ai_engine/saved_models/*.pkl):
#   crowd_model.pkl, delay_model.pkl, frequency_model.pkl, maintenance_model.pkl
# Training does NOT happen here anymore - it's done in Google Colab to keep
# this machine's CPU free. To get updated models, see colab_training/README.md.

uvicorn app.main:app --reload
```

## Real data

`datasets/` at the repo root holds the real CSVs (`stations.csv`,
`passenger_flow.csv`, `train_operations.csv`, `predictive_maintenance.csv`).
`app/database/seed_real_data.py` cleans and loads them into Postgres with
the exact same station ordering/IDs the Colab notebook used to train the
models, so predictions line up with the seeded data. This is a plain
DB-insert script - no model training, safe to run on any machine.

## AI predictions (4 models)

All four live under `app/ai_engine/prediction/`, each loading its
`.pkl` from `app/ai_engine/saved_models/` (with a heuristic fallback if
the file is missing) via `POST /api/v1/predictions/...`:

| Model | Endpoint | Predicts |
|---|---|---|
| `crowd_model.pkl` | `/predictions/crowd` | passenger count at a station |
| `delay_model.pkl` | `/predictions/delay` | expected delay (minutes) |
| `frequency_model.pkl` | `/predictions/frequency` | recommended train frequency |
| `maintenance_model.pkl` | `/predictions/maintenance` | train's remaining useful life (hrs) + health status, from live sensor readings |

API docs: http://127.0.0.1:8000/docs

## Passenger check-in / check-out

`POST /api/v1/checkin` / `POST /api/v1/checkout` - the real "Passenger
Entry & Exit Records" workflow the platform spec calls for. Checking
in bumps the source station's live crowd count (`current_count`) up by
1 immediately; checking out computes the fare (haversine distance x
per-km rate) and moves that +1 from the source station over to the
destination station, same as a passenger actually arriving there.
`GET /api/v1/checkout/active` returns the caller's in-progress journey,
if any. Frontend: `/crowd-monitor`'s "Check In / Check Out" card.

## Live simulator (optional)

Set `ENABLE_SIMULATOR=True` in `.env` to turn on `app/simulator/live_simulator.py`.
Instead of just overwriting each station's count with a raw AI
prediction, it now drives the same check-in/check-out code path a real
passenger uses: a pool of `SIMULATOR_PASSENGER_POOL_SIZE` virtual
passenger accounts (emails ending `@sim.metroflow.internal`, excluded
from the admin Users list) check in at AI-weighted-random stations and
check out after a distance-based travel delay, every
`SIMULATOR_INTERVAL_SECONDS`. Crowd counts move up/down exactly like
real check-ins/check-outs would, and every tick adds real rows to the
`journeys` table.

## Auth flow

1. Frontend calls `supabase.auth.signUp()` / `signInWithPassword()`
   directly (see the frontend's `src/lib/supabase/client.ts` and
   `src/app/(auth)/login/page.tsx`). Supabase issues a JWT.
2. Frontend sends that JWT as `Authorization: Bearer <token>` on every
   API request (wire this into `src/lib/axios.ts` with an interceptor
   that reads `supabase.auth.getSession()`).
3. This backend verifies the JWT's signature (`app/core/security.py`)
   and, on the very first request from a given user, creates a
   matching row in `user_profiles` (default role: `passenger`).
4. To promote someone to `admin`/`operator`, run
   `python -m app.database.set_user_role <email> <role>` - this is the
   only way to create the *first* admin, since every role-changing API
   route itself requires you to already be an admin.

There is intentionally no `/api/v1/auth/register` or `/auth/login`
endpoint on this backend - sign-up and login happen entirely on
Supabase/the frontend. The only auth route here is `GET /api/v1/auth/me`.

## What's implemented

### Milestone 1 - User Management & Crowd Monitoring
- `GET /api/v1/auth/me` - verifies Supabase session, returns/creates profile
- `GET/PUT /api/v1/users/*` - profile management, role-based access control
- `GET/POST/PUT/DELETE /api/v1/stations/*` - station master data
- `POST /api/v1/crowd/` - log a crowd reading
- `GET /api/v1/crowd/dashboard` - live station-wise snapshot
- `GET /api/v1/crowd/heatmap` - crowd heatmap generation
- `GET /api/v1/crowd/congestion` - congestion monitoring
- `GET /api/v1/crowd/{station_id}/inflow-outflow` - inflow/outflow analysis
- `GET /api/v1/crowd/{station_id}/analytics` - station-wise analytics
- `POST /api/v1/checkin/`, `POST /api/v1/checkout/` - passenger entry/exit

### Milestone 2 - Scheduling Management & AI Prediction
- `GET/POST/PUT /api/v1/schedules/*` - train schedule management
- `GET /api/v1/schedules/peak-hours` - peak-hour optimization view
- `PATCH /api/v1/schedules/{id}/delay` - delay handling workflow
- `PATCH /api/v1/schedules/{id}/frequency` - frequency adjustment workflow
- `POST /api/v1/predictions/crowd` - crowd prediction model
- `POST /api/v1/predictions/demand` - passenger demand forecasting
- `POST /api/v1/predictions/delay` - delay impact prediction
- `POST /api/v1/predictions/frequency` - train frequency recommendation
- `GET /api/v1/predictions/traffic-pattern/{station_id}` - traffic pattern analysis
- `GET /api/v1/predictions/recommendations/{station_id}` - smart recommendations
- `GET /api/v1/analytics/traffic-report` - traffic analysis reports
- `WS /ws/monitor` - real-time operational monitoring channel
  (set `ENABLE_SIMULATOR=True` in `.env` to also push simulated live
  crowd updates over this channel every `SIMULATOR_INTERVAL_SECONDS`)

### Kept in the repo, not wired in yet (Milestone 3 scope)
`app/api/v1/alerts.py` has working CRUD code but is deliberately left
out of `app/main.py` so the *running* app stays scoped to Milestone 1
+ 2. Add it back to the router list in `app/main.py` when you start
Milestone 3 (Alert & Notification Module, Week 5-6).

## Notes on this codebase
- `app/api/v1/stations.py`, `schedules.py`, `routes.py` from earlier
  iterations relied on a Supabase table client (`from database import
  supabase`) that never existed in this project. Kept for reference,
  not imported by `app/main.py`. The working replacements are
  `station.py` and `schedule.py`.
- The AI models under `app/ai_engine/saved_models/` are trained on a
  **synthetic** ridership dataset (`app/ai_engine/datasets/generate_dataset.py`)
  since no real ticketing/sensor dataset was provided. Swap in real data
  with the same column shape and re-run the training scripts.
- `DATABASE_URL` in `.env` is quoted because the password contains a `#`
  character, which some `.env` parsers treat as a comment marker.
