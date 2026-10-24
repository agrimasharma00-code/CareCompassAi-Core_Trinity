# CareCompass

CareCompass is a HackIIITD prototype for safe healthcare-access routing. A user can describe a request in English, Hindi, or Hinglish; the service either asks one short follow-up question or returns a care route and suitable caregivers. It does **not** diagnose, prescribe, book care, or replace emergency services.

Emergency rules run before the classifier. If the request includes a non-negated emergency warning sign, the service returns an immediate emergency referral, shows the red flags, and never returns caregivers.

## Quick start

Prerequisites: Python 3.11+ (the development machine used Python 3.13) and Node 20+.

```powershell
copy .env.example .env
cd backend
python -m pip install -r requirements.txt
python ml\train_triage.py
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000`. The API health endpoint is `http://localhost:8000/health`.

To run both services in containers, first create `.env` as above, then run:

```powershell
docker compose up --build
```

## API

`POST /api/v1/care/intake-triage-match`

```json
{
  "user_input": "papa ko do din se bukhar hai aur khansi bhi",
  "language": "auto",
  "location": {"lat": 28.545, "lng": 77.192},
  "conversation_history": []
}
```

The response follows the challenge contract: `follow_up_question`, `care_type`, `urgency`, `red_flags`, `reasoning`, and `matched_caregivers`. While a follow-up is needed, all decision fields are null/empty. `emergency_referral` always has `immediate` urgency and an empty caregiver list.

## Train, evaluate, and test

```powershell
cd backend
python ml\train_triage.py
python eval\run_eval.py
python -m pytest -q
```

The trainer creates ignored `backend/models/*.joblib` artifacts. Without them, the API still works using a small deterministic fallback; train before demos for the TF-IDF + LogisticRegression baseline. The evaluator writes `backend/eval/predictions.csv` (ignored) and validates every generated response against the Pydantic response schema.

The current held-out validation run on the deliberately tiny synthetic sample (10 vignettes, 50% stratified split, random seed 42) measured:

- Care-type macro-F1: `0.000`
- Urgency macro-F1: `0.222`
- Emergency recall before / after the 0.25 immediate threshold: `0.000 / 0.000`

These are real results from this sample, not claimed production metrics. Running `eval/run_eval.py` after training produced fixture-set macro-F1 values of `0.693` for care type and `0.778` for urgency, with emergency recall `1.000` and zero under-triage cases; this is a smoke evaluation over the small included fixture data, not an independent clinical benchmark.

## Data and safeguards

No source dataset was present in the repository. The files under `backend/data/sample_*` are clearly labelled synthetic prototype data; replace them with reviewed data before any real use. `red_flags.json` contains deterministic English, Hindi, and Hinglish patterns with basic negation handling. The model is never the only emergency control.

Known limitations:

- Pattern matching and the small baseline classifier do not provide clinical coverage or medical safety assurance.
- Follow-up and Hindi/Hinglish extraction are rule-based, with a best-effort optional Sarvam adapter only when `USE_LLM=true` and `SARVAM_API_KEY` is configured.
- Caregivers, availability, locations, and scores are synthetic in-memory records; there is no database, authentication, booking, or live availability.
- Default frontend coordinates are a demo location near IIIT-Delhi and must be replaced by user-selected location handling in a production product.
