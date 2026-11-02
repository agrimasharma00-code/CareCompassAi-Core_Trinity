"""Evaluate a prescription CNN and generate top-k, class, confusion, and Grad-CAM reports."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import yaml
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report, f1_score
from torch.utils.data import DataLoader

from ml.common.gradcam import overlay_png
from ml.common.reports import comparison_report, confusion_plot, training_curves
from ml.rx.data import RxDataset, load_rows, make_splits
from ml.rx.models import load_model
from ml.rx.synthetic import SYNTHETIC_NAMES


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--config",default="ml/configs/rx.yaml"); parser.add_argument("--synthetic",action="store_true"); parser.add_argument("--checkpoint"); args=parser.parse_args()
    cfg=yaml.safe_load(Path(args.config).read_text(encoding="utf-8")); rows=load_rows("ml/data/rx/synthetic" if args.synthetic else cfg["data_dir"]); splits=make_splits(rows,int(cfg.get("seed",42)))
    candidates=list(Path(cfg["artifact_dir"]).glob("*/best_checkpoint.pt")); checkpoint_path=Path(args.checkpoint) if args.checkpoint else (candidates[-1] if candidates else None)
    if checkpoint_path is None or not checkpoint_path.exists(): raise FileNotFoundError("No prescription checkpoint found. Train first with python -m ml.rx.train --synthetic.")
    checkpoint=torch.load(checkpoint_path,map_location="cpu",weights_only=False); classes=checkpoint["class_names"]; model_type=checkpoint["model_type"]; model=load_model(model_type,len(classes)); model.load_state_dict(checkpoint["state_dict"]); device=torch.device("cuda" if torch.cuda.is_available() else "cpu"); model.to(device).eval()
    ds=RxDataset(splits["test"],classes,False,checkpoint["mean"],checkpoint["std"],checkpoint.get("binarize",False)); loader=DataLoader(ds,batch_size=32,shuffle=False,num_workers=0); truth=[]; predicted=[]; probs=[]; examples=[]
    with torch.no_grad():
        for images,labels,_ in loader:
            output=model(images.to(device)).float().softmax(1).cpu(); truth.extend(labels.tolist()); predicted.extend(output.argmax(1).tolist()); probs.extend(output.tolist()); examples.extend(images)
    y=np.asarray(truth); pred=np.asarray(predicted); probability=np.asarray(probs); output=Path(cfg["report_dir"])/model_type; output.mkdir(parents=True,exist_ok=True)
    report=classification_report(y,pred,labels=list(range(len(classes))),target_names=classes,zero_division=0,output_dict=True); (output/"classification_report.txt").write_text(classification_report(y,pred,labels=list(range(len(classes))),target_names=classes,zero_division=0),encoding="utf-8")
    confusion_plot(y,pred,classes,output/"confusion_matrix.png"); confusion_plot(y,pred,classes,output/"confusion_matrix_top15.png",indices=list(range(min(15,len(classes)))))
    training_curves(checkpoint_path.parent/"training_log.csv",output/"training_curves.png","accuracy")
    fig,axes=plt.subplots(3,4,figsize=(15,9)); wrong=[i for i in range(len(y)) if y[i]!=pred[i]][:12]
    for ax,index in zip(axes.flat,wrong):
        tensor=examples[index]*checkpoint["std"]+checkpoint["mean"]; ax.imshow(tensor[0].numpy(),cmap="gray"); ax.set_title(f"true {classes[y[index]]} / pred {classes[pred[index]]}"); ax.axis("off")
    for ax in list(axes.flat)[len(wrong):]: ax.axis("off")
    fig.tight_layout(); fig.savefig(output/"misclassified_samples.png",dpi=140); plt.close(fig)
    target_layer="block4.0.3" if model_type in {"custom","custom_fallback"} else "backbone.layer4.1.conv2"; fig,axes=plt.subplots(2,4,figsize=(13,7))
    for i,ax in enumerate(axes.flat):
        if i>=len(examples): ax.axis("off"); continue
        try:
            png=overlay_png(model,examples[i][None].to(device),int(pred[i]),target_layer,lambda tensor:tensor*checkpoint["std"]+checkpoint["mean"]); ax.imshow(Image.open(io.BytesIO(png))); ax.set_title(f"{classes[pred[i]]} / {classes[y[i]]}"); ax.axis("off")
        except Exception as error: ax.text(.1,.5,f"Grad-CAM unavailable: {error}"); ax.axis("off")
    fig.tight_layout(); fig.savefig(output/"gradcam_samples.png",dpi=140); plt.close(fig)
    top3=(probability.argsort(axis=1)[:,-min(3,len(classes)):]==y[:,None]).any(axis=1).mean(); metrics={"dataset":"synthetic words" if args.synthetic else "Doctor's Handwritten Prescription BD","run_mode":checkpoint.get("run_mode","unknown"),"model_type":model_type,"parameters":sum(p.numel() for p in model.parameters()),"training_seconds":(json.loads((checkpoint_path.parent/"train_summary.json").read_text()).get("training_seconds") if (checkpoint_path.parent/"train_summary.json").exists() else None),"accuracy":float(accuracy_score(y,pred)),"top3_accuracy":float(top3),"macro_f1":float(f1_score(y,pred,average="macro",zero_division=0)),"per_class":report}
    (output/"metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8"); comparison_report(Path(cfg["report_dir"]),"Prescription CNN"); print(json.dumps({k:v for k,v in metrics.items() if k!="per_class"},indent=2))


if __name__=="__main__": main()
