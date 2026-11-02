# Repository and implementation notes

## Repository summary (Phase 0)

- **Frontend:** Next.js 14 App Router with React/TypeScript. The patient care UI is `frontend/app/patient/page.tsx`; demo sign-in is `frontend/app/login/[role]/page.tsx`.
- **Backend:** Python 3 / FastAPI. Care intake is routed by `backend/app/api/care.py` and `backend/app/core/pipeline.py`; PathoVision is `backend/app/api/pathovision.py`.
- **Persistence:** SQLAlchemy models exist for users, bookings, alerts, check-ins, events, and conversations in `backend/app/db/models.py`. There was no patient intake record or medication list. The demo patient flow also issues a stateless signed token. The new additive `PatientIntakeRecord` stores records by that token's patient subject; raw prescription and skin images are never saved.
- **Configuration and startup:** Backend settings read `backend/.env` through Pydantic Settings (`backend/app/config.py`). Frontend reads `frontend/.env.local`; start it with `npm run dev` in `frontend`. Start the API with `python -m uvicorn app.main:app --reload` in `backend`. Existing backend dependencies are in `backend/requirements.txt`; frontend dependencies are in `frontend/package.json` and `package-lock.json`.
- **Existing tests:** `backend/tests/` contains pytest coverage; frontend has no configured test runner. Existing tests were not run before these changes in this session.
- **Existing ML:** `backend/ml/augment.py` and `backend/ml/train_triage.py` are the synthetic text triage training pipeline. There was no `ml_service/`; the new image training code and inference service are isolated from backend dependencies.

## Assumptions and decisions

- The two CNNs are educational decision-support demonstrations. Skin models are trained for dermatoscopic HAM10000 images, not phone-camera photos, and must not be represented as diagnoses. The UI always identifies the output as an unvalidated AI aid and directs users to a clinician.
- The prescription classifier only proposes one of the dataset's 78 Bangladesh medicine-word labels. It does not read dose, route, frequency, or a complete prescription. Nothing is saved until the user confirms or edits each suggestion.
- HAM10000 groups are split by `lesion_id` to prevent multiple views of one lesion leaking between train/validation/test. The Rx dataset's official splits are used when found; otherwise a deterministic stratified split is created.
- No Kaggle token was provided or read. Download scripts print the required manual download steps and support a private `kaggle.json` or `KAGGLE_USERNAME` / `KAGGLE_KEY` when the user supplies them. Dataset files and model artifacts are gitignored.
- No real training data, trained model, or performance metrics are bundled. `--synthetic` is for pipeline smoke use only and its metrics are not clinical or real-dataset performance.
- Niramaya's FastAPI service proxies to one separate `ml_service` process at `ML_SERVICE_URL`; this keeps PyTorch and OpenCV out of the web backend requirements.
- `PatientIntakeRecord` is a new additive table keyed by the authenticated demo token subject because the existing schema had no patient record/medication field and no migration framework.

## Known limitations

- HAM10000 contains dermatoscopic images, has limited skin-tone diversity, and covers pigmented lesions; it does not cover rashes, burns, or wounds. Phone photos have a substantial domain shift.
- The Rx model recognizes only the 78 labels in the dataset and sees isolated word crops, not full prescriptions or dosage instructions. Manual correction is required, and a pharmacist should verify every medicine.
- Automatic Rx word segmentation is heuristic. The patient UI lets users remove proposed crops or add crops with image coordinates.
- Neither CNN is a diagnostic or prescribing device. Synthetic runs are engineering smoke checks only.
- This checkout has no `.git` directory or git remote, so branch creation and commits from the pasted prompts are unavailable in this folder copy.
