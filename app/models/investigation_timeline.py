import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class InvestigationTimeline(Base):
    __tablename__ = "investigation_timelines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id = Column(UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False)
    event_time = Column(DateTime, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    # Relationships
    investigation = relationship("Investigation", back_populates="timeline")
