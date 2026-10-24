"""Public request and response models for care routing."""

from enum import Enum

from pydantic import BaseModel, Field


class Language(str, Enum):
    AUTO = "auto"
    EN = "en"
    HI = "hi"
    HINGLISH = "hinglish"


class CareType(str, Enum):
    PARAMEDIC_HOME_VISIT = "paramedic_home_visit"
    NURSE = "nurse"
    GP_TELECONSULT = "gp_teleconsult"
    SPECIALIST = "specialist"
    EMERGENCY_REFERRAL = "emergency_referral"


class Urgency(str, Enum):
    ROUTINE = "routine"
    SAME_DAY = "same_day"
    IMMEDIATE = "immediate"


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class ConversationTurn(BaseModel):
    role: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=1, max_length=4000)


class CareRequest(BaseModel):
    user_input: str = Field(min_length=1, max_length=4000)
    language: Language = Language.AUTO
    location: Location
    conversation_history: list[ConversationTurn] = Field(default_factory=list)


class MatchedCaregiver(BaseModel):
    caregiver_id: str
    score: float = Field(ge=0, le=1)
    reason: str


class CareResponse(BaseModel):
    follow_up_question: str | None = None
    care_type: CareType | None = None
    urgency: Urgency | None = None
    red_flags: list[str] = Field(default_factory=list)
    reasoning: str
    matched_caregivers: list[MatchedCaregiver] = Field(default_factory=list)
