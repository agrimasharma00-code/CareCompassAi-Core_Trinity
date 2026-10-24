# CareCompass AI — Foundation + Core

CareCompass provides **care routing only**. It never diagnoses or prescribes. Emergency routes direct people to 112. The included Sanocare dataset and caregiver roster are fully synthetic, not clinical ground truth, and are for the hackathon only.

## Requirements

- Python 3.11 (backend)
- Node.js 20+ and npm (frontend)
- Docker Compose (optional)

## Local setup

```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

In another terminal:

```powershell
cd frontend
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

The API is at `http://localhost:8000`; frontend at `http://localhost:3000`. The scored endpoint is `POST /api/v1/care/intake-triage-match`. Health checks are `GET /health` and `GET /api/v1/sarvam/ping`. Set `SARVAM_API_KEY` only in `backend/.env`; it is never exposed to or logged by the frontend. The Sarvam adapter is optional and disabled unless configured.

## Demo roles (synthetic accounts)

Copy the sample `DEMO_PASSWORD` from `backend/.env.example` into `backend/.env` (or choose a local demo password). On backend startup, CareCompass creates the SQLite tables and seeds demo users. All demo accounts use the value of `DEMO_PASSWORD`:

| Demo account | Username | Role |
| --- | --- | --- |
| Demo Patient One | `patient1` | patient |
| Demo Patient Two | `patient2` | patient |
| Demo Dispatch Desk | `dispatch` | dispatch |
| Active caregivers | caregiver ID such as `CG_014` | provider |

Provider accounts are created only for caregivers marked active in `backend/data/raw/caregivers.csv`. Their usernames and caregiver IDs match. These synthetic demo credentials are for local judging only; change the sample password before exposing a deployment. The default database is `carecompass.db` in the backend working directory and can be overridden with `DATABASE_URL`. The intake and scored triage routes remain usable without an account.

Authentication signs access tokens with `JWT_SECRET`; set a unique random value of at least 32 characters in `backend/.env` before using the demo logins. The value in `.env.example` is a placeholder for local setup only. If you change `DEMO_PASSWORD`, update `NEXT_PUBLIC_DEMO_PASSWORD` in `frontend/.env.local` so the quick demo buttons stay aligned.

## Docker Compose

Copy `backend/.env.example` to `backend/.env`, then run `docker compose up --build`. Data is mounted read-only.

## Train and evaluate

```powershell
cd backend
python ml/augment.py
python ml/train_triage.py
python eval/run_eval.py --input data/raw/triage_dataset.jsonl --output predictions.csv
python eval/eval_matching.py
python -m pytest tests -q
```

Training uses GroupKFold (5 folds), grouped by normalized request text to prevent duplicate-text leakage. Each fold uses only paraphrases whose source group is in that fold’s training partition; final training uses all training examples and their paraphrases. LogisticRegression and calibrated LinearSVC are compared and the better grouped OOF care-type head is saved. A separate urgency head is trained and compared against the care-type default map; the better grouped score is used (the current pipeline uses the map after this comparison). Evaluation on a provided hidden test file is prediction-only; never train on that file. Metrics from this synthetic set must be called synthetic-data metrics, not clinical performance.

## Measured synthetic-data metrics

Computed on this workspace’s 340-row synthetic dataset. The 5-fold GroupKFold split groups by normalized user text. The selected calibrated LinearSVC scored care-type macro-F1 **0.616** before keyword rules; applying the configured low-confidence keyword prior increased grouped out-of-fold macro-F1 to **0.695**. Emergency recall after the prior was **0.911**, with **5 under-triaged emergency rows**. The separate urgency head scored macro-F1 **0.889**; mapping the care type selected after the keyword prior to its default urgency scored **0.907**, so the pipeline uses the map. These are grouped synthetic-data metrics, not clinical performance.

On the 301 labelled care-type rows, caregiver matching achieved exact top-1 **0.450** (among rows with a non-empty reference list), mean per-row Jaccard **0.421** (non-empty reference rows), NDCG@3 **0.581** (non-empty reference rows), and empty/non-empty agreement **0.887**. The matching evaluator uses reference caregiver IDs and is a synthetic-label comparison.

## Matching baseline

Eligibility is a hard filter: active caregiver, correct role, service radius for in-person service, required procedure skill where identified, and user language. Remaining caregivers are ranked with the dataset weights: language 0.35, proximity 0.30, skill 0.20, rating 0.15. Virtual doctors ignore distance. No eligible caregiver means an empty list. Reasons follow the dataset style and include distance only for in-person matches.

## Safety and configuration

- Deterministic red-flag patterns run before triage. Any recognized flag routes to emergency care, with no caregivers.
- `RED_FLAG_LABEL_MODE=correct` returns detected vocabulary labels. `dataset_compat` emits the dataset's historical chest-pain/breathlessness pair for every detected emergency to support organizer scoring compatibility.
- A high model emergency probability also routes to emergency with an empty red-flag list if no specific phrase matched; this threshold route does not invent a red-flag fact.
- Follow-ups leave care type and urgency null and caregiver results empty. At the configured limit, the core commits to the general home-assessment option.
- `USE_LLM` is off by default. Safety rules remain deterministic; Sarvam failures fall back silently.

## Three-role demo flow

Set `DEMO_PASSWORD` in `backend/.env` and the matching `NEXT_PUBLIC_DEMO_PASSWORD` in `frontend/.env.local`, start the backend and frontend, then use **Demo as Patient**, **Demo as Dispatch**, or **Demo as Provider** on `/login`. A patient can request a caregiver booking and run the labelled six-hour check-in simulation. Providers review requests at `/provider`; dispatch users review and update demo alerts at `/dispatch`. Booking and alert changes are sent to connected dashboards over authenticated WebSockets. Provider distances are computed from the selected patient coordinates and the synthetic caregiver roster. Dispatch locations are shown as a local schematic plot; no map service receives patient coordinates.

All accounts, caregivers, locations, bookings, and dashboard events are synthetic demo data. The dispatch alert is not connected to emergency services or an ambulance. In an emergency, call 112 directly. Re-triage and safety-net messages are demonstrations and do not replace clinical care.

## Known limitations

The data is 100% synthetic and not medically validated. Emergency response labels contain a known artifact: all emergency examples use `chest_pain` and `breathlessness`, even when the text describes other emergencies. The default uses rule-detected flags instead of learning those labels; set `RED_FLAG_LABEL_MODE=dataset_compat` only if required for scoring. Requests repeat heavily, so all reported training metrics must use grouped splits by normalized text. Urgency is strongly tied to care type in this dataset; the code compares a learned urgency prediction with the care-type default map. Caregiver eligibility and skills are inferred from a synthetic roster and basic keyword rules. Demo bookings and alerts are workflow simulations only; there is no real dispatch integration. The product is not a diagnostic, prescribing, or emergency-response service.
