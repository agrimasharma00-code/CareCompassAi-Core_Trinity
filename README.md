# CareCompass AI

CareCompass is a synthetic-data care-navigation demo. It provides a guided patient intake, caregiver request workflow, dispatch demo alerts, and a supportive wellbeing check-in. It does not diagnose, prescribe, or contact emergency services.

## Local setup

1. Use Python 3.11+ and Node 20+.
2. In `backend`, create a virtual environment, install `requirements.txt`, copy `.env.example` to `.env`, and set `DEMO_PASSWORD`.
3. In `frontend`, run `npm install`, copy `.env.example` to `.env.local`, and set `NEXT_PUBLIC_DEMO_PASSWORD` to the same demo password.
4. Run the API from `backend` with `uvicorn app.main:app --reload` and the UI from `frontend` with `npm run dev`.
5. Open `http://localhost:3000`. The API is at `http://localhost:8000/docs`.

## Run with Docker

1. Create `backend/.env` from `backend/.env.example` and set `DEMO_PASSWORD` (and a private `JWT_SECRET`). Create `frontend/.env.local` from `frontend/.env.local.example`. These files are supplied to the containers with Compose `env_file`; secrets are not copied into either image.
2. From the repository root, run `docker compose up --build`. The backend trains the synthetic triage model during image build using the exact pinned Python package versions in `backend/requirements.txt`.
3. Wait for the backend `/health` check to pass. Compose starts the frontend only after the backend is healthy.
4. Open `http://localhost:3000`; the browser calls the API at `http://localhost:8000`.

SQLite is stored in a named volume mounted at `/app/db` with `DATABASE_URL=sqlite:////app/db/carecompass.db`, so the database survives container replacement. Synthetic data is mounted read-only at `/app/data`. To stop the demo, run `docker compose down`; to remove the persisted database too, run `docker compose down -v`.

## Demo logins and flow

At `/login`, use Demo as Patient, Demo as Dispatch, or choose an active provider from Demo as Provider. Patient flow: describe a concern, answer the short red-flag/intake questions, optionally request a matched caregiver, then use the labelled demo check-in. Dispatch flow: open `/dispatch` in a second browser session to receive demo alerts and advance their status. Provider flow: open `/provider` to review and accept or reject booking requests. The `/serenemind` page offers a private-in-browser mood check-in and general supportive chat.

## Boundaries

All accounts and roster entries are synthetic. Dispatch is a dashboard simulation, not an ambulance service. Emergency? Call 112 directly. The current dispatch map is a local schematic that avoids disclosing patient coordinates to a third party. The Nexus, CareCall, PathoVision, and CareConnect modules are clearly marked Coming soon. Do not upload real medical reports to this demo.
