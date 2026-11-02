# Niramaya Vision

Two isolated research prototypes: DermaScan classifies seven HAM10000 lesion labels, and RxRead provides a CRNN (CNN + BiLSTM + CTC) architecture and lexicon utilities. This is an educational care-navigation aid, not a diagnosis or dispensing system. It must not guide treatment or medication use.

## Data and layout

| Folder | Dataset | Source |
|---|---|---|
| `ml/data/ham10000/` | HAM10000 metadata and images | [Kaggle dataset](https://www.kaggle.com/datasets/kmader/skin-cancer-mnist-ham10000); original dataset paper [Tschandl et al., Scientific Data (2018)](https://doi.org/10.1038/sdata.2018.161) |
| `ml/data/iam/` | IAM word images and `words.txt` | [Official IAM handwriting database](https://fki.tic.heia-fr.ch/databases/iam-handwriting-database), free account/registration required; download word images (`words.tgz`) and ASCII labels (`ascii.tgz`) |
| `ml/data/rx_bd/` | Segmented Bangladesh prescription words | [Kaggle dataset](https://www.kaggle.com/datasets/mamun1113/doctors-handwritten-prescription-bd-dataset) |
| `ml/data/lexicon/` | Indian A-Z medicine CSV | [Kaggle dataset](https://www.kaggle.com/datasets/shudhanshusingh/az-medicine-dataset-of-india) |

Place extracted data under those folders. Keep dataset licenses and attribution with your submitted coursework. `ml/data/` and trained artifacts are ignored by Git. Expected top-level layout:

```text
ml/data/ham10000/  ml/data/iam/  ml/data/rx_bd/  ml/data/lexicon/
ml/artifacts/derma/  ml/artifacts/rx/  ml/reports/derma/  ml/reports/rx/
```

## Isolated setup (PowerShell)

From the repository root:

```powershell
py -3.11 -m venv .venv-ml
.\.venv-ml\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r ml\requirements-ml.txt
```

Do not install PyTorch or OpenCV into `backend/` or the frontend. On a CPU-only machine, PyTorch uses CPU. Optional dependencies can be installed separately: `python -m pip install kaggle pillow-heif`; if pretrained torchvision weights cannot be downloaded, the DermaScan trainer uses random initialization (recorded in its metadata).

## DermaScan

```powershell
python -m ml.derma.train --model custom --quick --synthetic
python -m ml.derma.evaluate --model custom --synthetic
python -m ml.derma.export --model custom
```

For dataset training, replace `--synthetic` with `--data-dir ml/data/ham10000`; start with `--quick` to validate the dataset, then train without it. Grouped splits keep a `lesion_id` within one split. Quick and synthetic runs are demonstrations only. Synthetic images are colored blobs and cannot establish clinical model quality. Report independent held-out metrics only.

## RxRead

```powershell
python -m ml.rx.train --stage bd_only --quick --synthetic
python -m ml.rx.evaluate
python -m ml.rx.export
```

For research training, first extract IAM under `ml/data/iam/`, then run `python -m ml.rx.train --stage pretrain --resume`; fine-tune with BD labels using `--stage finetune --resume`. The CRNN/CTC training loop runs on supplied IAM or BD word images. Synthetic images validate the optimization and artifact path only; the model metadata marks those weights untrained and the inference service will not serve them. The Rx evaluator currently reports that independent test metrics are unavailable rather than inventing CER/WER. Run an independent BD test split before claiming performance.

## Run the inference service

Install service requirements into a separate environment, then:

```powershell
py -3.11 -m venv .venv-vision-service
.\.venv-vision-service\Scripts\Activate.ps1
python -m pip install -r ml_service\requirements-service.txt
$env:PYTHONPATH = (Get-Location).Path
$env:ML_SERVICE_PORT = "8001"
python -m uvicorn ml_service.main:app --host 127.0.0.1 --port 8001
```

The app backend reads `ML_SERVICE_URL=http://localhost:8001`. Missing/untrained model artifacts return a feature-specific 503; the intake can continue with manual entry. To run the app locally, use its existing instructions in the root README and set `ML_SERVICE_URL` in `backend/.env`.

## Colab

Open `ml/notebooks/niramaya_vision_colab.ipynb`, mount Drive, copy datasets beneath `NiramayaData/` (or upload `kaggle.json`), and use the notebook cells to train and export. IAM requires an account at the official site. Save checkpoints and exported artifacts to Drive between sessions; copy the resulting artifact folders back to `ml/artifacts/` locally.

## Reports

Reports are written under `ml/reports/`. A bootstrap/synthetic run is labeled as such. The evaluator intentionally does not invent performance numbers; real comparisons require held-out test splits. A single accuracy number can conceal poor recall on rare high-risk classes in a highly imbalanced dataset.

## Inspired by

- [`Pranaykarvi/derma-ai`](https://github.com/Pranaykarvi/derma-ai) — the project idea of HAM10000 transfer learning, Grad-CAM and condition information. This code is a clean reimplementation, not copied code.
- [`githubharald/SimpleHTR`](https://github.com/githubharald/SimpleHTR) — MIT-licensed project; the architectural idea of CNN + recurrent network + CTC word recognition on IAM. This code is a clean reimplementation, not copied code.

Dataset sources: HAM10000 paper DOI above; IAM official site above; BD prescription Kaggle page above; A-Z medicines Kaggle page above. Review each dataset's current license/terms before redistribution or non-coursework use.
