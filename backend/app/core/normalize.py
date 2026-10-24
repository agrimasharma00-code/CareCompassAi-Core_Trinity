import re, unicodedata
VARIANTS={"bukhaar":"bukhar","sans":"saans","khasi":"khansi","injekshan":"injection"}
HINDI_MARKERS={"ko","hai","nahi","mein","se","chahiye","karna","ghar","ka","ki","ho","raha","rahi","papa","mummy","bukhar","dard"}
def normalize_text(text):
 text=unicodedata.normalize("NFKC",text.lower())
 for a,b in VARIANTS.items(): text=re.sub(rf"\b{a}\b",b,text)
 # Preserve Devanagari combining vowel marks; Python's \w excludes them.
 return re.sub(r"[^\w\s\u0900-\u097f]"," ",text,flags=re.UNICODE).strip()
def history_text(history,current):
 parts=[]
 for item in history or []:
  if item.get("role")=="user": parts.append(str(item.get("content",item.get("text",""))))
 return normalize_text(" ".join(parts+[current]))
def detect_language(text):
 if re.search(r"[\u0900-\u097f]",text): return "Hindi"
 words=set(normalize_text(text).split())
 return "Hinglish" if words & HINDI_MARKERS else "English"
