# Niramaya image CNNs

Two isolated educational pipelines live here: HAM10000 skin-lesion risk triage (`ml.skin`) and handwritten medicine-word classification (`ml.rx`). Install training dependencies into a separate environment; do not add PyTorch or OpenCV to `backend/requirements.txt`.

```powershell
python -m venv .venv-ml
.venv-ml\Scripts\Activate.ps1
python -m pip install -r ml/requirements-ml.txt
```

## Data

HAM10000 is available from [Kaggle](https://www.kaggle.com/datasets/kmader/skin-cancer-mnist-ham10000) and its original Harvard Dataverse record (DOI `10.7910/DVN/DBW86T`). The prescription word dataset is on [Kaggle](https://www.kaggle.com/datasets/mamun1113/doctors-handwritten-prescription-bd-dataset) and [Mendeley Data](https://data.mendeley.com/datasets/zjjtptvn6f). The Kaggle HAM10000 listing reports 10,015 images and CC BY-NC-SA 4.0; the Mendeley prescription mirror reports 4,680 word crops across 78 classes under CC BY 4.0. Check the exact source terms before research or redistribution. Do not place patient data in these folders.

Download with a private Kaggle API token configured at `~/.kaggle/kaggle.json` (or environment variables `KAGGLE_USERNAME` and `KAGGLE_KEY`):

```powershell
python -m ml.skin.data --download
python -m ml.rx.data --download
```

Without Kaggle credentials, each command prints the manual download URL and expected target folder (`ml/data/ham10000/` or `ml/data/rx_bd/`) and exits cleanly. Unzip downloads there. No credential file should be committed.

## Train, evaluate, export

```powershell
python -m ml.skin.train --synthetic
python -m ml.skin.evaluate --synthetic
python -m ml.skin.export
python -m ml.rx.train --synthetic
python -m ml.rx.evaluate --synthetic
python -m ml.rx.export
```

For real data use `python -m ml.skin.train --model custom`, then `--model transfer`; Rx uses `python -m ml.rx.train --model custom` and `--model transfer`. `--quick` limits data/epochs for a laptop smoke run. Full HAM10000 training is best run in the supplied Colab notebooks on a GPU. Reports are written under `ml/reports/{skin,rx}/`; deployable weights and JSON metadata go under `ml/artifacts/{skin,rx}/` (gitignored). No performance claim should use synthetic or quick-run results.

## Local app

Run the separate model service in one terminal:

```powershell
python -m pip install -r ml_service/requirements-service.txt
python -m uvicorn ml_service.main:app --host 127.0.0.1 --port 8001 --reload
```

The Niramaya API proxies optional uploads to `ML_SERVICE_URL` (default `http://127.0.0.1:8001`). If a model is absent, information and Rx segmentation remain available; prediction endpoints return a clear `model_missing` response and the intake UI offers manual entry/continuation.

The skin classifier uses dermatoscopic HAM10000 images and is not a diagnostic device. Rx predictions are only candidate medicine names; users must confirm/correct each one and a pharmacist should verify the prescription. The Rx pipeline does not read dosage or instructions.

## RxRead CRNN/CTC training

The open-vocabulary RxRead model uses a CNN + bidirectional LSTM + CTC recognizer, separate from the existing closed-set RxCNN baseline:

```powershell
python -m ml.rx.train_ctc --stage pretrain   # optional IAM word pretraining
python -m ml.rx.train_ctc --stage finetune   # BD prescription words
python -m ml.rx.train_ctc --stage bd_only    # BD baseline from scratch
python -m ml.rx.export_ctc
python -m ml.rx.evaluate_ctc
```

HAM10000 belongs in `ml/data/ham10000/`, IAM words in `ml/data/iam/`, the prescription dataset in `ml/data/rx_bd/`, and the A-Z medicine CSV in `ml/data/lexicon/`. Training reports clearly when data is missing. Model artifacts are gitignored. Code alone is not a trained model: the app returns `model_missing` until real training and export finish.

DermaScan is scoped to dermatoscopic HAM10000-like images and does not generalize to every medical image. RxRead suggests candidate transcriptions and lexicon matches; a person must verify each name and a pharmacist should check the prescription. Neither feature is a diagnosis or prescription, and RxRead does not read dosage instructions.

## Inspired by

- DermaScan's educational project idea: [Pranaykarvi/derma-ai](https://github.com/Pranaykarvi/derma-ai). This repository contains an independent PyTorch implementation.
- RxRead's CRNN/CTC architecture idea: [githubharald/SimpleHTR](https://github.com/githubharald/SimpleHTR). This repository contains an independent PyTorch implementation.
