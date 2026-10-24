from app.core.red_flags import find_red_flags


def test_english_red_flag_is_detected() -> None:
    assert "Breathing difficulty" in find_red_flags("I have severe breathing difficulty")


def test_hindi_red_flag_is_detected() -> None:
    assert "Chest pain" in find_red_flags("सीने में दर्द हो रहा है")


def test_hinglish_red_flag_is_detected() -> None:
    assert "Breathing difficulty" in find_red_flags("saans lene mein dikkat hai")


def test_negated_red_flag_does_not_trigger() -> None:
    assert "Breathing difficulty" not in find_red_flags("No breathing difficulty, only cough")
    assert "Breathing difficulty" not in find_red_flags("saans lene mein dikkat nahi hai")
