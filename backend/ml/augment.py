import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.loaders import load_dataset
OUT=Path(__file__).resolve().parents[1]/"data"/"augment"/"paraphrases.jsonl"
TEMPLATES=["please {text}","urgent: {text}","{text} please help", "ghar par {text}","mummy ke liye {text}","papa ko {text}","{text} chahiye", "can someone help, {text}"]
MILD_PARAPHRASES={
 "headache":[("I have a mild headache","teleconsultation"),("My head has been aching today","teleconsultation"),("Mere sir mein halka dard hai","teleconsultation"),("Sir dard ho raha hai","teleconsultation"),("मेरे सिर में हल्का दर्द है","teleconsultation"),("सिर दर्द है, डॉक्टर से बात करनी है","teleconsultation"),("Please come home to check my headache","paramedic_home_visit"),("सिर दर्द है, घर पर देखने आ सकते हैं?","paramedic_home_visit")],
 "stomach_ache":[("I have a mild stomach ache","teleconsultation"),("My stomach hurts a little","teleconsultation"),("Pet mein halka dard hai","teleconsultation"),("Mere pet mein thoda dard hai","teleconsultation"),("पेट में हल्का दर्द है","teleconsultation"),("पेट में थोड़ा दर्द हो रहा है","teleconsultation"),("Please come home to check my stomach pain","paramedic_home_visit"),("पेट दर्द है, घर पर जांच कर दें","paramedic_home_visit")],
 "cold":[("I have a mild cold","teleconsultation"),("I have a runny nose and cold","teleconsultation"),("Mujhe halki sardi hai","teleconsultation"),("Mujhe zukham ho gaya hai","teleconsultation"),("मुझे हल्की सर्दी है","teleconsultation"),("जुकाम है, डॉक्टर से बात करनी है","teleconsultation"),("Please come home to check my cold","paramedic_home_visit"),("सर्दी है, घर पर देखने आ सकते हैं?","paramedic_home_visit")],
 "body_ache":[("I have mild body aches","teleconsultation"),("My body feels achy today","teleconsultation"),("Badan mein halka dard hai","teleconsultation"),("Mere shareer mein dard ho raha hai","teleconsultation"),("मेरे बदन में हल्का दर्द है","teleconsultation"),("शरीर में दर्द है, डॉक्टर से सलाह चाहिए","teleconsultation"),("Please come home to check my body aches","paramedic_home_visit"),("बदन दर्द है, घर पर देखने आ सकते हैं?","paramedic_home_visit")]
}
def main():
 seen=set(); rows=[]
 for row in load_dataset():
  text=row["request"]["user_input"].strip(); key=text.lower()
  if key in seen:continue
  seen.add(key); care=row["response"]["care_type"] or "followup"
  for template in TEMPLATES: rows.append({"text":template.format(text=text),"care_type":care,"source_text":text})
 # Curated mild-symptom examples are tied to an existing labeled source group.
 # The trainer includes them only when that carrier group is in the fold's train split.
 carriers={}
 for row in load_dataset():
  care=row["response"]["care_type"] or "followup"
  if care in {"teleconsultation","paramedic_home_visit"}:carriers.setdefault(care,row["request"]["user_input"].strip())
 for variants in MILD_PARAPHRASES.values():
  for text,care in variants:rows.append({"text":text,"care_type":care,"source_text":carriers[care]})
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in rows),encoding="utf-8");print(f"Wrote {len(rows)} paraphrases from {len(seen)} unique source texts")
if __name__=="__main__":main()
