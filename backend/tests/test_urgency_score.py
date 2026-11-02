from app.core.urgency_score import BANDS, compute_urgency_score


def test_red_flag_forces_emergency_score_100():
    result = compute_urgency_score({}, {"urgency": "same_day", "red_flags": ["chest_pain"]})
    assert result["score"] == 100
    assert result["level"] == "emergency"
    assert result["factors"][0]["detail"] == "chest_pain"


def test_headache_one_day_stays_inside_same_day_band():
    result = compute_urgency_score(
        {"age_group": "adult", "duration": "1 day", "symptoms": ["headache"]},
        {"urgency": "same_day", "red_flags": []},
    )
    assert result["level"] == "same_day"
    assert BANDS["same_day"]["min"] <= result["score"] <= BANDS["same_day"]["max"]


def test_lab_request_stays_scheduled_and_missing_facts_are_explicit():
    result = compute_urgency_score({}, {"urgency": "scheduled", "red_flags": []})
    assert result["level"] == "scheduled"
    assert result["score"] == 0
    assert all(factor["detail"] == "Not provided" for factor in result["factors"])


def test_score_always_respects_triage_band():
    for level, band in BANDS.items():
        score = compute_urgency_score(
            {"age_group": "child", "duration": "more than 3 days", "symptoms": ["a", "b", "c"], "symptom_text": "severe"},
            {"urgency": level, "red_flags": []},
        )
        assert band["min"] <= score["score"] <= band["max"]
