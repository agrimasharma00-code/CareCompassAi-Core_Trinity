import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.loaders import load_dataset
OUT=Path(__file__).resolve().parents[1]/"data"/"augment"/"paraphrases.jsonl"
TEMPLATES=["please {text}","urgent: {text}","{text} please help", "ghar par {text}","mummy ke liye {text}","papa ko {text}","{text} chahiye", "can someone help, {text}"]
def main():
 seen=set(); rows=[]
 for row in load_dataset():
  text=row["request"]["user_input"].strip(); key=text.lower()
  if key in seen:continue
  seen.add(key); care=row["response"]["care_type"] or "followup"
  for template in TEMPLATES: rows.append({"text":template.format(text=text),"care_type":care,"source_text":text})
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in rows),encoding="utf-8");print(f"Wrote {len(rows)} paraphrases from {len(seen)} unique source texts")
if __name__=="__main__":main()
