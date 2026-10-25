"""Safety-first orchestration for one routing request."""

from app.core.intake import extract_facts, next_follow_up
from app.core.matching import match_caregivers
from app.core.red_flags import find_red_flags
from app.core.reasoning import build_reasoning, handoff_summary, safety_netting, why_not_explanation
from app.core.triage import TriageClassifier
from app.schemas.care import CareRequest, CareResponse, CareType, Urgency


class CarePipeline:
    def __init__(self, triage: TriageClassifier | None = None) -> None:
        self.triage = triage or TriageClassifier()

    def run(self, request: CareRequest, force_final: bool = False) -> CareResponse:
        prior_user_text = " ".join(turn.content for turn in request.conversation_history if turn.role.lower() == "user")
        full_text = f"{prior_user_text} {request.user_input}".strip()
        facts = extract_facts(full_text, request.language)
        red_flags = find_red_flags(full_text)
        if red_flags:
            return CareResponse(
                care_type=CareType.EMERGENCY_REFERRAL,
                urgency=Urgency.IMMEDIATE,
                red_flags=red_flags,
                reasoning=build_reasoning(full_text, facts, red_flags),
                matched_caregivers=[],
                safety_netting=safety_netting(red_flags, Urgency.IMMEDIATE.value),
                why_not=why_not_explanation(red_flags, CareType.EMERGENCY_REFERRAL.value),
                handoff_summary=handoff_summary(facts, Urgency.IMMEDIATE.value, red_flags),
            )
        triage = self.triage.predict(full_text)
        question = next_follow_up(facts, full_text, request.conversation_history, triage.confidence, force_final)
        if question:
            return CareResponse(follow_up_question=question, reasoning="One brief detail will help route this request safely.", safety_netting=safety_netting([], None), why_not="A care option is not selected yet because one detail is still needed.", handoff_summary=handoff_summary(facts, None, []))
        lower_text = full_text.lower()
        # The compact training sample can confuse a pain-location answer with
        # home nursing. Keep the routing navigation-specific: knee/joint pain
        # should surface the supplied specialist-doctor roster for matching.
        symptom_route = "specialist" if any(term in lower_text for term in ("knee", "knees", "joint", "ghutna", "ghutno")) else None
        care_type = facts.requested_service or symptom_route or triage.care_type
        caregivers = match_caregivers(care_type, request.location, facts.language, full_text)
        return CareResponse(
            care_type=CareType(care_type),
            urgency=Urgency(triage.urgency),
            red_flags=[],
            reasoning=build_reasoning(full_text, facts),
            matched_caregivers=caregivers,
            safety_netting=safety_netting([], triage.urgency),
            why_not=why_not_explanation([], care_type),
            handoff_summary=handoff_summary(facts, triage.urgency, []),
        )
