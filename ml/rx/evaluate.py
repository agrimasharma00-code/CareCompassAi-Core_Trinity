import json
from pathlib import Path
import csv
def main():
 meta=Path("ml/artifacts/rx/model_meta.json")
 if not meta.exists(): raise SystemExit("No RxRead artifact. Run python -m ml.rx.train --synthetic first.")
 info=json.loads(meta.read_text());root=Path("ml/reports/rx");root.mkdir(parents=True,exist_ok=True)
 (root/"metrics.json").write_text(json.dumps({"status":"synthetic_demo_only" if info.get("synthetic") else "no_independent_metrics","note":"No CER/WER claims are available until a held-out IAM/BD evaluation is run."},indent=2))
 (root/"comparison.md").write_text("No real comparison is available yet. Checkpoint training history is not independent test evidence; do not claim OCR accuracy from it.\n")
 try:
  import matplotlib.pyplot as plt
  log=root/"training_curves.csv"
  rows=list(csv.DictReader(log.open(encoding="utf-8"))) if log.exists() else []
  fig,ax=plt.subplots()
  if rows:
   ax.plot([int(r["epoch"]) for r in rows],[float(r["train_loss"]) for r in rows],label="train loss")
   ax.plot([int(r["epoch"]) for r in rows],[float(r["val_loss"]) for r in rows],label="validation loss")
   ax.legend()
  else:ax.text(.5,.5,"No training history available",ha="center",va="center")
  ax.set(xlabel="Epoch",ylabel="Loss");fig.savefig(root/"training_curves.png",bbox_inches="tight");plt.close(fig)
  for filename,title in (("samples_correct.png","Correct samples require a held-out test set"),("samples_wrong.png","Incorrect samples require a held-out test set"),("cer_by_length.png","CER by length requires a held-out test set"),("saliency_samples.png","Input-gradient saliency requires a trained model and test crops")):
   fig,ax=plt.subplots(figsize=(7,2));ax.axis("off");ax.text(.5,.5,title,ha="center",va="center");fig.savefig(root/filename,bbox_inches="tight");plt.close(fig)
 except ImportError: print("matplotlib is missing; report plots skipped. Install ml/requirements-ml.txt.")
 print("Evaluation status recorded; no fabricated metrics written.")
if __name__=="__main__":main()
