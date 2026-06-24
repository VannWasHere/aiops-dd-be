from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.chat import ChatSessionCreate, ChatSessionOut, ChatMessageCreate, ChatMessageOut
from app.repositories.chat_repository import ChatRepository
from typing import List
import uuid

router = APIRouter()

@router.get("/sessions", response_model=List[ChatSessionOut])
def read_chat_sessions(db: Session = Depends(get_db)):
    return ChatRepository.get_sessions(db)

@router.post("/sessions", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
def create_chat_session(session_in: ChatSessionCreate, db: Session = Depends(get_db)):
    return ChatRepository.create_session(db, session_in)

@router.get("/sessions/{id}/messages", response_model=List[ChatMessageOut])
def read_chat_messages(id: uuid.UUID, db: Session = Depends(get_db)):
    return ChatRepository.get_session_messages(db, id)

@router.post("/sessions/{id}/messages", response_model=ChatMessageOut, status_code=status.HTTP_201_CREATED)
def create_chat_message(id: uuid.UUID, message_in: ChatMessageCreate, db: Session = Depends(get_db)):
    return ChatRepository.create_message(db, id, message_in)
