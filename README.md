# Harbor Health Patient Portal

A minimal patient portal built for the take-home assignment. Patients can request and cancel appointments, while providers can confirm and reschedule them.

## Stack

- **Frontend:** React 19, TypeScript, Vite
- **Backend:** FastAPI, SQLModel, SQLite
- **Runtime:** Python 3.14 and Node.js 22+

## Run Locally

Start the backend in one terminal:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Start the frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173.

The API is available at http://127.0.0.1:8000. Swagger documentation is available at http://127.0.0.1:8000/docs.

## Product Behavior

Use the role switcher in the top-right corner to view either side of the workflow. Authentication is intentionally omitted for this exercise.

### Patient

- View seeded appointments
- Request an appointment with a preferred date, time, type, and reason
- Cancel confirmed appointments
- Pending appointments cannot be cancelled

### Provider

- View all appointments assigned to the provider
- Confirm pending requests
- Move pending or confirmed appointments to a new time; moving a pending request confirms it immediately
- Conflicting confirmed appointments are rejected

## API

```text
GET  /api/health
GET  /api/appointments?patient_email=...
GET  /api/appointments?provider_id=...
POST /api/appointments
POST /api/appointments/{id}/confirm
POST /api/appointments/{id}/reschedule
POST /api/appointments/{id}/cancel
GET  /api/appointments/{id}/history
```

Mutation requests include the appointment `version` returned by the list endpoint.

## Assignment Decisions

### Stale updates

Appointments use optimistic concurrency through a version number. Every mutation checks the version it received against the current database row. If another user changed the appointment first, the request returns `409 Conflict`, preserves the successful change, and the frontend refreshes the list.

### Audit history

Every request, confirmation, reschedule, and cancellation appends a record to `appointment_history`. Each record stores the action, previous status/time, new status/time, actor role, actor identifier, and timestamp.

### Notifications

Confirmation, rescheduling, and cancellation write notification jobs to `notification_outbox` in the same transaction as the appointment change. A FastAPI background task then logs the simulated delivery. Notification processing cannot slow down or roll back the appointment response.

For production traffic, the outbox would be processed by a durable worker with retries and monitoring.

### Overlapping appointments

Confirmation and rescheduling of confirmed appointments use a SQLite `BEGIN IMMEDIATE` write transaction. The transaction re-reads the appointment, checks for overlapping confirmed appointments, and then updates the row. Concurrent confirmations are serialized: one succeeds and the other receives `409 Conflict`.

## Data

SQLite is created at `backend/patient_portal.db` on first startup. The application creates its tables and seeds three appointments automatically when the database is empty.

## Validation

```bash
cd frontend
npm run build
```

The backend was validated with API smoke tests covering startup, seeded listing, confirmation, audit history, stale updates, and overlap rejection.

## Timezone

All appointment times and application timestamps use India Standard Time (`Asia/Kolkata`). The API stores and returns IST wall-clock values without a UTC conversion, and the frontend formats values explicitly in IST. This keeps `datetime-local` input, persistence, API responses, and display consistent.

If you created local data before this timezone change, remove `backend/patient_portal.db` once and restart the backend so the development seed data is recreated under the IST policy. Existing rows cannot be converted reliably without knowing whether each old value was entered as UTC or IST.
