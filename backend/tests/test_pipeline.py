from app.core.pipeline import CarePipeline
from app.schemas.care import CareRequest, ConversationTurn, Location


def test_emergency_case_never_returns_caregivers() -> None:
    response = CarePipeline().run(CareRequest(user_input="I have chest pain", location=Location(lat=28.545, lng=77.192)))
    assert response.care_type == "emergency_referral"
    assert response.urgency == "immediate"
    assert response.matched_caregivers == []


def test_explicit_home_lab_request_uses_supplied_roster() -> None:
    response = CarePipeline().run(CareRequest(user_input="Need a blood sample collected at home", location=Location(lat=28.545, lng=77.192)))
    assert response.care_type == "lab_test_home"
    assert response.matched_caregivers


def test_headache_collects_targeted_details_before_matching() -> None:
    pipeline = CarePipeline()
    location = Location(lat=28.545, lng=77.192)
    first = pipeline.run(CareRequest(user_input="I have a headache", location=location))
    assert first.follow_up_question == "When did this start? Did it begin suddenly or gradually?"
    second_history = [
        ConversationTurn(role="user", content="I have a headache"),
        ConversationTurn(role="assistant", content=first.follow_up_question),
    ]
    second = pipeline.run(CareRequest(user_input="It started two days ago", location=location, conversation_history=second_history))
    assert second.follow_up_question and "Where is the headache" in second.follow_up_question
    third_history = second_history + [
        ConversationTurn(role="user", content="It started two days ago"),
        ConversationTurn(role="assistant", content=second.follow_up_question),
    ]
    third = pipeline.run(CareRequest(user_input="It is on the right side, throbbing, seven out of ten", location=location, conversation_history=third_history))
    assert third.follow_up_question and "worst-ever" in third.follow_up_question
    final_history = third_history + [
        ConversationTurn(role="user", content="It is on the right side, throbbing, seven out of ten"),
        ConversationTurn(role="assistant", content=third.follow_up_question),
    ]
    final = pipeline.run(CareRequest(user_input="No, none of those warning symptoms", location=location, conversation_history=final_history))
    assert final.follow_up_question is None
    assert "not a diagnosis" in final.reasoning
