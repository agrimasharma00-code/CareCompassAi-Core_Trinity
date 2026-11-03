"""IAM word-level handwriting index loader with resilient nested-path search."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PIL import Image


def load_iam(data_dir: str | Path) -> pd.DataFrame:
    root = Path(data_dir)
    manifests = list(root.rglob("words.txt"))
    if not manifests:
        raise FileNotFoundError(f"IAM words.txt was not found under {root}; extract words.tgz and words.txt there.")
    image_index = {path.stem.casefold(): path for path in root.rglob("*.png")}
    rows = []
    for manifest in manifests:
        for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            fields = line.split()
            if len(fields) < 9 or fields[1].casefold() != "ok":
                continue
            word_id = fields[0]
            transcription = " ".join(fields[8:]).strip()
            if not transcription:
                continue
            parts = word_id.split("-")
            expected = manifest.parent / "words" / parts[0] / "-".join(parts[:2]) / f"{word_id}.png"
            image = expected if expected.is_file() else image_index.get(word_id.casefold())
            if image is None or not image.is_file() or image.stat().st_size == 0:
                continue
            try:
                with Image.open(image) as source:
                    source.verify()
            except Exception:
                continue
            rows.append({"path": str(image), "text": transcription, "writer": "-".join(parts[:2]), "word_id": word_id})
    if not rows:
        raise FileNotFoundError(f"IAM manifest found under {root}, but no valid word images were indexed.")
    return pd.DataFrame(rows).drop_duplicates("word_id").reset_index(drop=True)
