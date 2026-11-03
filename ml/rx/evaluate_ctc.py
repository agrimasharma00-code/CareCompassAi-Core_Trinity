"""Evaluate exported or staged RxRead CRNN checkpoints on BD held-out words."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from ml.rx.charset import load_charset
from ml.rx.data import load_rows, make_splits
from ml.rx.decode import best_path, beam_search, lexicon_correct
from ml.rx.model import CRNN
from ml.rx.train_ctc import WordDataset, _collate, _cer

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "ml" / "artifacts" / "rx"


def _word_errors(truth: str, guess: str) -> tuple[int, int]:
    left, right = truth.split(), guess.split()
    dp = list(range(len(right) + 1))
    for i, token in enumerate(left, 1):
        current = [i]
        for j, other in enumerate(right, 1):
            current.append(min(current[-1] + 1, dp[j] + 1, dp[j - 1] + (token.casefold() != other.casefold())))
        dp = current
    return dp[-1], max(1, len(left))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "ml" / "data" / "rx_bd")
    parser.add_argument("--checkpoint", type=Path, default=ARTIFACTS / "model.pt")
    parser.add_argument("--meta", type=Path, default=ARTIFACTS / "model_meta.json")
    args = parser.parse_args()
    try:
        rows = load_rows(args.data_dir)
    except FileNotFoundError as error:
        print(f"RxRead evaluation skipped: {error}")
        return
    if not args.checkpoint.is_file() or not args.meta.is_file() or not (ARTIFACTS / "charset.json").is_file():
        print("RxRead evaluation skipped: export a trained CRNN first with python -m ml.rx.export_ctc.")
        return
    meta = json.loads(args.meta.read_text(encoding="utf-8"))
    charset = load_charset(ARTIFACTS / "charset.json")
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    model = CRNN(int(meta["num_characters"]), int(meta.get("input_height", 32)), int(meta.get("input_width", 128)))
    model.load_state_dict(checkpoint["model_state"]); model.eval()
    test = make_splits(rows, 42)["test"].rename(columns={"brand": "text"})
    dataset = WordDataset(test, charset, False, int(meta.get("input_width", 128)), float(meta.get("mean", .5)), float(meta.get("std", .25)))
    loader = DataLoader(dataset, batch_size=16, shuffle=False, num_workers=0, collate_fn=_collate)
    lexicon_path = ARTIFACTS / "lexicon.json"
    lexicon = json.loads(lexicon_path.read_text(encoding="utf-8")) if lexicon_path.exists() else []
    chars = words = top1 = top3 = samples = 0
    char_total = word_total = 0
    with torch.inference_mode():
        for images, _, _, truths in loader:
            output = model(images)
            for index, truth in enumerate(truths):
                greedy, _ = best_path(output[:, index], charset)
                beam = beam_search(output[:, index], charset, beam_width=10)
                beam_text = beam[0][0] if beam else ""
                chars += round(_cer(truth.casefold(), greedy.casefold()) * max(1, len(truth)))
                char_total += max(1, len(truth))
                err, count = _word_errors(truth, beam_text); words += err; word_total += count
                matches = lexicon_correct(beam_text, lexicon, k=3)
                candidate_names = [item["name"].casefold() for item in matches]
                top1 += bool(candidate_names and candidate_names[0] == truth.casefold())
                top3 += truth.casefold() in candidate_names
                samples += 1
    result = {"dataset": "Doctor's Handwritten Prescription BD", "run_mode": meta.get("run_mode", "unknown"), "sample_count": samples, "greedy_cer": chars / max(1, char_total), "beam_wer": words / max(1, word_total), "lexicon_top1_accuracy": top1 / max(1, samples), "lexicon_top3_accuracy": top3 / max(1, samples)}
    report = ROOT / "ml" / "reports" / "rx"; report.mkdir(parents=True, exist_ok=True)
    (report / "ctc_metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
