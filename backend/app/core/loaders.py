import csv,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
RAW=ROOT/"data"/"raw"
def load_dataset():return [json.loads(x) for x in (RAW/"triage_dataset.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
def load_caregivers():
 with (RAW/"caregivers.csv").open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
