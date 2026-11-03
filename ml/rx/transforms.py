"""Shared aspect-ratio-preserving preprocessing for RxRead word crops."""

from __future__ import annotations

import numpy as np
import torch
from PIL import Image, ImageOps


def preprocess_word(image: Image.Image, height: int = 32, width: int = 128, mean: float = 0.5, std: float = 0.25) -> torch.Tensor:
    gray = ImageOps.autocontrast(ImageOps.grayscale(ImageOps.exif_transpose(image)))
    scale = min(height / max(gray.height, 1), width / max(gray.width, 1))
    resized = gray.resize((max(1, round(gray.width * scale)), max(1, round(gray.height * scale))), Image.Resampling.LANCZOS)
    canvas = Image.new("L", (width, height), 255)
    canvas.paste(resized, (0, (height - resized.height) // 2))
    array = np.asarray(canvas, dtype=np.float32) / 255.0
    array = (array - mean) / max(std, 1e-6)
    return torch.from_numpy(array.copy()).unsqueeze(0)
