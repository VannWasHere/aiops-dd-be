import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Investigation(Base):
    __tablename__ = "investigations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    question = Column(Text, nullable=False)
    status = Column(String(50), nullable=False) # e.g. investigating, resolved, closed
    summary = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    service = relationship("Service", backref="investigations")
    timeline = relationship("InvestigationTimeline", back_populates="investigation", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="investigation", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="investigation", cascade="all, delete-orphan")
