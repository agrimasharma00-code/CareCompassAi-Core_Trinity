# Niramaya Vision implementation notes

## Phase 0: repository and baseline

- Frontend: Next.js 14 / React, custom CSS and inline styles, no component library and no i18n framework. Patient intake lives in `frontend/app/patient/page.tsx`; the optional Vision section is mounted in this flow.
- Backend: Python FastAPI under `backend/app`; routes use `APIRouter` and JWT Bearer auth (`backend/app/api/auth.py`). Patient identity and role are verified from the signed token.
- Storage: SQLAlchemy models in `backend/app/db/models.py`; SQLite defaults are in `backend/app/config.py`. There is no Alembic migration setup; `initialize_database()` in `backend/app/db/database.py` uses `create_all` plus guarded SQLite `ALTER TABLE` upgrades.
- Before this feature, no medication or intake record field existed. Assistant history lived in `Conversation.messages`; triage consumes request facts and computes results in `backend/app/core/pipeline.py::run`, with urgency levels `emergency`, `same_day`, `scheduled`. The explainable score lives in `backend/app/core/urgency_score.py::compute_urgency_score`. Booking triage reasons are assembled and stored in `backend/app/api/bookings.py::_handoff` / `Booking.handoff_summary`, which the provider view displays. Confirmed medicines and skin results now live in JSON fields on `Conversation`; booking handoffs expose them to the provider without adding medication-based priority rules.
- Voice is implemented separately under `backend/app/api/voice.py` and `backend/app/integrations/sarvam_client.py`; it is unchanged by this feature.
- Configuration loads through Pydantic Settings from `.env` and environment variables. Existing local run flow uses backend Uvicorn and frontend Next.js dev server; the ML service has separate port 8001 and a separate Docker Compose service.
- Tests: backend `python -m pytest -q`; frontend `npm run test:unit` and `npx tsc --noEmit`; frontend production build `npm run build`.
- The pre-existing `backend/ml/` package is the text triage trainer; vision work lives in this separate top-level `ml/` package. No `ml_service/` existed before this feature.
- Baseline before vision changes: backend pytest 73 passed; frontend unit tests 6 passed; TypeScript passed; frontend build passed (captured in the preceding CareCompass task).
- The current environment has Python/FastAPI for the app but no PyTorch or torchvision installed. Vision dependencies remain isolated in `ml/requirements-ml.txt` and `ml_service/requirements-service.txt`.
- No HAM10000, IAM, BD prescription, A-Z medicine data, or handwriting font files were found in the repository during initial inspection. Training must be run after the user supplies datasets or with the documented synthetic demo mode.
- Current runtime check: `backend/venv` has no torch/torchvision and the ML service dependencies are not installed here. So real PyTorch training/inference could not be executed in this environment; the synthetic and model routes remain disabled until the isolated ML/service requirements are installed and trained artifacts exist.

## Limitations and safety

- HAM10000 is dermatoscopic; phone photos may perform worse. Skin-tone diversity is limited and the dataset represents pigmented lesions, not all skin conditions.
- Handwriting recognition is limited to marked words, not dosage or frequency. Indian prescription handwriting differs from IAM/BD; the lexicon can be incomplete or outdated.
- Segmentation is heuristic. This is not a diagnostic or dispensing tool. AI medicine suggestions are never persisted until a patient explicitly confirms or corrects them.
- Condition cards are unreviewed educational content and not medical advice. They contain no medicines, creams, dosages, or home remedies.
- Expected fallbacks: no pretrained model is assumed; missing model artifacts leave only the affected service route unavailable. Missing datasets are reported and never represented as real evaluation results. No synthetic metric is presented as real-world performance.
- Future work: lexicon-constrained beam search, line-level recognition, dosage/frequency extraction, a consented Indian prescription dataset, and dermatologist review of condition cards.
