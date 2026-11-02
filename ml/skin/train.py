"""CLI for reproducible HAM10000 custom and transfer CNN training."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd
import torch
import yaml
from torch.utils.data import Subset

from ml.common.training import set_seed, train_model
from ml.skin.data import CLASS_NAMES, SkinDataset, dataset_summary, discover_rows, make_splits
from ml.skin.models import build_model, write_summary
from ml.skin.synthetic import generate

logging.basicConfig(level=logging.INFO)


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--config",default="ml/configs/skin.yaml"); parser.add_argument("--model",choices=["custom","transfer"],default="custom"); parser.add_argument("--quick",action="store_true"); parser.add_argument("--synthetic",action="store_true"); parser.add_argument("--data-dir")
    args=parser.parse_args(); config=yaml.safe_load(Path(args.config).read_text(encoding="utf-8")); data_dir=Path(args.data_dir or config["data_dir"]); seed=int(config.get("seed",42)); set_seed(seed)
    if args.synthetic: generate("ml/data/skin/synthetic",per_class=20,seed=seed); data_dir=Path("ml/data/skin/synthetic")
    rows=discover_rows(data_dir); splits=make_splits(rows,Path("ml/data/skin/splits")/("synthetic" if args.synthetic else "ham10000"),seed); print(dataset_summary(splits))
    class_codes=[code for code in config.get("classes", CLASS_NAMES) if code in set(rows["dx"])]; size=128 if args.quick else int(config.get("input_size",224))
    train_ds=SkinDataset(splits["train"],class_codes,True,size); val_ds=SkinDataset(splits["val"],class_codes,False,size)
    if args.quick:
        train_ds=Subset(train_ds,list(range(min(len(train_ds),max(16,int(len(train_ds)*.1)))))); val_ds=Subset(val_ds,list(range(min(len(val_ds),64))))
    model,model_type=build_model(args.model,len(class_codes)); write_summary(model,"ml/reports/skin/architecture.txt",size)
    result=train_model(model,train_ds,val_ds,output_dir=Path(config["artifact_dir"])/model_type,classes=class_codes,config={**config,"input_size":size},quick=args.quick,transfer=args.model=="transfer")
    checkpoint=torch.load(result["checkpoint"],map_location="cpu",weights_only=False); checkpoint.update({"model_type":model_type,"model_family":args.model,"input_size":size,"mean":[0.485,0.456,0.406],"std":[0.229,0.224,0.225],"dataset":"synthetic" if args.synthetic else "HAM10000","run_mode":"synthetic" if args.synthetic else "quick" if args.quick else "full"}); torch.save(checkpoint,result["checkpoint"])
    (Path(config["artifact_dir"])/model_type/"train_summary.json").write_text(json.dumps({key:value for key,value in result.items() if key!="history"},indent=2),encoding="utf-8")
    print(f"Saved best checkpoint to {result['checkpoint']}")


if __name__=="__main__": main()
