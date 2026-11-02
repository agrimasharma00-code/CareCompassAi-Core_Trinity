from pathlib import Path
import json
def main():
 root=Path("ml/artifacts/rx")
 for name in ("model.pt","model_meta.json","charset.json","lexicon.json"):
  if not (root/name).exists(): raise SystemExit(f"Missing {root/name}; run python -m ml.rx.train --synthetic first")
 print(f"RxRead export ready: {root}")
if __name__=="__main__":main()
