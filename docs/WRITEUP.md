# CareCompass AI — short write-up

## Problem and approach

Finding the right kind of care can be confusing, especially when a family member is asking on someone else's behalf. CareCompass provides a guided, multilingual intake and helps the user navigate among a virtual doctor, a home visit, nursing, and home sample collection. It asks a short set of questions only when the answer changes routing. Deterministic red-flag checks run before conversational classification, and emergency UI puts Call 112 first.

## Working demo

The patient assistant accepts typed or spoken input and keeps conversation history in the browser, with server persistence for logged-in demo patients. The booking workflow uses an active synthetic caregiver roster, an availability window, and conflict checks. Providers can review requests on a live dashboard. Patients can send a separate demo alert to dispatch; WebSocket events carry state changes to connected users. SereneMind provides brief general support, an optional local-only mood note, and a crisis response with 112 and Tele-MANAS 14416.

## Safety and privacy

CareCompass does not diagnose, prescribe, provide therapy, or place emergency calls. The dispatch and appointment features are simulations. Dataset and roster data are synthetic and not clinically validated. The dispatch map is a local schematic so patient coordinates are not sent to a map vendor. Wellness messages are not persisted. The report upload, continuous phone loop, multi-agent approval workflow, and provider directory map remain clearly marked Coming soon.

## Evaluation

The training pipeline uses five-fold GroupKFold grouped by normalized request text. `backend/ml/train_triage.py` writes metrics labelled synthetic data. These scores describe a small synthetic dataset, not clinical performance. The scored triage endpoint remains separate from the assistant experience.
