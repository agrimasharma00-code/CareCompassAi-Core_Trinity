"""Select a validation checkpoint and export inference weights plus metadata."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import torch
import yaml

from ml.skin.data import CLASS_NAMES


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--config",default="ml/configs/skin.yaml"); parser.add_argument("--model",choices=["custom","transfer"]); args=parser.parse_args(); cfg=yaml.safe_load(Path(args.config).read_text())
    candidates=[]
    for path in Path(cfg["artifact_dir"]).glob("*/best_checkpoint.pt"):
        item=torch.load(path,map_location="cpu",weights_only=False)
        if args.model and item.get("model_family")!=args.model: continue
        candidates.append((float(item.get("best_score",-1)),path,item))
    if not candidates: raise FileNotFoundError("No trained skin checkpoint found. Run python -m ml.skin.train first.")
    _,source,checkpoint=max(candidates,key=lambda item:item[0]); target=Path(cfg["artifact_dir"]); target.mkdir(parents=True,exist_ok=True); output=target/"model.pt"; shutil.copyfile(source,output)
    metrics_path=Path(cfg["report_dir"])/checkpoint["model_type"]/"metrics.json"; metrics=json.loads(metrics_path.read_text()) if metrics_path.exists() else None
    meta={"model_type":checkpoint["model_type"],"model_family":checkpoint["model_family"],"num_classes":len(checkpoint["class_names"]),"class_codes":checkpoint["class_names"],"class_names":{code:CLASS_NAMES.get(code,code) for code in checkpoint["class_names"]},"input_size":checkpoint["input_size"],"mean":checkpoint["mean"],"std":checkpoint["std"],"confidence_thresholds":{"high_risk_confidence":cfg["high_risk_confidence"],"high_risk_sum":cfg["high_risk_sum"],"uncertain_confidence":cfg["uncertain_confidence"]},"risk_mapping":{"high_risk_classes":["mel","bcc","akiec"]},"training_date":datetime.now(timezone.utc).isoformat(),"dataset":checkpoint["dataset"],"run_mode":checkpoint["run_mode"],"metrics":metrics}
    (target/"model_meta.json").write_text(json.dumps(meta,indent=2),encoding="utf-8"); print(f"Exported {output} and model_meta.json")


if __name__=="__main__": main()
