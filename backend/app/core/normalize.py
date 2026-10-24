import logging
import re
import unicodedata

from app.config import get_settings

VARIANTS={"bukhaar":"bukhar","sans":"saans","khasi":"khansi","injekshan":"injection"}
HINDI_MARKERS={"ko","hai","nahi","mein","se","chahiye","karna","ghar","ka","ki","ho","raha","rahi","papa","mummy","bukhar","dard"}

logger = logging.getLogger(__name__)
INDIC_SCRIPTS = (
 ("Gurmukhi", "pa-IN", re.compile(r"[\u0a00-\u0a7f]")),
 ("Bengali", "bn-IN", re.compile(r"[\u0980-\u09ff]")),
 ("Gujarati", "gu-IN", re.compile(r"[\u0a80-\u0aff]")),
 ("Odia", "or-IN", re.compile(r"[\u0b00-\u0b7f]")),
 ("Tamil", "ta-IN", re.compile(r"[\u0b80-\u0bff]")),
 ("Telugu", "te-IN", re.compile(r"[\u0c00-\u0c7f]")),
 ("Kannada", "kn-IN", re.compile(r"[\u0c80-\u0cff]")),
 ("Malayalam", "ml-IN", re.compile(r"[\u0d00-\u0d7f]")),
)

GURMUKHI_TO_DEVANAGARI = str.maketrans({
 "ਅ":"अ", "ਆ":"आ", "ਇ":"इ", "ਈ":"ई", "ਉ":"उ", "ਊ":"ऊ", "ਏ":"ए", "ਐ":"ऐ", "ਓ":"ओ", "ਔ":"औ",
 "ਕ":"क", "ਖ":"ख", "ਗ":"ग", "ਘ":"घ", "ਙ":"ङ", "ਚ":"च", "ਛ":"छ", "ਜ":"ज", "ਝ":"झ", "ਞ":"ञ",
 "ਟ":"ट", "ਠ":"ठ", "ਡ":"ड", "ਢ":"ढ", "ਣ":"ण", "ਤ":"त", "ਥ":"थ", "ਦ":"द", "ਧ":"ध", "ਨ":"न",
 "ਪ":"प", "ਫ":"फ", "ਬ":"ब", "ਭ":"भ", "ਮ":"म", "ਯ":"य", "ਰ":"र", "ਲ":"ल", "ਵ":"व", "ੜ":"ड़",
 "ਸ਼":"श", "ਸ":"स", "ਹ":"ह", "ਖ਼":"ख़", "ਗ਼":"ग़", "ਜ਼":"ज़", "ਫ਼":"फ़", "ਲ਼":"ळ",
 "ਾ":"ा", "ਿ":"ि", "ੀ":"ी", "ੁ":"ु", "ੂ":"ू", "ੇ":"े", "ੈ":"ै", "ੋ":"ो", "ੌ":"ौ", "ੰ":"ं", "ਂ":"ँ", "ੱ":"", "੍":"्", "਼":"़", "ੑ":"॑", "੒":"॒",
 "੦":"०", "੧":"१", "੨":"२", "੩":"३", "੪":"४", "੫":"५", "੬":"६", "੭":"७", "੮":"८", "੯":"९",
})

def script_language(text):
 for script, language_code, pattern in INDIC_SCRIPTS:
  if pattern.search(text):
   return script, language_code
 return None, None

def _fallback_gurmukhi(text):
 # These common Punjabi words need Hindi postpositions/orthography for the
 # existing red-flag vocabulary to recognize their meaning after mapping.
 for punjabi, hindi in (("ਵਿੱਚ", "में"), ("ਨੂੰ", "को"), ("ਦਰਦ", "दर्द"), ("ਰਿਹਾ", "रहा"), ("ਰਹੀ", "रही"), ("ਹਨ", "हैं")):
  text = text.replace(punjabi, hindi)
 return text.translate(GURMUKHI_TO_DEVANAGARI)

def transliterate_to_devanagari(text):
 script, source_language_code = script_language(text)
 if not script:
  return text
 converted = None
 if get_settings().sarvam_api_key:
  try:
   from app.integrations import sarvam_client
   converted = sarvam_client.transliterate(text, source_language_code, "hi-IN")
  except Exception:
   converted = None
 if converted:
  logger.info("Converted %s script to Devanagari for intake", script)
  return converted
 if script == "Gurmukhi":
  logger.info("Converted Gurmukhi script to Devanagari with local character mapping")
  return _fallback_gurmukhi(text)
 logger.warning("Could not convert %s script to Devanagari; Sarvam transliteration is unavailable", script)
 return text

def normalize_text(text):
 text=transliterate_to_devanagari(text)
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
