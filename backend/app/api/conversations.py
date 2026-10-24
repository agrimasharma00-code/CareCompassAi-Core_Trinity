from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_role
from app.db.database import get_db
from app.db.models import Conversation, User, utc_now

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


class ConversationUpdate(BaseModel):
    messages: list[dict] = Field(default_factory=list, max_length=1000)


@router.get("/current")
def current_conversation(patient: User = Depends(require_role("patient")), session: Session = Depends(get_db)):
    conversation = session.scalar(select(Conversation).where(Conversation.user_id == patient.id))
    return {"messages": conversation.messages if conversation else [], "updated_at": conversation.updated_at.isoformat() if conversation else None}


@router.put("/current")
def save_conversation(request: ConversationUpdate, patient: User = Depends(require_role("patient")), session: Session = Depends(get_db)):
    conversation = session.scalar(select(Conversation).where(Conversation.user_id == patient.id))
    if conversation is None:
        conversation = Conversation(user_id=patient.id, messages=request.messages, updated_at=utc_now())
        session.add(conversation)
    else:
        conversation.messages = request.messages
        conversation.updated_at = utc_now()
    session.commit()
    session.refresh(conversation)
    return {"messages": conversation.messages, "updated_at": conversation.updated_at.isoformat()}
