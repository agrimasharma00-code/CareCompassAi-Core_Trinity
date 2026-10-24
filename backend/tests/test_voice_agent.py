from app.core.voice_agent import language_from_text, resolved_language
from app.schemas.care import Language


def test_detects_devanagari_hindi_for_agent_reply() -> None:
    assert language_from_text("नमस्ते, मुझे बुखार है") == Language.HI


def test_detects_roman_hinglish_for_agent_reply() -> None:
    assert language_from_text("abhi thora sahi hai") == Language.HINGLISH


def test_detects_english_for_agent_reply() -> None:
    assert language_from_text("I have had a fever since yesterday") == Language.EN


def test_keeps_sarvam_hinglish_decision() -> None:
    assert resolved_language("hinglish", Language.AUTO) == Language.HINGLISH
