from app.core.intake import extract_facts, next_follow_up
from app.schemas.care import ConversationTurn, Language


def test_extracts_hinglish_duration_and_relation() -> None:
    facts = extract_facts("papa ko do din se bukhar hai", Language.AUTO)
    assert facts.language == "hinglish"
    assert facts.duration == "do din"
    assert facts.relation == "papa"


def test_follow_up_is_not_repeated() -> None:
    facts = extract_facts("papa ko bukhar hai", Language.AUTO)
    history = [ConversationTurn(role="assistant", content="Kya saans ki dikkat, seene mein dard, behoshi, zyada khoon ya daura hai?")]
    question = next_follow_up(facts, "papa ko bukhar hai", history, confidence=0.4)
    assert question == "Patient ki umar kya hai?"
