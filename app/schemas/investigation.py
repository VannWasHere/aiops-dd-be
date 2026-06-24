from pydantic import BaseModel, Field
from datetime import datetime
import uuid
from typing import List, Optional
from app.schemas.service import ServiceOut

class InvestigationTimelineOut(BaseModel):
    id: uuid.UUID
    investigation_id: uuid.UUID
    event_time: datetime
    title: str
    description: str

    class Config:
        from_attributes = True

class RecommendationOut(BaseModel):
    id: uuid.UUID
    investigation_id: uuid.UUID
    title: str
    description: str
    priority: str

    class Config:
        from_attributes = True

class EvidenceOut(BaseModel):
    id: uuid.UUID
    investigation_id: uuid.UUID
    source: str
    details: str

    class Config:
        from_attributes = True

class InvestigationBase(BaseModel):
    title: str = Field(..., max_length=255)
    question: str
    service_id: uuid.UUID

class InvestigationCreate(InvestigationBase):
    pass

class InvestigationUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    question: Optional[str] = None
    status: Optional[str] = Field(None, max_length=50)
    summary: Optional[str] = None
    root_cause: Optional[str] = None

class InvestigationInDBBase(InvestigationBase):
    id: uuid.UUID
    status: str
    summary: Optional[str] = None
    root_cause: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class InvestigationOut(InvestigationInDBBase):
    pass

class InvestigationDetailedOut(InvestigationInDBBase):
    service: Optional[ServiceOut] = None
    timeline: List[InvestigationTimelineOut] = []
    recommendations: List[RecommendationOut] = []
    evidence: List[EvidenceOut] = []
