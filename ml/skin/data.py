"""HAM10000 discovery, lesion-grouped splits, transforms, and dataset summary."""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
from pathlib import Path

import pandas as pd
from PIL import Image, ImageOps
from sklearn.model_selection import StratifiedGroupKFold
from torch.utils.data import Dataset, WeightedRandomSampler
from torchvision import transforms

CLASS_NAMES = {
    "akiec": "Actinic keratoses / intraepithelial carcinoma", "bcc": "Basal cell carcinoma",
    "bkl": "Benign keratosis-like lesion", "df": "Dermatofibroma", "mel": "Melanoma",
    "nv": "Melanocytic nevus (common mole)", "vasc": "Vascular lesion",
}
KAGGLE_SLUG = "kmader/skin-cancer-mnist-ham10000"


def download_dataset(target: Path) -> bool:
    """Use the official Kaggle CLI if credentials exist; otherwise show manual steps."""
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if not kaggle_json.exists() and not (os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY")):
        print("No Kaggle credentials found. Sign in to Kaggle, download HAM10000, unzip it into ml/data/ham10000/, then rerun training.")
        print(f"Kaggle: https://www.kaggle.com/datasets/{KAGGLE_SLUG}")
        print("Expected: HAM10000_metadata.csv and HAM10000_images_part_1/, HAM10000_images_part_2/.")
        return False
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(["kaggle", "datasets", "download", "-d", KAGGLE_SLUG, "-p", str(target), "--unzip"], check=True)
    return True


def discover_rows(data_dir: str | Path) -> pd.DataFrame:
    root = Path(data_dir)
    metadata_paths = list(root.rglob("HAM10000_metadata.csv")) or list(root.rglob("*metadata*.csv"))
    if not metadata_paths:
        raise FileNotFoundError(f"No HAM10000 metadata CSV found under {root}. Expected ml/data/skin/raw/HAM10000_metadata.csv and two image-part folders.")
    metadata = pd.read_csv(metadata_paths[0])
    required = {"image_id", "dx"}
    if not required.issubset({column.lower() for column in metadata.columns}):
        raise ValueError(f"Metadata needs image_id and dx columns; found {list(metadata.columns)}")
    metadata.columns = [column.lower() for column in metadata.columns]
    index = {path.stem: path for path in root.rglob("*") if path.suffix.lower() in {".jpg", ".jpeg", ".png"}}
    metadata["path"] = metadata["image_id"].map(index)
    metadata["lesion_id"] = metadata.get("lesion_id", metadata["image_id"])
    rows = metadata.dropna(subset=["path", "dx"]).copy()
    if rows.empty:
        searched = ", ".join(str(path) for path in root.rglob("*images*")) or str(root)
        raise FileNotFoundError(f"Found no labeled lesion images. Searched {root}; image folders seen: {searched}. Expected HAM10000_images_part_1 and part_2.")
    rows["path"] = rows["path"].map(str)
    return rows


def make_splits(rows: pd.DataFrame, split_dir: str | Path, seed: int = 42) -> dict[str, pd.DataFrame]:
    split_path = Path(split_dir); split_path.mkdir(parents=True, exist_ok=True)
    saved = {name: split_path / f"{name}.csv" for name in ("train", "val", "test")}
    if all(path.exists() for path in saved.values()):
        return {name: pd.read_csv(path) for name, path in saved.items()}
    # Ten stratified group folds approximate a reproducible 70/10/20 split
    # while never placing images from one lesion_id into multiple partitions.
    splitter = StratifiedGroupKFold(n_splits=10, shuffle=True, random_state=seed)
    fold_sets = list(splitter.split(rows, rows["dx"], groups=rows["lesion_id"]))
    assignments: dict[str, list[int]] = {"train": [], "val": [], "test": []}
    for fold_idx, (_, valid_idx) in enumerate(fold_sets):
        label = "train" if fold_idx < 7 else "val" if fold_idx == 7 else "test"
        assignments[label].extend(rows.index[valid_idx].tolist())
    result = {name: rows.loc[indexes].reset_index(drop=True) for name, indexes in assignments.items()}
    for name, frame in result.items(): frame.to_csv(saved[name], index=False)
    return result


class SkinDataset(Dataset):
    def __init__(self, rows: pd.DataFrame, class_codes: list[str], train: bool, size: int = 224, mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)) -> None:
        self.rows = rows.reset_index(drop=True); self.class_to_index = {code: idx for idx, code in enumerate(class_codes)}
        self.transform = transforms.Compose([
            transforms.RandomResizedCrop(size, scale=(0.8, 1.0)) if train else transforms.Compose([transforms.Resize(size), transforms.CenterCrop(size)]),
            *([transforms.RandomHorizontalFlip(), transforms.RandomVerticalFlip(), transforms.RandomRotation(20), transforms.ColorJitter(0.2, 0.2, 0.2, 0.02)] if train else []),
            transforms.ToTensor(), transforms.Normalize(mean, std),
        ])

    def __len__(self) -> int: return len(self.rows)

    def __getitem__(self, index: int):
        row = self.rows.iloc[index]
        with Image.open(row["path"]) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
        return self.transform(image), self.class_to_index[str(row["dx"])], str(row["dx"])


def dataset_summary(splits: dict[str, pd.DataFrame]) -> str:
    all_rows = pd.concat([frame.assign(split=name) for name, frame in splits.items()])
    counts = all_rows.groupby("dx").size()
    lines = [f"Classes: {all_rows['dx'].nunique()}", *(f"{name}: {len(frame)} images" for name, frame in splits.items()), f"Per-class min/max: {counts.min()} / {counts.max()}"]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--download", action="store_true"); parser.add_argument("--data-dir", default="ml/data/ham10000")
    args = parser.parse_args(); target = Path(args.data_dir)
    if args.download:
        download_dataset(target); return
    splits = make_splits(discover_rows(target), "ml/data/skin/splits")
    print(dataset_summary(splits))


if __name__ == "__main__": main()
