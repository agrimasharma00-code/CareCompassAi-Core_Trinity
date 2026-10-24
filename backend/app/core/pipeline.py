from app.core.intake import prepare
from app.core.red_flags import check
from app.core.triage import TriageModel,keyword_rule,URGENCY
from app.core.followup import decide,SCREENING,screening_asked,answer_kind
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
 asked=screening_asked(request.conversation_history)
 if asked:
  answer=answer_kind(request.user_input)
  if answer=="yes":
   return {"follow_up_question":None,"care_type":"emergency_112","urgency":"emergency","red_flags":flags,"reasoning":"Emergency screening answer confirmed a possible red flag; routed to emergency services.","matched_caregivers":[]}
  if answer=="unclear":
   return {"follow_up_question":None,"care_type":"emergency_112","urgency":"emergency","red_flags":[],"reasoning":"Emergency screening was unclear; using the safer emergency route.","matched_caregivers":[]}
  # A negative answer clears the model-only suspicion; select the strongest
  # non-emergency class and continue the regular triage path.
  non_emergency={k:v for k,v in probs.items() if k!="emergency_112"}
  if non_emergency:prediction=max(non_emergency,key=non_emergency.get);confidence=float(non_emergency[prediction])
  if rule:prediction=rule
 elif probs.get("emergency_112",0)>=cfg.emergency_threshold:
  count=sum(1 for x in request.conversation_history or [] if x.get("role")=="assistant" and x.get("follow_up_question"))
  if count<cfg.max_followups:
   return {"follow_up_question":SCREENING.get(lang,SCREENING["English"]),"care_type":None,"urgency":None,"red_flags":[],"reasoning":"The model raised an emergency concern without a matching red-flag phrase; asking a safety screening question.","matched_caregivers":[]}
  prediction="emergency_112"
 if prediction=="emergency_112":return {"follow_up_question":None,"care_type":"emergency_112","urgency":"emergency","red_flags":[],"reasoning":"Emergency routing triggered by model risk threshold; no specific red-flag phrase was identified.","matched_caregivers":[]}
 question=decide(text,lang,request.conversation_history,prediction,confidence,rule)
 if question:return {"follow_up_question":question,"care_type":None,"urgency":None,"red_flags":[],"reasoning":"Intent underspecified — asking a follow-up before deciding care type.","matched_caregivers":[]}
 if prediction=="followup":prediction="paramedic_home_visit"
 urgency=_model.predict_urgency(text,prediction)
 if urgency=="emergency":
  return {"follow_up_question":None,"care_type":"emergency_112","urgency":"emergency","red_flags":[],"reasoning":"Urgency model selected emergency routing; no specific red-flag phrase was identified.","matched_caregivers":[]}
 return {"follow_up_question":None,"care_type":prediction,"urgency":urgency,"red_flags":[],"reasoning":explain(prediction,urgency,[],text),"matched_caregivers":match(prediction,request.location,lang,text)}
