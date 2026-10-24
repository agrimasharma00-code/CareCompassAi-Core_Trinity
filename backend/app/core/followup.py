from app.config import get_settings
QUESTION={"English":"Happy to help. Could you tell me the main symptom or service you need (home visit, nursing, lab test, or teleconsult)?","Hindi":"ज़रूर। कृपया मुख्य परेशानी या सेवा बताएं (घर पर जांच, नर्सिंग, लैब टेस्ट या डॉक्टर से बात)?","Hinglish":"Zaroor. Main symptom ya service bata sakte hain (home visit, nursing, lab test, ya doctor se baat)?"}
SCREENING={"English":"Is there chest pain, difficulty breathing, fainting or confusion?","Hindi":"क्या सीने में दर्द, सांस लेने में तकलीफ़, बेहोशी या भ्रम है?","Hinglish":"Kya seene mein dard, saans lene mein dikkat, behoshi ya confusion hai?"}
YES={"yes","y","haan","han","ha","हाँ","हां","जी","जी हाँ","ji","ji haan"}
NO={"no","n","nahi","nahin","नहीं","ना"}
def screening_asked(history):
 return any(x.get("role")=="assistant" and x.get("follow_up_question") in SCREENING.values() for x in history or [])
def answer_kind(text):
 t=text.strip().lower()
 if t in YES:return "yes"
 if t in NO:return "no"
 if any(token in t for token in ("chest pain","seene mein dard","सीने में दर्द","can't breathe","cannot breathe","saans nahi","सांस नहीं","faint","behosh","बेहोश","confusion","confused","भ्रम")):return "yes"
 return "unclear"
def decide(text,lang,history,prediction,confidence,rule):
 count=sum(1 for x in history or [] if x.get("role")=="assistant" and x.get("follow_up_question"))
 if (prediction=="followup" or (confidence<get_settings().followup_threshold and not rule)) and count<get_settings().max_followups:
  q=QUESTION.get(lang,QUESTION["English"]); previous={x.get("follow_up_question") for x in history or []}
  if q in previous:q=QUESTION["English"] if lang=="English" else QUESTION["Hinglish"]
  if q not in previous:return q
 return None
