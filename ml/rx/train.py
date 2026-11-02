"""CLI for custom RxCNN and ResNet18 medicine-word classification."""

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
from ml.rx.data import RxDataset, compute_mean_std, dataset_summary, load_rows, make_splits
from ml.rx.models import build_model, write_summary
from ml.rx.synthetic import SYNTHETIC_NAMES, generate

logging.basicConfig(level=logging.INFO)


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--config",default="ml/configs/rx.yaml"); parser.add_argument("--model",choices=["custom","transfer"],default="custom"); parser.add_argument("--quick",action="store_true"); parser.add_argument("--synthetic",action="store_true"); parser.add_argument("--data-dir")
    args=parser.parse_args(); config=yaml.safe_load(Path(args.config).read_text(encoding="utf-8")); data_dir=Path(args.data_dir or config["data_dir"]); seed=int(config.get("seed",42)); set_seed(seed)
    if args.synthetic: generate("ml/data/rx/synthetic",per_class=30,seed=seed); data_dir=Path("ml/data/rx/synthetic")
    rows=load_rows(data_dir); splits=make_splits(rows,seed); print(dataset_summary(splits)); classes=SYNTHETIC_NAMES if args.synthetic else sorted(rows["brand"].unique().tolist())
    mean,std=compute_mean_std(splits["train"],bool(config.get("binarize",False)))
    train_ds=RxDataset(splits["train"],classes,True,mean,std,binarize=bool(config.get("binarize",False))); val_ds=RxDataset(splits["val"],classes,False,mean,std,binarize=bool(config.get("binarize",False)))
    if args.quick:
        train_ds=Subset(train_ds,list(range(min(len(train_ds),max(32,int(len(train_ds)*.1)))))); val_ds=Subset(val_ds,list(range(min(len(val_ds),128))))
    model,model_type=build_model(args.model,len(classes)); write_summary(model,"ml/reports/rx/architecture.txt")
    result=train_model(model,train_ds,val_ds,output_dir=Path(config["artifact_dir"])/model_type,classes=classes,config=config,quick=args.quick,transfer=args.model=="transfer")
    checkpoint=torch.load(result["checkpoint"],map_location="cpu",weights_only=False); checkpoint.update({"model_type":model_type,"model_family":args.model,"input_height":64,"input_width":256,"mean":mean,"std":std,"binarize":bool(config.get("binarize",False)),"generic_names":dict(zip(classes,rows.groupby("brand")["generic"].first().reindex(classes).fillna("").tolist())),"dataset":"synthetic" if args.synthetic else "Doctor's Handwritten Prescription BD","run_mode":"synthetic" if args.synthetic else "quick" if args.quick else "full"}); torch.save(checkpoint,result["checkpoint"])
    (Path(config["artifact_dir"])/model_type/"train_summary.json").write_text(json.dumps({key:value for key,value in result.items() if key!="history"},indent=2),encoding="utf-8")
    print(f"Saved best checkpoint to {result['checkpoint']}")


if __name__=="__main__": main()
