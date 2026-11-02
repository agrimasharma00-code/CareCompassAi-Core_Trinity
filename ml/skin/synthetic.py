"""Create clearly synthetic colored lesion-like blobs for pipeline smoke runs."""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFilter

CLASSES = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]


def generate(root: str | Path, per_class: int = 20, seed: int = 42) -> Path:
    random.seed(seed); root = Path(root); root.mkdir(parents=True, exist_ok=True); rows = []
    for code_idx, code in enumerate(CLASSES):
        folder = root / "synthetic_images"; folder.mkdir(exist_ok=True)
        for index in range(per_class):
            image_id = f"synthetic_{code}_{index:03d}"; image = Image.new("RGB", (256, 256), (235, 218, 205)); draw = ImageDraw.Draw(image)
            center = (random.randint(96, 160), random.randint(96, 160)); radius = random.randint(24, 72)
            color = ((40 + code_idx * 22) % 180 + 30, (24 + code_idx * 19) % 130 + 20, (18 + code_idx * 13) % 100 + 15)
            draw.ellipse((center[0]-radius, center[1]-radius, center[0]+radius, center[1]+radius), fill=color)
            for _ in range(random.randint(4, 18)):
                x = center[0] + random.randint(-radius, radius); y = center[1] + random.randint(-radius, radius)
                draw.ellipse((x, y, x+random.randint(2, 8), y+random.randint(2, 8)), fill=(30, 20, 14))
            if random.random() < 0.5: image = image.filter(ImageFilter.GaussianBlur(random.uniform(0.2, 1.4)))
            image.save(folder / f"{image_id}.jpg")
            rows.append({"image_id": image_id, "lesion_id": image_id, "dx": code})
    pd.DataFrame(rows).to_csv(root / "HAM10000_metadata.csv", index=False)
    return root
