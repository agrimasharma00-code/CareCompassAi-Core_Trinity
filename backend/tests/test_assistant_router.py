from app.modules.agents import router as assistant
from app.schemas.care import Location


def request(message, history=None, language="auto", care_context=None):
    return assistant.AssistantRequest(
        message=message,
        location=Location(lat=28.54, lng=77.27),
        history=history or [],
        language=language,
        care_context=care_context,
    )


def test_rule_intents_route_without_triage_for_non_care_messages(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_json", lambda *args: None)
    cases = {
        "hello": "smalltalk",
        "mera naam Khushi hai": "smalltalk",
        "bukhar mein kya khana chahiye?": "answer",
        "what is normal BP?": "answer",
        "booking kaise karein?": "app_help",
        "IPL score kya hai?": "off_topic",
    }
    for message, mode in cases.items():
        result = assistant.chat(request(message))
        assert result.mode == mode
        assert result.care is None


def test_personal_symptom_and_red_flag_take_care_path(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_json", lambda *args: None)
    care = assistant.chat(request("mujhe bukhar hai, kya karun?"))
    assert care.mode in {"care", "followup"}
    assert care.care is not None

    emergency = assistant.chat(request("seene mein dard hai, kya karun?"))
    assert emergency.mode == "emergency"
    assert emergency.care["care_type"] == "emergency_112"


def test_red_flag_in_earlier_user_turn_is_checked_first(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_json", lambda *args: None)
    result = assistant.chat(request("hello", [{"role": "user", "content": "chest pain"}]))
    assert result.mode == "emergency"


def test_model_classification_failure_falls_back_to_clarification(monkeypatch):
    def fail(*args):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(assistant.sarvam_client, "chat_json", fail)
    result = assistant.chat(request("I need help deciding what to do"))
    assert result.mode == "followup"
    assert "looking for care" in result.message


def test_sarvam_answer_failure_uses_template_without_care(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_text", lambda *args: None)
    result = assistant.chat(request("bukhar mein kya khana chahiye?"))
    assert result.mode == "answer"
    assert result.care is None
    assert "112" in result.message
    assert "doctor" in result.message.lower()


def test_app_help_uses_fixed_faq_context(monkeypatch):
    seen = {}

    def fake_chat(messages):
        seen["system"] = messages[0]["content"]
        return None

    monkeypatch.setattr(assistant.sarvam_client, "chat_text", fake_chat)
    result = assistant.chat(request("booking kaise karein?"))
    assert result.mode == "app_help" and result.care is None
    assert "Booking is not enabled yet" in seen["system"]


def test_more_details_explains_prior_decision_without_retriage(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_text", lambda *args: None)
    calls = []

    def fake_triage(req):
        calls.append(req.user_input)
        return {"care_type": "teleconsultation", "urgency": "same_day", "reasoning": "prior reasoning", "follow_up_question": None, "red_flags": [], "matched_caregivers": []}

    monkeypatch.setattr(assistant, "run_triage", fake_triage)
    first = assistant.chat(request("I need a doctor consult for acidity"))
    assert first.mode == "care" and first.care_context is not None
    history = [
        {"role": "user", "content": "I need a doctor consult for acidity"},
        {"role": "assistant", "content": first.message, "care_context": first.care_context.model_dump()},
    ]
    detail = assistant.chat(request("more details", history, care_context=first.care_context))
    assert detail.mode == "answer"
    assert "Other options" in detail.message
    assert "chest pain" in detail.message and "call 112" in detail.message
    assert calls == ["I need a doctor consult for acidity"]


def test_just_information_uses_symptoms_from_context(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_text", lambda *args: None)
    monkeypatch.setattr(assistant, "run_triage", lambda req: {"care_type": "teleconsultation", "urgency": "same_day", "reasoning": "reason", "follow_up_question": None, "red_flags": [], "matched_caregivers": []})
    first = assistant.chat(request("I have a headache and want a doctor consult"))
    followup = assistant.chat(request("just information", care_context=first.care_context, history=[{"role": "user", "content": "I have a headache"}]))
    assert followup.mode == "answer"
    assert "headache" in followup.message.lower()


def test_latest_script_controls_reply_and_chips(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_text", lambda *args: None)
    hindi = assistant.chat(request("नमस्ते"))
    assert hindi.language == "Hindi"
    assert "मैं" in hindi.message and "सकती हूँ" in hindi.message
    assert all(not any("a" <= char.lower() <= "z" for char in chip) for chip in hindi.suggestions)

    hinglish = assistant.chat(request("Namaste"))
    assert hinglish.language == "Hinglish"
    assert "sakti hoon" in hinglish.message
    assert all(not any("\u0900" <= char <= "\u097f" for char in chip) for chip in hinglish.suggestions)


def test_followup_for_devanagari_user_stays_hindi(monkeypatch):
    monkeypatch.setattr(assistant, "run_triage", lambda req: {"care_type": None, "urgency": None, "reasoning": "", "follow_up_question": "Happy to help. What service do you need?", "red_flags": [], "matched_caregivers": []})
    result = assistant.chat(request("मुझे बुखार है"))
    assert result.mode == "followup"
    assert "कृपया" in result.message
    assert "A" not in result.message
