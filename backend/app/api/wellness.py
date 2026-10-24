import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.red_flags import check_wellness_crisis
from app.integrations import sarvam_client

router = APIRouter(prefix="/api/v1/wellness", tags=["wellness"])


class WellnessRequest(BaseModel):
    message: str = Field(min_length=1, max_length=3000)
    language: Literal["Hindi", "Hinglish", "English", "auto"] = "auto"


class WellnessResponse(BaseModel):
    message: str
    language: Literal["Hindi", "Hinglish", "English"]
    crisis: bool = False
    contacts: list[dict] = Field(default_factory=list)


def _language(text: str, selected: str) -> str:
    if selected != "auto":
        return selected
    if re.search(r"[\u0900-\u097f]", text):
        return "Hindi"
    tokens = set(re.findall(r"[a-z]+", text.lower()))
    return "Hinglish" if tokens & {"hai", "hoon", "nahi", "nahin", "mujhe", "mera", "meri", "kar", "raha", "rahi", "dil", "bahut"} else "English"


@router.post("/chat", response_model=WellnessResponse)
def chat(request: WellnessRequest):
    language = _language(request.message, request.language)
    if check_wellness_crisis(request.message):
        messages = {
            "Hindi": "मुझे दुख है कि आप इतना कठिन महसूस कर रही हैं। कृपया अभी किसी भरोसेमंद व्यक्ति को अपने पास बुलाएँ और अकेली न रहें। तत्काल खतरा हो तो 112 पर कॉल करें; Tele-MANAS से 14416 पर बात करें।",
            "Hinglish": "Mujhe afsos hai ki aap itna mushkil mehsoos kar rahi hain. Kripya abhi kisi bharosemand vyakti ko apne paas bulayein aur akeli na rahein. Turant khatra ho to 112 call karein; Tele-MANAS 14416 par baat karein.",
            "English": "I’m sorry you’re going through this. Please ask someone you trust to stay with you now. If you may be in immediate danger, call 112; you can also contact Tele-MANAS at 14416.",
        }
        return WellnessResponse(message=messages[language], language=language, crisis=True, contacts=[{"label": "Emergency", "number": "112"}, {"label": "Tele-MANAS", "number": "14416"}])

    prompt = (
        "You are a supportive CareCompass wellbeing companion for people in India. Listen first and reply briefly (2–4 sentences) in the user's requested language. "
        "Never diagnose, prescribe, claim to provide therapy, create dependence, or promise confidentiality beyond the app's stated privacy. "
        "Encourage trusted people and qualified professionals where appropriate. Do not save or share this message."
    )
    reply = sarvam_client.chat_text([{"role": "system", "content": f"{prompt} Target language: {language}. Use Devanagari for Hindi and Roman script for Hinglish."}, {"role": "user", "content": request.message}])
    if not reply:
        reply = {
            "Hindi": "यह सुनकर लगता है कि यह समय आपके लिए कठिन है। आप चाहें तो बताएं कि अभी सबसे ज़्यादा क्या परेशान कर रहा है। किसी भरोसेमंद व्यक्ति या स्वास्थ्य पेशेवर से बात करना मददगार हो सकता है।",
            "Hinglish": "Yeh waqt aapke liye mushkil lag raha hai. Aap chahein to bata sakti hain ki abhi sabse zyada kya pareshan kar raha hai. Kisi bharosemand vyakti ya health professional se baat karna madadgar ho sakta hai.",
            "English": "It sounds like this is a difficult moment. If you’d like, tell me what feels hardest right now. Talking with someone you trust or a qualified health professional may help.",
        }[language]
    return WellnessResponse(message=reply, language=language)
