from app.modules.agents import router as assistant
from app.schemas.care import Location


def request(message, history=None, language="auto", care_context=None, intake_state=None):
    return assistant.AssistantRequest(
        message=message,
        location=Location(lat=28.54, lng=77.27),
        history=history or [],
        language=language,
        care_context=care_context,
        intake_state=intake_state,
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


def test_arithmetic_and_unrelated_questions_are_redirected_without_llm(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("off-topic text must not reach a generative model")

    monkeypatch.setattr(assistant.sarvam_client, "chat_json", forbidden)
    monkeypatch.setattr(assistant.sarvam_client, "chat_text", forbidden)
    for message in ("2+2", "What is 2 + 2?", "What is the capital of France?", "Write me a Python script"):
        result = assistant.chat(request(message))
        assert result.mode == "off_topic"
        assert result.care is None
        assert "health" in result.message.lower()


def test_medicine_and_dose_requests_get_safe_redirect_without_llm(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_text", lambda *_args: (_ for _ in ()).throw(AssertionError("no medication advice from the model")))
    result = assistant.chat(request("Which medicine should I take for a headache?"))
    assert result.mode == "answer"
    assert "can’t recommend a medicine or dose" in result.message


def test_unsafe_model_health_answer_is_replaced_by_safe_fallback(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_text", lambda *_args: "You have flu. Take paracetamol 500 mg now.")
    result = assistant.chat(request("What are common reasons for fever?"))
    assert result.mode == "answer"
    assert "You have flu" not in result.message
    assert "500 mg" not in result.message


def test_personal_symptom_and_red_flag_take_care_path(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_json", lambda *args: None)
    care = assistant.chat(request("mujhe bukhar hai, kya karun?"))
    assert care.mode == "followup"
    assert care.intake_state.pending_question == "red_flag"

    emergency = assistant.chat(request("seene mein dard hai, kya karun?"))
    assert emergency.mode == "emergency"
    assert emergency.care["care_type"] == "emergency_112"


def test_guided_intake_screens_then_collects_missing_facts(monkeypatch):
    monkeypatch.setattr(assistant, "run_triage", lambda req: {"care_type": "teleconsultation", "urgency": "same_day", "reasoning": "A virtual consult fits the reported concern.", "follow_up_question": None, "red_flags": [], "matched_caregivers": []})
    first = assistant.chat(request("मेरे सिर में दर्द हो रहा है"))
    assert first.mode == "followup" and first.intake_state.pending_question == "red_flag"
    assert first.suggestions == ["नहीं", "हाँ"]
    second = assistant.chat(request("नहीं", intake_state=first.intake_state))
    assert second.intake_state.pending_question == "who_age"
    third = assistant.chat(request("वयस्क", intake_state=second.intake_state))
    assert third.intake_state.pending_question == "duration"
    final = assistant.chat(request("1–3 दिन", intake_state=third.intake_state))
    assert final.mode == "care" and final.care["care_type"] == "teleconsultation"
    assert final.understood and final.why_not and final.safety_net


def test_guided_red_flag_yes_escalates_without_triage(monkeypatch):
    monkeypatch.setattr(assistant, "run_triage", lambda req: (_ for _ in ()).throw(AssertionError("triage should not run")))
    first = assistant.chat(request("I have a headache"))
    result = assistant.chat(request("yes", intake_state=first.intake_state))
    assert result.mode == "emergency" and result.care["care_type"] == "emergency_112"


def test_guided_mild_headache_prefers_virtual_doctor_unless_home_visit_requested(monkeypatch):
    monkeypatch.setattr(assistant, "run_triage", lambda _req: {"care_type": "paramedic_home_visit", "urgency": "same_day", "reasoning": "model prediction", "follow_up_question": None, "red_flags": [], "matched_caregivers": []})
    state = assistant.IntakeState(symptoms=["headache"], who="self", age_group="adult", duration="today", red_flags_screened=True, question_count=3)
    virtual = assistant.chat(request("I have a headache", intake_state=state))
    assert virtual.mode == "care" and virtual.care["care_type"] == "teleconsultation"


def test_emergency_does_not_stick_to_new_turn_and_adds_reminder(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_json", lambda *args: None)
    first = assistant.chat(request("i am having chest pain"))
    assert first.mode == "emergency"
    result = assistant.chat(request("i am having stomach ache", [{"role": "user", "content": "i am having chest pain"}, {"role": "assistant", "content": first.message, "display": {"mode": "emergency"}}]))
    assert result.mode in {"care", "followup"}
    assert "If the earlier emergency symptoms are still present, call 112 now." in result.message


def test_typo_health_routes_to_care_and_arithmetic_is_off_topic(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_json", lambda *args: None)
    stomach = assistant.chat(request("i am having stomch issues"))
    assert stomach.mode == "followup"
    assert "stomach pain" in stomach.intake_state.symptoms
    assert assistant.chat(request("2+2 kitna hai")).mode == "off_topic"


def test_vague_and_yes_care_requests_ask_for_symptom_chips(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_json", lambda *args: None)
    for text in ("i am not feeling well", "tabiyat theek nahi", "help"):
        response = assistant.chat(request(text))
        assert response.mode == "followup"
        assert "problem" in response.message.lower() or "problem" in response.message or "परेशानी" in response.message or "problem" in response.message.lower()
        assert len(response.suggestions) == 6
        yes = assistant.chat(request("Yes, I need care", intake_state=response.intake_state, language="en-IN"))
        assert yes.mode == "followup" and yes.message == "What is the main problem?"


def test_chip_answers_are_structured_and_not_triage_text(monkeypatch):
    seen = []
    monkeypatch.setattr(assistant, "run_triage", lambda req: (seen.append(req.user_input) or {"care_type": "teleconsultation", "urgency": "same_day", "reasoning": "ok", "follow_up_question": None, "red_flags": [], "matched_caregivers": []}))
    state = assistant.IntakeState(pending_question="who_problem")
    parsed = assistant.chat(request("Stomach problem", intake_state=state))
    assert parsed.intake_state.symptoms == ["stomach pain"]
    assert "Stomach problem" not in parsed.intake_state.symptom_text
    ready = assistant.IntakeState(symptoms=["fever"], symptom_text="fever", who="self", age_group="adult", duration="today", red_flags_screened=True)
    assistant.chat(request("yes", intake_state=ready))
    assert all("yes" not in text.lower() for text in seen)


def test_heavy_bleeding_is_reported_as_a_red_flag(monkeypatch):
    result = assistant.chat(request("I am bleeding heavily"))
    assert result.mode == "emergency"
    assert "severe_bleeding" in result.care["red_flags"]


def test_model_classification_failure_falls_back_to_clarification(monkeypatch):
    def fail(*args):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(assistant.sarvam_client, "chat_json", fail)
    result = assistant.chat(request("I need help deciding what to do"))
    assert result.mode == "followup"
    assert result.message == "What is the main problem?"


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
    assert "simulated demo workflow" in seen["system"]


def test_more_details_explains_prior_decision_without_retriage(monkeypatch):
    monkeypatch.setattr(assistant.sarvam_client, "chat_text", lambda *args: None)
    calls = []

    def fake_triage(req):
        calls.append(req.user_input)
        return {"care_type": "teleconsultation", "urgency": "same_day", "reasoning": "prior reasoning", "follow_up_question": None, "red_flags": [], "matched_caregivers": []}

    monkeypatch.setattr(assistant, "run_triage", fake_triage)
    first = assistant.chat(request("I need a doctor consult for acidity"))
    first = assistant.chat(request("no", care_context=first.care_context, intake_state=first.intake_state))
    first = assistant.chat(request("adult", care_context=first.care_context, intake_state=first.intake_state))
    first = assistant.chat(request("2 days", care_context=first.care_context, intake_state=first.intake_state))
    first = assistant.chat(request("doctor consult", care_context=first.care_context, intake_state=first.intake_state))
    assert first.mode == "care" and first.care_context is not None
    history = [
        {"role": "user", "content": "I need a doctor consult for acidity"},
        {"role": "assistant", "content": first.message, "care_context": first.care_context.model_dump()},
    ]
    detail = assistant.chat(request("more details", history, care_context=first.care_context))
    assert detail.mode == "answer"
    assert "Not emergency" in detail.message and "Not home nursing" in detail.message
    assert "chest pain" in detail.message and "call 112" in detail.message
    assert calls and "acidity" in calls[-1] and "2 days" in calls[-1]
    assert len(calls) == 2


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
    assert result.message.startswith("क्या")
    assert "A" not in result.message
