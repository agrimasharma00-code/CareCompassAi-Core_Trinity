"""Choose the best validation top-1 checkpoint and export the medicine index."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import torch
import yaml


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--config",default="ml/configs/rx.yaml"); parser.add_argument("--model",choices=["custom","transfer"]); args=parser.parse_args(); cfg=yaml.safe_load(Path(args.config).read_text())
    candidates=[]
    for path in Path(cfg["artifact_dir"]).glob("*/best_checkpoint.pt"):
        item=torch.load(path,map_location="cpu",weights_only=False)
        if args.model and item.get("model_family")!=args.model: continue
        candidates.append((float(item.get("best_score",-1)),path,item))
    if not candidates: raise FileNotFoundError("No trained prescription checkpoint found. Run python -m ml.rx.train first.")
    _,source,checkpoint=max(candidates,key=lambda item:item[0]); target=Path(cfg["artifact_dir"]); target.mkdir(parents=True,exist_ok=True); output=target/"model.pt"; shutil.copyfile(source,output)
    metrics_path=Path(cfg["report_dir"])/checkpoint["model_type"]/"metrics.json"; metrics=json.loads(metrics_path.read_text()) if metrics_path.exists() else None
    classes=checkpoint["class_names"]; generics=checkpoint.get("generic_names",{}); medicines={str(index):{"brand":brand,"generic":generics.get(brand,"")} for index,brand in enumerate(classes)}
    meta={"model_type":checkpoint["model_type"],"model_family":checkpoint["model_family"],"num_classes":len(classes),"class_names":classes,"input_size":[checkpoint["input_height"],checkpoint["input_width"]],"mean":checkpoint["mean"],"std":checkpoint["std"],"binarize":checkpoint["binarize"],"confidence_thresholds":{"high":cfg["confidence_high"],"medium":cfg["confidence_medium"]},"training_date":datetime.now(timezone.utc).isoformat(),"dataset":checkpoint["dataset"],"run_mode":checkpoint["run_mode"],"metrics":metrics}
    (target/"model_meta.json").write_text(json.dumps(meta,indent=2),encoding="utf-8"); (target/"medicines.json").write_text(json.dumps(medicines,indent=2),encoding="utf-8"); print(f"Exported {output}, model_meta.json, and medicines.json")


if __name__=="__main__": main()
