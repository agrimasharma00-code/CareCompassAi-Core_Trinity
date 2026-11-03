"""Train the open-vocabulary RxRead CNN + BiLSTM + CTC recognizer.

The tool intentionally exits with a useful message when optional datasets are
absent. It never downloads private data or reports synthetic scores as clinical
performance.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import torch
from PIL import Image
from torch.nn.utils import clip_grad_norm_
from torch.utils.data import DataLoader, Dataset

from ml.rx.charset import build_charset, encode, save_charset
from ml.rx.data import augment_word, load_rows, make_splits
from ml.rx.data_iam import load_iam
from ml.rx.lexicon import build_lexicon, save_lexicon
from ml.rx.model import CRNN, write_summary
from ml.rx.transforms import preprocess_word

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ml" / "data"
ARTIFACTS = ROOT / "ml" / "artifacts" / "rx"
REPORTS = ROOT / "ml" / "reports" / "rx"


class WordDataset(Dataset):
    def __init__(self, rows: pd.DataFrame, charset: list[str], train: bool, width: int, mean: float = .5, std: float = .25):
        self.rows = rows.reset_index(drop=True)
        self.charset, self.train, self.width, self.mean, self.std = charset, train, width, mean, std

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows.iloc[index]
        with Image.open(row.path) as image:
            image = image.convert("L")
            if self.train:
                image = augment_word(image)
            tensor = preprocess_word(image, width=self.width, mean=self.mean, std=self.std)
        target = encode(str(row.text), self.charset)
        return tensor, torch.tensor(target, dtype=torch.long), str(row.text)


def _collate(items):
    images, labels, texts = zip(*items)
    return torch.stack(images), torch.cat(labels), torch.tensor([len(label) for label in labels]), list(texts)


def _iam_splits(root: Path, seed: int) -> dict[str, pd.DataFrame]:
    rows = load_iam(root)
    groups = sorted(rows.writer.unique().tolist())
    random.Random(seed).shuffle(groups)
    n = len(groups)
    train_end, val_end = max(1, int(n * .9)), max(2, int(n * .95))
    buckets = {"train": set(groups[:train_end]), "val": set(groups[train_end:val_end]), "test": set(groups[val_end:])}
    if not buckets["val"] and len(groups) > 1:
        buckets["val"] = {groups[-1]}; buckets["train"].discard(groups[-1])
    return {name: rows[rows.writer.isin(group)].reset_index(drop=True) for name, group in buckets.items()}


def _cer(reference: str, hypothesis: str) -> float:
    previous = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1] / max(1, len(reference))


def _decode(log_probs, charset):
    result = []
    for sequence in log_probs.detach().argmax(2).transpose(0, 1).cpu().tolist():
        chars, previous = [], -1
        for label in sequence:
            if label and label != previous and label < len(charset):
                chars.append(charset[label])
            previous = label
        result.append("".join(chars))
    return result


def _run_epoch(model, loader, optimizer, loss_fn, device, train: bool, scaler, charset):
    model.train(train)
    total_loss, total_chars, total_errors = 0.0, 0, 0
    for images, targets, target_lengths, texts in loader:
        images, targets = images.to(device), targets.to(device)
        if train:
            optimizer.zero_grad(set_to_none=True)
        with torch.set_grad_enabled(train):
            with torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
                output = model(images)
                input_lengths = torch.full((images.shape[0],), output.shape[0], dtype=torch.long, device="cpu")
                loss = loss_fn(output, targets, input_lengths, target_lengths)
            if train:
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                clip_grad_norm_(model.parameters(), 5.0)
                scaler.step(optimizer); scaler.update()
        predictions = _decode(output, charset)
        for truth, prediction in zip(texts, predictions):
            total_errors += round(_cer(truth.casefold(), prediction.casefold()) * max(1, len(truth)))
            total_chars += max(1, len(truth))
        total_loss += float(loss.detach()) * images.shape[0]
    return total_loss / max(1, len(loader.dataset)), total_errors / max(1, total_chars)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("pretrain", "finetune", "bd_only"), default="bd_only")
    parser.add_argument("--iam-dir", type=Path, default=DATA / "iam")
    parser.add_argument("--bd-dir", type=Path, default=DATA / "rx_bd")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    seed = 42
    random.seed(seed); torch.manual_seed(seed)

    splits: dict[str, pd.DataFrame] = {"train": pd.DataFrame(), "val": pd.DataFrame(), "test": pd.DataFrame()}
    iam_rows = pd.DataFrame()
    if args.stage in {"pretrain", "finetune"}:
        try:
            iam_splits = _iam_splits(args.iam_dir, seed)
            iam_rows = pd.concat(iam_splits.values(), ignore_index=True)
            if args.stage == "pretrain":
                splits = iam_splits
            print(f"IAM writer split: {len(iam_splits['train'])} train, {len(iam_splits['val'])} val, {len(iam_splits['test'])} test words")
        except FileNotFoundError as error:
            if args.stage == "pretrain":
                print(f"Skipping IAM pretraining: {error}"); return
            print(f"IAM unavailable; finetune will start from scratch: {error}")
    if args.stage in {"finetune", "bd_only"}:
        try:
            bd = load_rows(args.bd_dir)
            bd = bd.rename(columns={"brand": "text"})
            bd_splits = make_splits(bd.rename(columns={"text": "brand"}), seed)
            for key, frame in bd_splits.items():
                frame = frame.rename(columns={"brand": "text"})
                splits[key] = frame.reset_index(drop=True)
            print("Prescription BD data loaded.")
        except (FileNotFoundError, ValueError) as error:
            if args.stage == "bd_only":
                print(f"RxRead training skipped: {error}"); return
            print(f"Prescription BD data unavailable: {error}"); return

    train, val = splits["train"], splits["val"]
    if train.empty or val.empty:
        print("Training requires non-empty train and validation splits; add real IAM or prescription data first."); return
    bd_labels = pd.DataFrame()
    try:
        bd_labels = load_rows(args.bd_dir).rename(columns={"brand": "text"})
    except FileNotFoundError:
        if args.stage == "pretrain":
            print("BD labels unavailable while pretraining; a later fine-tune may require a new character set.")
    lexicon = build_lexicon(DATA / "lexicon", bd_rows=bd_labels.rename(columns={"text": "brand"}) if not bd_labels.empty else None)
    all_texts = [*train.text.astype(str).tolist(), *val.text.astype(str).tolist(), *iam_rows.text.astype(str).tolist(), *bd_labels.text.astype(str).tolist(), *[item["name"] for item in lexicon]]
    charset = build_charset(all_texts)
    sample_labels = max(len(encode(text, charset)) for text in [*train.text.astype(str).tolist(), *val.text.astype(str).tolist()])
    width = max(128, min(512, math.ceil(sample_labels * 2 / 32) * 128))
    train_ds, val_ds = WordDataset(train, charset, True, width), WordDataset(val, charset, False, width)
    if args.quick:
        train_ds = torch.utils.data.Subset(train_ds, range(min(128, len(train_ds))))
        val_ds = torch.utils.data.Subset(val_ds, range(min(64, len(val_ds))))
    train_loader = DataLoader(train_ds, batch_size=8 if args.quick else args.batch_size, shuffle=True, num_workers=0, collate_fn=_collate)
    val_loader = DataLoader(val_ds, batch_size=8 if args.quick else args.batch_size, shuffle=False, num_workers=0, collate_fn=_collate)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = CRNN(len(charset), input_width=width).to(device)
    if model.time_steps() < sample_labels * 2:
        raise ValueError(f"Input width {model.input_width} gives {model.time_steps()} CTC steps; longest label needs {sample_labels * 2}. Configure a wider input or use word crops.")
    REPORTS.mkdir(parents=True, exist_ok=True); write_summary(model, str(REPORTS / "architecture.txt"))
    ARTIFACTS.mkdir(parents=True, exist_ok=True); save_charset(charset, ARTIFACTS / "charset.json"); save_lexicon(lexicon, ARTIFACTS / "lexicon.json")
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3 if args.stage == "pretrain" else 3e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", patience=2)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")
    loss_fn = torch.nn.CTCLoss(blank=0, zero_infinity=True)
    checkpoint_path, best_path, best_cer, stale = ARTIFACTS / f"crnn_{args.stage}_last.pt", ARTIFACTS / f"crnn_{args.stage}_best.pt", math.inf, 0
    if args.resume and checkpoint_path.exists():
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        model.load_state_dict(checkpoint["model_state"]); optimizer.load_state_dict(checkpoint["optimizer"])
        best_cer = float(checkpoint.get("val_cer", best_cer))
        print(f"Resumed {checkpoint_path} (best CER {best_cer:.4f})")
    elif args.stage == "finetune" and (ARTIFACTS / "crnn_pretrain_best.pt").exists():
        pretrain = torch.load(ARTIFACTS / "crnn_pretrain_best.pt", map_location="cpu", weights_only=False)
        try:
            model.load_state_dict(pretrain["model_state"])
            print("Initialized fine-tuning from the IAM pretraining checkpoint.")
        except RuntimeError as error:
            print(f"IAM checkpoint shape/charset differs; starting from scratch: {error}")
    epochs = min(args.epochs, 2) if args.quick else args.epochs
    for epoch in range(epochs):
        train_loss, train_cer = _run_epoch(model, train_loader, optimizer, loss_fn, device, True, scaler, charset)
        with torch.no_grad():
            val_loss, val_cer = _run_epoch(model, val_loader, optimizer, loss_fn, device, False, scaler, charset)
        scheduler.step(val_cer)
        checkpoint = {"model_state": model.state_dict(), "optimizer": optimizer.state_dict(), "epoch": epoch + 1, "val_cer": val_cer}
        torch.save(checkpoint, checkpoint_path)
        print(f"epoch {epoch+1}/{epochs}: train_loss={train_loss:.4f} train_cer={train_cer:.4f} val_loss={val_loss:.4f} val_cer={val_cer:.4f}")
        if val_cer < best_cer:
            best_cer, stale = val_cer, 0
            torch.save(checkpoint, best_path)
        else:
            stale += 1
            if stale >= 6: break
    meta = {"model_type": "crnn_ctc", "model_family": "custom_crnn_bilstm_ctc", "num_characters": len(charset), "input_height": 32, "input_width": width, "mean": .5, "std": .25, "dataset": args.stage, "training_date": datetime.now(timezone.utc).isoformat(), "run_mode": "quick" if args.quick else "real_data", "metrics": {"validation_cer": best_cer}}
    (ARTIFACTS / f"crnn_{args.stage}_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Best validation CER {best_cer:.4f}; checkpoint saved under {ARTIFACTS}. Use ml.rx.export_ctc to export it.")


if __name__ == "__main__":
    main()
