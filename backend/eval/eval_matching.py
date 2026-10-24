import sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.loaders import load_dataset
from app.core.matching import match
from app.schemas.care import Location
def main():
 rows=[r for r in load_dataset() if r["response"].get("care_type")];top=jaccard_sum=ndcgs=empty=nonempty=0
 for r in rows:
  req=r["request"];res=r["response"];lang=r.get("detected_language","English");pred=match(res["care_type"],Location(**req["location"]),lang,req["user_input"]);ref=[x["caregiver_id"] for x in res["matched_caregivers"]];got=[x["caregiver_id"] for x in pred]
  if ref:
   nonempty+=1; top+=int(bool(got) and ref[0]==got[0]); overlap=len(set(ref)&set(got)); denom=len(set(ref)|set(got));jaccard_sum+=overlap/denom if denom else 1
   dcg=sum(1/math.log2(i+2) for i,x in enumerate(got[:3]) if x in ref);ideal=sum(1/math.log2(i+2) for i in range(min(len(ref),3)));ndcgs+=dcg/ideal if ideal else 0
  empty+=int(bool(ref)==bool(got))
 print("labelled rows",len(rows));print("exact top-1 (non-empty reference)",top/max(1,nonempty));print("mean Jaccard",jaccard_sum/max(1,nonempty));print("NDCG@3 (non-empty reference)",ndcgs/max(1,nonempty));print("empty/non-empty agreement",empty/len(rows))
if __name__=="__main__":main()
