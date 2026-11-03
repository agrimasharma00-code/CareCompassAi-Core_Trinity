"""Export the best trained CRNN checkpoint for ml_service."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "ml" / "artifacts" / "rx"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()
    checkpoint = args.checkpoint or next((path for path in (ARTIFACTS / "crnn_finetune_best.pt", ARTIFACTS / "crnn_bd_only_best.pt") if path.is_file()), None)
    if checkpoint is None:
        raise FileNotFoundError(f"No BD-trained RxRead checkpoint found in {ARTIFACTS}. Train finetune or bd_only first.")
    metadata = args.metadata or checkpoint.with_name(checkpoint.name.replace("_best.pt", "_meta.json"))
    for required in (checkpoint, metadata, ARTIFACTS / "charset.json"):
        if not required.is_file():
            raise FileNotFoundError(f"Missing {required}. Train RxRead first with python -m ml.rx.train_ctc.")
    meta = json.loads(metadata.read_text(encoding="utf-8"))
    if not meta.get("metrics"):
        raise ValueError("Checkpoint metadata has no recorded validation metrics; refusing an unverified export.")
    shutil.copyfile(checkpoint, ARTIFACTS / "model.pt")
    meta["exported_from"] = checkpoint.name
    (ARTIFACTS / "model_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if not (ARTIFACTS / "lexicon.json").exists():
        (ARTIFACTS / "lexicon.json").write_text("[]", encoding="utf-8")
    print(f"Exported CRNN model, metadata, charset, and lexicon to {ARTIFACTS}")


if __name__ == "__main__":
    main()
