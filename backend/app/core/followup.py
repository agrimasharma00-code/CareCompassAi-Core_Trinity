from app.config import get_settings
QUESTION={"English":"Happy to help. Could you tell me the main symptom or service you need (home visit, nursing, lab test, or teleconsult)?","Hindi":"ज़रूर। कृपया मुख्य परेशानी या सेवा बताएं (घर पर जांच, नर्सिंग, लैब टेस्ट या डॉक्टर से बात)?","Hinglish":"Zaroor. Main symptom ya service bata sakte hain (home visit, nursing, lab test, ya doctor se baat)?"}
def decide(text,lang,history,prediction,confidence,rule):
 count=sum(1 for x in history or [] if x.get("role")=="assistant" and x.get("follow_up_question"))
 if (prediction=="followup" or (confidence<get_settings().followup_threshold and not rule)) and count<get_settings().max_followups:
  q=QUESTION.get(lang,QUESTION["English"]); previous={x.get("follow_up_question") for x in history or []}
  if q in previous:q=QUESTION["English"] if lang=="English" else QUESTION["Hinglish"]
  if q not in previous:return q
 return None
