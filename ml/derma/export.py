import argparse,json,shutil
from ml.derma.config import TOP1_HIGH, HIGH_RISK_SUM, UNCERTAIN_MAX, HIGH_RISK
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument("--model",choices=("custom","effnet","resnet50"),default=None);a=p.parse_args()
 src=Path("ml/artifacts/derma/model.pt");meta=Path("ml/artifacts/derma/model_meta.json")
 if not src.exists() or not meta.exists(): raise SystemExit("Train DermaScan first with python -m ml.derma.train --synthetic --quick")
 data=json.loads(meta.read_text())
 if a.model and data.get("architecture")!=a.model: raise SystemExit(f"Checkpoint architecture is {data.get('architecture')}, not {a.model}")
data.update({"thresholds":{"top1_high":TOP1_HIGH,"high_risk_sum":HIGH_RISK_SUM,"uncertain_max":UNCERTAIN_MAX},"risk_mapping":{"high":sorted(HIGH_RISK)},"dataset":"synthetic demo" if data.get("synthetic") else "HAM10000"})
 meta.write_text(json.dumps(data,indent=2));print(f"Export ready: {src}")
if __name__=="__main__":main()
