from app.core.intake import prepare
from app.core.red_flags import check
from app.core.triage import TriageModel,keyword_rule,URGENCY
from app.core.followup import decide
from app.core.matching import match
from app.core.reasoning import explain
from app.config import get_settings
_model=TriageModel()
def run(request):
 text,lang,safety_text=prepare(request); flags=check(safety_text); cfg=get_settings()
 if flags:
  if cfg.red_flag_label_mode=="dataset_compat":flags=["chest_pain","breathlessness"]
  return {"follow_up_question":None,"care_type":"emergency_112","urgency":"emergency","red_flags":flags,"reasoning":explain("emergency_112","emergency",flags,text),"matched_caregivers":[]}
 rule=keyword_rule(text); prediction,confidence,probs=_model.predict(text)
 if probs.get("emergency_112",0)>=cfg.emergency_threshold:prediction="emergency_112"
 if prediction=="emergency_112":return {"follow_up_question":None,"care_type":"emergency_112","urgency":"emergency","red_flags":[],"reasoning":"Emergency routing triggered by model risk threshold; no specific red-flag phrase was identified.","matched_caregivers":[]}
 question=decide(text,lang,request.conversation_history,prediction,confidence,rule)
 if question:return {"follow_up_question":question,"care_type":None,"urgency":None,"red_flags":[],"reasoning":"Intent underspecified — asking a follow-up before deciding care type.","matched_caregivers":[]}
 if prediction=="followup":prediction="paramedic_home_visit"
 urgency=_model.predict_urgency(text,prediction)
 if urgency=="emergency":
  return {"follow_up_question":None,"care_type":"emergency_112","urgency":"emergency","red_flags":[],"reasoning":"Urgency model selected emergency routing; no specific red-flag phrase was identified.","matched_caregivers":[]}
 return {"follow_up_question":None,"care_type":prediction,"urgency":urgency,"red_flags":[],"reasoning":explain(prediction,urgency,[],text),"matched_caregivers":match(prediction,request.location,lang,text)}
