"""Render fake medicine-like word crops; these are not real drug prescriptions."""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SYNTHETIC_NAMES = ["Beklo", "Maxima", "Leptic", "Esoral", "Omastin", "Esonix", "Canazole", "Fixal", "Progut", "Diflu"]


def generate(root: str | Path, per_class: int = 30, seed: int = 42) -> Path:
    random.seed(seed); root = Path(root); words = root / "synthetic_words"; words.mkdir(parents=True, exist_ok=True); rows = []
    try:
        import matplotlib.font_manager as fm
        fonts = [Path(path) for path in fm.findSystemFonts() if path.lower().endswith((".ttf", ".otf"))][:40]
    except Exception: fonts = []
    for label in SYNTHETIC_NAMES:
        for idx in range(per_class):
            image = Image.new("L", (300, 96), 255); draw = ImageDraw.Draw(image)
            try: font = ImageFont.truetype(str(random.choice(fonts)), random.randint(36, 54)) if fonts else ImageFont.load_default()
            except Exception: font = ImageFont.load_default()
            draw.text((random.randint(8, 20), random.randint(5, 28)), label, font=font, fill=random.randint(0, 85), stroke_width=random.choice([0, 0, 1]))
            image = image.rotate(random.uniform(-4, 4), resample=Image.Resampling.BICUBIC, fillcolor=255)
            if random.random() < 0.7: image = image.filter(ImageFilter.GaussianBlur(random.uniform(0, 0.5)))
            filename = f"{label}_{idx:03d}.png"; image.save(words / filename)
            rows.append({"IMAGE": filename, "MEDICINE_NAME": label, "GENERIC_NAME": ""})
    pd.DataFrame(rows).to_csv(root / "synthetic_labels.csv", index=False)
    return root
