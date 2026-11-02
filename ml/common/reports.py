"""Plot/report helpers shared by both image experiments."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def confusion_plot(y_true, y_pred, labels, path: Path, indices=None, normalize=False):
    from sklearn.metrics import confusion_matrix
    ids=list(range(len(labels))) if indices is None else indices
    matrix=confusion_matrix(y_true,y_pred,labels=ids,normalize="true" if normalize else None)
    fig,ax=plt.subplots(figsize=(max(7,len(ids)*.45),max(6,len(ids)*.42)))
    sns.heatmap(matrix,annot=len(ids)<=10,fmt=".2f" if normalize else "d",xticklabels=[labels[i] for i in ids],yticklabels=[labels[i] for i in ids],cmap="Blues",ax=ax)
    ax.set_xlabel("Predicted"); ax.set_ylabel("True"); fig.tight_layout(); fig.savefig(path,dpi=150); plt.close(fig)


def training_curves(log_path: Path, output: Path, metric: str):
    if not log_path.exists(): return
    data=pd.read_csv(log_path)
    if data.empty: return
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    axes[0].plot(data.epoch,data.train_loss,label="train"); axes[0].plot(data.epoch,data.val_loss,label="validation"); axes[0].set_title("Loss"); axes[0].legend()
    axes[1].plot(data.epoch,data[f"train_{metric}"],label="train"); axes[1].plot(data.epoch,data[f"val_{metric}"],label="validation"); axes[1].set_title(metric); axes[1].legend()
    fig.tight_layout(); fig.savefig(output,dpi=150); plt.close(fig)


def comparison_report(root: Path, kind: str):
    entries=[]
    for path in root.glob("*/metrics.json"):
        metrics=json.loads(path.read_text(encoding="utf-8")); entries.append((path.parent.name,metrics))
    if len(entries)<2:return
    columns=["model","run mode","params","training seconds","accuracy","top-3","macro-F1"]
    rows=[]
    for name,m in entries:
        rows.append([name,m.get("run_mode","unknown"),m.get("parameters","n/a"),m.get("training_seconds","n/a"),m.get("accuracy","n/a"),m.get("top3_accuracy","n/a"),m.get("macro_f1","n/a")])
    (root/"comparison.md").write_text(f"# {kind} model comparison\n\nOnly evaluated runs are included; synthetic/quick runs are labelled.\n\n| " + " | ".join(columns) + " |\n|" + "|".join(["---"]*len(columns)) + "|\n" + "\n".join("| " + " | ".join(map(str,row)) + " |" for row in rows) + "\n",encoding="utf-8")
