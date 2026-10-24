def why_not(care_type): return f"Other care options were not selected; routing is based on the requested service ({care_type})."
def safety_net(): return "If symptoms become severe or an emergency develops, call 112 immediately."
def explain(care_type,urgency,flags,text):
 if flags:return f"Red-flag symptoms detected ({', '.join(flags)}); routed to emergency services, not home care."
 t=text.lower()
 if care_type=="home_nursing": lead="Specific nursing procedure requested; Medic home visit"
 elif care_type=="lab_test_home":lead="Home sample collection requested; lab service"
 elif care_type=="teleconsultation":lead="Request suitable for a virtual doctor consult"
 else:lead="Home assessment requested; Medic home visit"
 return f"{lead}; urgency assessed as {urgency}."
