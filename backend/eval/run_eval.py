import argparse,csv,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.pipeline import run
from app.schemas.care import IntakeRequest,IntakeResponse
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",default="predictions.csv");args=ap.parse_args();src=Path(args.input);items=[];labels=[]
 if src.suffix.lower()==".jsonl":
  for line in src.read_text(encoding="utf-8").splitlines():
   if line.strip():
    row=json.loads(line);items.append(row["request"]);labels.append(row.get("response"))
 else:
  with src.open(encoding="utf-8-sig",newline="") as f:
   for i,r in enumerate(csv.DictReader(f)):
    items.append({"user_input":r.get("user_input",r.get("text","")),"language":"auto","location":{"lat":float(r.get("lat",28.54) or 28.54),"lng":float(r.get("lng",77.27) or 77.27)},"conversation_history":[]});labels.append(r if r.get("care_type") else None)
 out=[];full=[]
 for i,item in enumerate(items):
  pred=IntakeResponse.model_validate(run(IntakeRequest.model_validate(item))).model_dump(mode="json");full.append(pred);out.append({"id":item.get("id",str(i)),"care_type":pred["care_type"],"urgency":pred["urgency"],"red_flags":";".join(pred["red_flags"]),"follow_up_question":pred["follow_up_question"],"matched_caregiver_ids":";".join(m["caregiver_id"] for m in pred["matched_caregivers"]),"top_score":pred["matched_caregivers"][0]["score"] if pred["matched_caregivers"] else ""})
 with Path(args.output).open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fieldnames=list(out[0]) if out else []);w.writeheader();w.writerows(out)
 Path(args.output).with_suffix(".jsonl").write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in full),encoding="utf-8")
 if any(labels):
  from sklearn.metrics import f1_score,recall_score
  valid=[i for i,x in enumerate(labels) if x]; yt=[labels[i].get("care_type") or "followup" for i in valid];yp=[full[i]["care_type"] or "followup" for i in valid]; print("Care type macro-F1 (synthetic dataset; not group split):",f1_score(yt,yp,average="macro",zero_division=0));print("Emergency recall:",recall_score([x=="emergency_112" for x in yt],[x=="emergency_112" for x in yp],zero_division=0));print("Under-triage count:",sum(a=="emergency_112" and b!="emergency_112" for a,b in zip(yt,yp)))
 print(f"Wrote {len(out)} predictions")
if __name__=="__main__":main()
