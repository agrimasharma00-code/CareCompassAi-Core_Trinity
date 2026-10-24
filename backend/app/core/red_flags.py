import json,re
from pathlib import Path
VOCAB=["chest_pain","breathlessness","unconsciousness","severe_bleeding","stroke_symptoms","seizure","high_fever_infant","suicidal_ideation","severe_dehydration"]
PATTERNS={
"chest_pain":[r"chest pain",r"seene mein dard",r"सीने में दर्द"],
"breathlessness":[r"can't breathe",r"cannot breathe",r"saans nahi aa rahi",r"सांस नहीं आ रही",r"saans ki dikkat",r"सांस की तकलीफ"],
"unconsciousness":[r"behosh",r"बेहोश",r"collapsed",r"not responding",r"gir gaye response nahi",r"जवाब नहीं दे रहे",r"होश में नहीं"],
"severe_bleeding":[r"heavy bleeding",r"bleeding ruk nahi rahi",r"खून नहीं रुक रहा"],
"stroke_symptoms":[r"face droop",r"slurred speech",r"ek taraf kamzori",r"लकवा"],
"seizure":[r"daura",r"दौरा",r"मिर्गी",r"mirgi",r"fits",r"convulsion"],
"high_fever_infant":[r"(?:baby|infant|newborn|navjaat|नवजात).{0,35}(?:high fever|tez bukhar|तेज बुखार)",r"(?:high fever|tez bukhar|तेज बुखार).{0,35}(?:baby|infant|newborn|navjaat|नवजात)"],
"suicidal_ideation":[r"khudkushi",r"आत्महत्या",r"marna chahta",r"मरना चाहता",r"suicide",r"end my life"],
"severe_dehydration":[r"can't keep fluids",r"sunken eyes",r"bahut ulti.{0,30}dast.{0,30}peshab nahi",r"पेशाब नहीं.{0,20}(?:उल्टी|दस्त)",r"बहुत उल्टी.{0,25}दस्त.{0,25}पेशाब नहीं"]}
NEG={"chest_pain":[r"no chest pain",r"chest pain nahi hai",r"सीने में दर्द नहीं"],"breathlessness":[r"saans ki dikkat nahi hai",r"breathing difficulty nahi",r"no breathlessness",r"सांस की तकलीफ नहीं है"]}
def check(text):
 t=text.lower(); found=[]
 for label,ps in PATTERNS.items():
  if any(re.search(p,t) for p in ps) and not any(re.search(p,t) for p in NEG.get(label,[])):found.append(label)
 return found
