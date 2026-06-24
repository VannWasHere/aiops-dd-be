from pydantic import BaseModel, Field
from datetime import datetime
import uuid
from typing import Optional

class ServiceBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    environment: str = Field(..., max_length=100)
    owner: str = Field(..., max_length=255)
    status: str = Field(..., max_length=50)

class ServiceCreate(ServiceBase):
    pass

class ServiceUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    environment: Optional[str] = Field(None, max_length=100)
    owner: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(None, max_length=50)

class ServiceInDBBase(ServiceBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ServiceOut(ServiceInDBBase):
    pass
