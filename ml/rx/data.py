"""Auto-detect prescription word images, labels, official splits, and shared preprocessing."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset
from torchvision import transforms

KAGGLE_SLUG = "mamun1113/doctors-handwritten-prescription-bd-dataset"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def download_dataset(target: Path) -> bool:
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if not kaggle_json.exists() and not (os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY")):
        print("No Kaggle credentials found. Download the Doctor's Handwritten Prescription BD dataset, unzip it under ml/data/rx/raw/, then rerun training.")
        print(f"Kaggle: https://www.kaggle.com/datasets/{KAGGLE_SLUG}")
        print("Alternative: https://data.mendeley.com/datasets/zjjtptvn6f. Expected: image folders and a CSV/XLSX with image and MEDICINE_NAME labels.")
        return False
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(["kaggle", "datasets", "download", "-d", KAGGLE_SLUG, "-p", str(target), "--unzip"], check=True)
    return True


def _image_index(root: Path) -> dict[str, Path]:
    return {image.name.casefold(): image for image in root.rglob("*") if image.suffix.lower() in IMAGE_EXTENSIONS}


def _column(columns, predicate):
    return next((column for column in columns if predicate(str(column).strip().casefold())), None)


def load_rows(data_dir: str | Path) -> pd.DataFrame:
    root = Path(data_dir); images = _image_index(root); records = []
    for label_file in [*root.rglob("*.csv"), *root.rglob("*.xlsx"), *root.rglob("*.xls")]:
        try: table = pd.read_excel(label_file) if label_file.suffix.lower() in {".xls", ".xlsx"} else pd.read_csv(label_file)
        except Exception: continue
        image_col = _column(table.columns, lambda value: any(str(cell).strip().lower().endswith(tuple(IMAGE_EXTENSIONS)) for cell in table[value].dropna().head(15)))
        label_col = _column(table.columns, lambda value: value == "medicine_name") or _column(table.columns, lambda value: "medicine" in value and "generic" not in value)
        if image_col is None or label_col is None: continue
        generic_col = _column(table.columns, lambda value: "generic" in value)
        split_hint = (label_file.parent.name + " " + label_file.stem).casefold()
        split = "train" if "train" in split_hint else "val" if "valid" in split_hint or "val" in split_hint else "test" if "test" in split_hint else ""
        for _, row in table.iterrows():
            filename = Path(str(row[image_col])).name
            image_path = images.get(filename.casefold())
            if image_path is None or pd.isna(row[label_col]): continue
            records.append({"path": str(image_path), "brand": str(row[label_col]).strip(), "generic": str(row[generic_col]).strip() if generic_col and pd.notna(row[generic_col]) else "", "split": split})
    rows = pd.DataFrame(records).drop_duplicates(subset="path") if records else pd.DataFrame()
    if rows.empty:
        raise FileNotFoundError(f"Found no labeled medicine-word images. Searched recursively under {root}. Expected image files plus CSV/XLSX columns IMAGE and MEDICINE_NAME.")
    return rows


def make_splits(rows: pd.DataFrame, seed: int = 42) -> dict[str, pd.DataFrame]:
    labeled = rows[rows["split"].astype(bool)]
    if len(labeled) and {"train", "test"}.issubset(set(labeled["split"])):
        split = {"train": rows[rows["split"] == "train"].copy(), "val": rows[rows["split"].isin(["val", "valid"])].copy(), "test": rows[rows["split"] == "test"].copy()}
        if split["val"].empty:
            split["train"], split["val"] = train_test_split(split["train"], test_size=0.15, random_state=seed, stratify=split["train"]["brand"])
        return split
    train, rest = train_test_split(rows, test_size=0.30, random_state=seed, stratify=rows["brand"])
    val, test = train_test_split(rest, test_size=0.50, random_state=seed, stratify=rest["brand"])
    return {"train": train.reset_index(drop=True), "val": val.reset_index(drop=True), "test": test.reset_index(drop=True)}


def canonical_word_image(image: Image.Image, binarize: bool = False, height: int = 64, width: int = 256) -> Image.Image:
    image = ImageOps.autocontrast(ImageOps.grayscale(ImageOps.exif_transpose(image)))
    if binarize:
        image = image.point(lambda value: 255 if value > 160 else 0)
    ratio = height / image.height
    resized_width = max(1, min(width, round(image.width * ratio)))
    image = image.resize((resized_width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("L", (width, height), 255)
    canvas.paste(image, (0, 0))
    return canvas


def preprocess_word(image: Image.Image, mean: float = 0.5, std: float = 0.25, binarize: bool = False, height: int = 64, width: int = 256) -> torch.Tensor:
    """One normalization/resizing path used by both training and inference."""
    canvas = canonical_word_image(image,binarize,height,width)
    tensor = transforms.ToTensor()(canvas)
    return transforms.Normalize((mean,), (max(std, 1e-5),))(tensor)


def compute_mean_std(rows: pd.DataFrame, binarize: bool = False) -> tuple[float,float]:
    total=0.0; squared=0.0; pixels=0
    for path in rows["path"]:
        with Image.open(path) as source: tensor=transforms.ToTensor()(canonical_word_image(source,binarize))
        total+=float(tensor.sum()); squared+=float((tensor*tensor).sum()); pixels+=tensor.numel()
    mean=total/max(1,pixels); std=max(1e-5,(squared/max(1,pixels)-mean*mean)**0.5)
    return mean,std


def augment_word(image: Image.Image) -> Image.Image:
    """Text-safe train-only affine, light elastic-like warp, blur and stroke noise."""
    import random
    image = ImageOps.grayscale(image)
    angle = random.uniform(-5, 5); shear = random.uniform(-0.12, 0.12)
    image = image.rotate(angle, resample=Image.Resampling.BILINEAR, fillcolor=255)
    image = image.transform(image.size, Image.Transform.AFFINE, (1, shear, random.uniform(-4, 4), random.uniform(-2, 2), 1, 0), resample=Image.Resampling.BILINEAR, fillcolor=255)
    image = ImageEnhance.Contrast(image).enhance(random.uniform(0.8, 1.2))
    image = ImageEnhance.Brightness(image).enhance(random.uniform(0.85, 1.15))
    if random.random() < 0.2: image = image.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.2, 0.8)))
    if random.random() < 0.2:
        array = np.asarray(image).copy(); kernel = np.ones((2, 2), np.uint8)
        try:
            import cv2
            array = cv2.erode(array, kernel, iterations=1) if random.random() < 0.5 else cv2.dilate(array, kernel, iterations=1)
            image = Image.fromarray(array)
        except ImportError: pass
    return image


class RxDataset(Dataset):
    def __init__(self, rows: pd.DataFrame, classes: list[str], train: bool, mean: float = 0.5, std: float = 0.25, binarize: bool = False) -> None:
        self.rows = rows.reset_index(drop=True); self.classes = classes; self.indices = {name: i for i, name in enumerate(classes)}
        self.train = train; self.mean = mean; self.std = std; self.binarize = binarize

    def __len__(self): return len(self.rows)

    def __getitem__(self, index):
        row = self.rows.iloc[index]
        with Image.open(row["path"]) as source: image = ImageOps.exif_transpose(source).convert("L")
        if self.train: image = augment_word(image)
        return preprocess_word(image, self.mean, self.std, self.binarize), self.indices[str(row["brand"])], str(row["brand"])


def dataset_summary(splits: dict[str, pd.DataFrame]) -> str:
    all_rows = pd.concat([frame.assign(which=name) for name, frame in splits.items()]); counts = all_rows.groupby("brand").size()
    return f"Classes: {all_rows['brand'].nunique()}\n" + "\n".join(f"{name}: {len(frame)} images" for name, frame in splits.items()) + f"\nPer-class min/max: {counts.min()} / {counts.max()}"


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--download", action="store_true"); parser.add_argument("--data-dir", default="ml/data/rx/raw")
    args = parser.parse_args(); target = Path(args.data_dir)
    if args.download: download_dataset(target); return
    print(dataset_summary(make_splits(load_rows(target))))


if __name__ == "__main__": main()
