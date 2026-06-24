from sqlalchemy.orm import Session
from app.models.chat_session import ChatSession
from app.models.chat_message import ChatMessage
from app.schemas.chat import ChatSessionCreate, ChatMessageCreate
from typing import List, Optional
import uuid

class ChatRepository:
    @staticmethod
    def get_sessions(db: Session) -> List[ChatSession]:
        return db.query(ChatSession).order_by(ChatSession.created_at.desc()).all()

    @staticmethod
    def create_session(db: Session, obj_in: ChatSessionCreate) -> ChatSession:
        db_obj = ChatSession(title=obj_in.title)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    @staticmethod
    def get_session_messages(db: Session, session_id: uuid.UUID) -> List[ChatMessage]:
        return db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()).all()

    @staticmethod
    def create_message(db: Session, session_id: uuid.UUID, obj_in: ChatMessageCreate) -> ChatMessage:
        # Create user message
        user_msg = ChatMessage(
            session_id=session_id,
            role="user",
            content=obj_in.content
        )
        db.add(user_msg)
        db.commit()
        db.refresh(user_msg)

        # Generate assistant response
        assistant_reply = (
            "Datadog MCP not connected yet.\n"
            "AWS Bedrock not connected yet.\n\n"
            "Future analysis will run through:\n"
            "- Datadog MCP\n"
            "- AWS Bedrock"
        )
        
        assistant_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=assistant_reply
        )
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)

        return assistant_msg
