import json

def write_metrics(path, metrics, *, real_evaluation=False):
    if not real_evaluation and any(key in metrics for key in ("accuracy","macro_f1","cer","wer")):
        raise ValueError("Do not write evaluation metrics without an independent real evaluation.")
    with open(path,"w",encoding="utf-8") as handle: json.dump(metrics,handle,indent=2)
