"""Small reproducible classifier trainer shared by the skin and Rx pipelines."""

from __future__ import annotations

import csv
import random
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch import nn
from torch.utils.data import DataLoader, WeightedRandomSampler


def set_seed(seed: int) -> None:
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)


def device_for_training() -> torch.device:
    if torch.cuda.is_available(): return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available(): return torch.device("mps")
    print("Warning: no GPU detected; full training may be slow. Use the Colab notebook for real-data training.")
    return torch.device("cpu")


def balanced_sampler(dataset) -> WeightedRandomSampler:
    labels = [dataset[index][1] for index in range(len(dataset))]
    counts = np.bincount(labels); weights = [1.0 / max(1, counts[label]) for label in labels]
    return WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)


def _epoch(model, loader, device, criterion, optimizer=None, scaler=None):
    training = optimizer is not None; model.train(training); total_loss = 0.0; seen = 0; targets=[]; guesses=[]; top3_hits=0
    for images, labels, _names in loader:
        images = images.to(device); labels = labels.to(device)
        if training: optimizer.zero_grad(set_to_none=True)
        with torch.set_grad_enabled(training):
            use_amp = device.type == "cuda"
            with torch.autocast(device_type="cuda", enabled=use_amp): logits = model(images); loss = criterion(logits, labels)
            if training:
                if scaler is not None and device.type == "cuda":
                    scaler.scale(loss).backward(); scaler.unscale_(optimizer); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); scaler.step(optimizer); scaler.update()
                else:
                    loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step()
        batch = labels.size(0); total_loss += float(loss.detach()) * batch; seen += batch
        probs = logits.detach().float().softmax(1); guesses.extend(probs.argmax(1).cpu().tolist()); targets.extend(labels.cpu().tolist())
        top3_hits += int((probs.topk(min(3, probs.shape[1]), 1).indices == labels[:, None]).any(1).sum().item())
    return {"loss": total_loss / max(1, seen), "accuracy": float(np.mean(np.asarray(targets) == np.asarray(guesses))), "top3": top3_hits / max(1, seen), "macro_f1": float(f1_score(targets, guesses, average="macro", zero_division=0))}


def train_model(model, train_ds, val_ds, *, output_dir: str | Path, classes: list[str], config: dict, quick: bool = False, transfer: bool = False):
    output_dir = Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    device = device_for_training(); model.to(device)
    sampler = balanced_sampler(train_ds) if config.get("sampler", "weighted") == "weighted" else None
    train_loader = DataLoader(train_ds, batch_size=int(config.get("batch_size", 32)), shuffle=sampler is None, sampler=sampler, num_workers=0 if quick else int(config.get("workers", 2)))
    val_loader = DataLoader(val_ds, batch_size=int(config.get("batch_size", 32)), shuffle=False, num_workers=0 if quick else int(config.get("workers", 2)))
    criterion = nn.CrossEntropyLoss(label_smoothing=float(config.get("label_smoothing", 0.05)))
    epochs = int(config.get("quick_epochs", 2) if quick else config.get("epochs", 25)); lr = float(config.get("learning_rate", 0.001)); patience = int(config.get("patience", 6))
    history=[]; best=-1.0; stale=0; started=time.time(); checkpoint=output_dir / "best_checkpoint.pt"
    stages = [("head", epochs)]
    if transfer: stages = [("head", max(1, epochs // 4)), ("fine_tune", max(1, epochs - max(1, epochs // 4)))]
    global_epoch=0
    for stage, stage_epochs in stages:
        if transfer:
            for name, parameter in model.named_parameters():
                parameter.requires_grad = stage != "head" or any(key in name for key in ("classifier", "fc"))
            if stage == "fine_tune":
                for name, parameter in model.named_parameters():
                    if any(key in name for key in ("layer3", "layer4", "features.6", "features.7")): parameter.requires_grad = True
        stage_lr = float(config.get("fine_tune_learning_rate", lr)) if stage == "fine_tune" else lr
        optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=stage_lr, weight_decay=0.01)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, stage_epochs)); scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
        for _ in range(stage_epochs):
            global_epoch += 1; train_metrics = _epoch(model, train_loader, device, criterion, optimizer, scaler); val_metrics = _epoch(model, val_loader, device, criterion)
            row={"epoch":global_epoch,"stage":stage,"train_loss":train_metrics["loss"],"val_loss":val_metrics["loss"],"train_accuracy":train_metrics["accuracy"],"val_accuracy":val_metrics["accuracy"],"train_top3":train_metrics["top3"],"val_top3":val_metrics["top3"],"train_macro_f1":train_metrics["macro_f1"],"val_macro_f1":val_metrics["macro_f1"]}; history.append(row); scheduler.step()
            score = val_metrics["macro_f1"] if config.get("early_stop_metric") == "macro_f1" else val_metrics["accuracy"]
            if score > best:
                best=score; stale=0; torch.save({"state_dict":model.state_dict(),"epoch":global_epoch,"best_score":best,"class_names":classes},checkpoint)
            else: stale += 1
            print(f"{stage} epoch {global_epoch}/{epochs}: val accuracy={val_metrics['accuracy']:.3f}, macro-F1={val_metrics['macro_f1']:.3f}")
            if stale >= patience: break
        if stale >= patience: break
    with (output_dir / "training_log.csv").open("w", newline="", encoding="utf-8") as handle:
        writer=csv.DictWriter(handle, fieldnames=list(history[0]) if history else ["epoch"]); writer.writeheader(); writer.writerows(history)
    return {"checkpoint":str(checkpoint),"best_val_score":best,"training_seconds":time.time()-started,"epochs":global_epoch,"device":str(device),"history":history}
