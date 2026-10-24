from app.api import wellness


def test_crisis_response_precedes_model_and_has_indian_resources(monkeypatch):
    monkeypatch.setattr(wellness.sarvam_client, "chat_text", lambda *_: (_ for _ in ()).throw(AssertionError("model must not run for crisis")))
    result = wellness.chat(wellness.WellnessRequest(message="मैं जीना नहीं चाहता"))
    assert result.crisis and result.language == "Hindi"
    assert "112" in result.message and "14416" in result.message
    assert result.contacts == [{"label": "Emergency", "number": "112"}, {"label": "Tele-MANAS", "number": "14416"}]


def test_non_crisis_uses_template_when_sarvam_is_down(monkeypatch):
    monkeypatch.setattr(wellness.sarvam_client, "chat_text", lambda *_: None)
    result = wellness.chat(wellness.WellnessRequest(message="I feel stressed today"))
    assert not result.crisis and result.language == "English"
    assert "qualified health professional" in result.message
