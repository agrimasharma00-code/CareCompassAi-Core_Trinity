import math,re
from app.config import get_settings
from app.core.loaders import load_caregivers
def distance_km(a,b,c,d):
 r=6371; p1,p2=math.radians(a),math.radians(c);dp=math.radians(c-a);dl=math.radians(d-b);x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return 2*r*math.asin(math.sqrt(x))
def required_skill(text):
 t=text.lower();
 for words,skill in [(("injection","insulin"),"injection_im"),(("dressing","patti","wound"),"wound_dressing"),(("catheter",),"catheter_care"),(("iv",),"injection_iv"),(("sample","blood test","cbc"),"sample_collection")]:
  if any(w in t for w in words):return skill
 return None
def match(care_type,location,lang,text):
 if care_type in (None,"emergency_112"):return []
 role={"paramedic_home_visit":"medic","home_nursing":"medic","lab_test_home":"phlebotomist","teleconsultation":"doctor"}.get(care_type); skill=required_skill(text); results=[]
 for c in load_caregivers():
  if c["active"].lower()!="true" or c["role"]!=role:continue
  languages=c["languages"].split(";"); desired="English" if lang=="English" else "Hindi"
  if desired not in languages:continue
  virtual=role=="doctor"; km=0 if virtual else distance_km(location.lat,location.lng,float(c["base_lat"]),float(c["base_lng"]))
  radius=float(c["max_radius_km"]);
  if not virtual and km>radius:continue
  skills=c["skills"].split(";");
  if skill and skill not in skills:continue
  prox=1 if virtual else max(0,min(1,1-km/radius)); skill_score=1 if skill and skill in skills else .5
  score=round(.35+.30*prox+.20*skill_score+.15*(float(c["rating"])/5),2)
  free=f"free {c['free_from']}–{c['free_until']}";reason=f"{desired}-speaking, {free}, ★{float(c['rating']):.1f}" if virtual else f"{desired}-speaking, {km:.1f} km away, {free}"
  results.append({"caregiver_id":c["caregiver_id"],"score":score,"reason":reason})
 return sorted(results,key=lambda x:(-x["score"],x["caregiver_id"]))[:get_settings().match_top_k]
