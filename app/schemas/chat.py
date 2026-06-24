from pydantic import BaseModel, Field
from datetime import datetime
import uuid
from typing import Optional

class ChatMessageBase(BaseModel):
    content: str

class ChatMessageCreate(ChatMessageBase):
    pass

class ChatMessageOut(ChatMessageBase):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    created_at: datetime

    class Config:
        from_attributes = True

class ChatSessionBase(BaseModel):
    title: str = Field(..., max_length=255)

class ChatSessionCreate(ChatSessionBase):
    pass

class ChatSessionOut(ChatSessionBase):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True
