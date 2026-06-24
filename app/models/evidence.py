import uuid
from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    investigation_id = Column(UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(255), nullable=False) # e.g. Datadog Metrics, AWS CloudWatch Logs, APM Trace
    details = Column(Text, nullable=False)

    # Relationships
    investigation = relationship("Investigation", back_populates="evidence")
