"""Evaluate a saved skin checkpoint and emit real-run metrics and visual reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import yaml
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, f1_score, roc_auc_score
from torch.utils.data import DataLoader

from ml.common.gradcam import overlay_png
from ml.common.reports import comparison_report, confusion_plot, training_curves
from ml.skin.data import CLASS_NAMES, SkinDataset, discover_rows, make_splits
from ml.skin.models import load_model


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--config",default="ml/configs/skin.yaml"); parser.add_argument("--synthetic",action="store_true"); parser.add_argument("--checkpoint"); args=parser.parse_args()
    cfg=yaml.safe_load(Path(args.config).read_text(encoding="utf-8")); raw=Path("ml/data/skin/synthetic" if args.synthetic else cfg["data_dir"]); rows=discover_rows(raw); splits=make_splits(rows,Path("ml/data/skin/splits")/("synthetic" if args.synthetic else "ham10000"),int(cfg.get("seed",42)))
    checkpoints=list(Path(cfg["artifact_dir"]).glob("*/best_checkpoint.pt")); checkpoint_path=Path(args.checkpoint) if args.checkpoint else (checkpoints[-1] if checkpoints else None)
    if checkpoint_path is None or not checkpoint_path.exists(): raise FileNotFoundError("No skin checkpoint found. Train first with python -m ml.skin.train --synthetic.")
    checkpoint=torch.load(checkpoint_path,map_location="cpu",weights_only=False); classes=checkpoint["class_names"]; model_type=checkpoint["model_type"]; size=int(checkpoint.get("input_size",224)); model=load_model(model_type,len(classes)); model.load_state_dict(checkpoint["state_dict"]); device=torch.device("cuda" if torch.cuda.is_available() else "cpu"); model.to(device).eval()
    ds=SkinDataset(splits["test"],classes,False,size,checkpoint["mean"],checkpoint["std"]); loader=DataLoader(ds,batch_size=32,shuffle=False,num_workers=0); truth=[]; predicted=[]; probs=[]; examples=[]
    with torch.no_grad():
        for images,labels,_ in loader:
            outputs=model(images.to(device)).float().softmax(1).cpu(); truth.extend(labels.tolist()); predicted.extend(outputs.argmax(1).tolist()); probs.extend(outputs.tolist()); examples.extend(images)
    y=np.asarray(truth); pred=np.asarray(predicted); probability=np.asarray(probs); high_indices=[i for i,code in enumerate(classes) if code in {"mel","bcc","akiec"}]; high_mask=np.isin(y,high_indices); high_recall=float(np.isin(pred[high_mask],high_indices).mean()) if high_mask.any() else 0.0
    try: auc=float(roc_auc_score(y,probability,multi_class="ovr",average="macro",labels=list(range(len(classes)))))
    except ValueError: auc=None
    output=Path(cfg["report_dir"])/model_type; output.mkdir(parents=True,exist_ok=True)
    report=classification_report(y,pred,labels=list(range(len(classes))),target_names=[CLASS_NAMES.get(code,code) for code in classes],zero_division=0,output_dict=True)
    (output/"classification_report.txt").write_text(classification_report(y,pred,labels=list(range(len(classes))),target_names=classes,zero_division=0),encoding="utf-8")
    confused=np.asarray([sum(1 for a,b in zip(y,pred) if a==i and b!=i) for i in range(len(classes))]); main_ids=np.argsort(confused)[::-1][:min(15,len(classes))]
    confusion_plot(y,pred,classes,output/"confusion_matrix.png",normalize=True); confusion_plot(y,pred,classes,output/"confusion_matrix_top15.png",indices=main_ids,normalize=True)
    training_curves(checkpoint_path.parent/"training_log.csv",output/"training_curves.png","macro_f1")
    fig,axes=plt.subplots(2,4,figsize=(13,7)); names=list(splits["test"]["dx"])
    for i,ax in enumerate(axes.flat):
        if i>=len(examples): ax.axis("off"); continue
        image=examples[i].clone(); mean=torch.tensor(checkpoint["mean"]).view(3,1,1); std=torch.tensor(checkpoint["std"]).view(3,1,1); image=image*std+mean
        ax.imshow(np.uint8(image.permute(1,2,0).numpy().clip(0,1)*255)); ax.set_title(f"true {classes[y[i]]} / pred {classes[pred[i]]}"); ax.axis("off")
    fig.tight_layout(); fig.savefig(output/"misclassified_samples.png",dpi=140); plt.close(fig)
    # Save hook-based overlays on up to eight test images.
    target_layer="features.3.0.0" if model_type in {"custom","custom_fallback"} else "backbone.features.8" if model_type=="efficientnet_b0" else "backbone.features.12"
    fig,axes=plt.subplots(2,4,figsize=(13,7))
    for i,ax in enumerate(axes.flat):
        if i>=len(examples): ax.axis("off"); continue
        try:
            png=overlay_png(model,examples[i][None].to(device),int(pred[i]),target_layer,lambda tensor:tensor*torch.tensor(checkpoint["std"]).view(3,1,1)+torch.tensor(checkpoint["mean"]).view(3,1,1)); from PIL import Image; import io; ax.imshow(Image.open(io.BytesIO(png))); ax.set_title(f"{classes[pred[i]]} / {classes[y[i]]}"); ax.axis("off")
        except Exception as error: ax.text(.1,.5,f"Grad-CAM unavailable: {error}"); ax.axis("off")
    fig.tight_layout(); fig.savefig(output/"gradcam_samples.png",dpi=140); plt.close(fig)
    metrics={"dataset":"HAM10000" if not args.synthetic else "synthetic blobs","run_mode":checkpoint.get("run_mode","unknown"),"model_type":model_type,"parameters":sum(p.numel() for p in model.parameters()),"training_seconds":(json.loads((checkpoint_path.parent/"train_summary.json").read_text()).get("training_seconds") if (checkpoint_path.parent/"train_summary.json").exists() else None),"accuracy":float(accuracy_score(y,pred)),"balanced_accuracy":float(balanced_accuracy_score(y,pred)),"macro_f1":float(f1_score(y,pred,average="macro",zero_division=0)),"high_risk_recall_mel_bcc_akiec":high_recall,"roc_auc_ovr_macro":auc,"per_class":report}
    (output/"metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8"); comparison_report(Path(cfg["report_dir"]),"Skin CNN"); print(json.dumps({k:v for k,v in metrics.items() if k!="per_class"},indent=2))


if __name__=="__main__": main()
