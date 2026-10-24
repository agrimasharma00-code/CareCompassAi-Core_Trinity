from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
class CareType(str,Enum): paramedic_home_visit="paramedic_home_visit"; home_nursing="home_nursing"; lab_test_home="lab_test_home"; teleconsultation="teleconsultation"; emergency_112="emergency_112"
class Urgency(str,Enum): emergency="emergency"; same_day="same_day"; scheduled="scheduled"
class Location(BaseModel): lat: float; lng: float
class IntakeRequest(BaseModel): user_input: str; language: str="auto"; location: Location; conversation_history: list[dict]=Field(default_factory=list)
class Match(BaseModel): caregiver_id: str; score: float=Field(ge=0,le=1); reason: str
class IntakeResponse(BaseModel): model_config=ConfigDict(use_enum_values=True); follow_up_question: str|None; care_type: CareType|None; urgency: Urgency|None; red_flags: list[str]; reasoning: str; matched_caregivers: list[Match]
