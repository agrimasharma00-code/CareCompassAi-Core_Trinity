import re
CARE_TYPES=["paramedic_home_visit","home_nursing","lab_test_home","teleconsultation","emergency_112","followup"]
URGENCY={"paramedic_home_visit":"same_day","home_nursing":"same_day","lab_test_home":"scheduled","teleconsultation":"same_day","emergency_112":"emergency"}
NURSING_RE=r"injection|insulin|dressing|patti|bedsore|\biv\b|catheter|nursing|इंजेक्शन|ड्रेसिंग"
LAB_RE=r"test|cbc|thyroid|sugar test|full body|sample|collection|लैब|जांच|टेस्ट|नमूना"
HOME_RE=r"ghar pe dikhana|ghar aa|ghar pe check|home visit|visit at home|घर पर दिखाना|घर आ|someone come home to check"
SYMPTOM_RE=r"bukhar|fever|khansi|cough|kamzori|kamzor|weak|not eating|khana nahi|bp|sugar check|बुखार|खांसी|कमज़ोरी|कमजोरी|खाना नहीं"
TELE_RE=r"consult|second opinion|reports|doctor se baat|doctor se consult|acidity|virtual doctor|online doctor|डॉक्टर से बात|डॉक्टर से सलाह"
DOCTOR_RE=r"\bdoctor\b|डॉक्टर"
GENERAL_HOME_RE=r"bp|sugar check|weak|kamzor|bukhar|khansi|home checkup|ghar pe dikhana|fever|cough|कमज़ोरी|बुखार|खांसी"

def keyword_rule(text):
    t=text.lower()
    # Specific service requests take precedence over general home assessment.
    if re.search(NURSING_RE,t,re.I): return "home_nursing"
    if re.search(LAB_RE,t,re.I): return "lab_test_home"
    # A symptom plus a home-visit cue explicitly means in-person assessment.
    if re.search(HOME_RE,t,re.I) and re.search(SYMPTOM_RE,t,re.I): return "paramedic_home_visit"
    if re.search(TELE_RE,t,re.I): return "teleconsultation"
    if re.search(GENERAL_HOME_RE,t,re.I): return "paramedic_home_visit"
    # A bare doctor request is too vague to route without a symptom or service.
    if re.search(DOCTOR_RE,t,re.I): return "followup"
    return None

class TriageModel:
 def __init__(self):
  self.model=None; self.urgency_model=None
  try:
   import joblib
   from pathlib import Path
   path=Path(__file__).resolve().parents[2]/"models"/"triage.joblib"
   if path.exists():
    bundle=joblib.load(path)
    if isinstance(bundle,dict): self.model=bundle.get("care_model");self.urgency_model=bundle.get("urgency_model")
    else:self.model=bundle
  except Exception:self.model=None;self.urgency_model=None
 def predict(self,text):
  rule=keyword_rule(text)
  if rule=="followup": return "followup",1.0,{}
  if self.model is None:return (rule or "followup",1.0 if rule else 0.0,{})
  try:
   probs=self.model.predict_proba([text])[0]; names=list(self.model.classes_); idx=max(range(len(probs)),key=probs.__getitem__); cls=names[idx]
   # These service rules are deterministic and intentionally outrank the model.
   if rule=="paramedic_home_visit": cls=rule
   elif rule and cls!=rule and probs[idx]<.65: cls=rule
   return cls,float(probs[idx]),dict(zip(names,map(float,probs)))
  except Exception:return (rule or "followup",1.0 if rule else 0.0,{})
 def predict_urgency(self,text,care_type):
  if self.urgency_model is not None:
   try:return str(self.urgency_model.predict([text])[0])
   except Exception:pass
  return URGENCY.get(care_type,"same_day")
