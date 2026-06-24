from sqlalchemy.orm import Session
from app.models.investigation import Investigation
from app.models.service import Service
from app.schemas.investigation import InvestigationCreate, InvestigationUpdate
from app.services.mock_investigator import generate_investigation_details
from typing import List, Optional
import uuid

class InvestigationRepository:
    @staticmethod
    def get_all(db: Session) -> List[Investigation]:
        return db.query(Investigation).order_by(Investigation.created_at.desc()).all()

    @staticmethod
    def get_by_id(db: Session, investigation_id: uuid.UUID) -> Optional[Investigation]:
        return db.query(Investigation).filter(Investigation.id == investigation_id).first()

    @staticmethod
    def create(db: Session, obj_in: InvestigationCreate) -> Investigation:
        # Create investigation object
        db_obj = Investigation(
            service_id=obj_in.service_id,
            title=obj_in.title,
            question=obj_in.question,
            status="created",
            summary="",
            root_cause=""
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)

        # Retrieve service name for mock investigator
        service = db.query(Service).filter(Service.id == obj_in.service_id).first()
        service_name = service.name if service else "unknown-service"

        # Generate mock details and save to database
        db_obj = generate_investigation_details(db, db_obj, service_name)
        return db_obj

    @staticmethod
    def update(db: Session, db_obj: Investigation, obj_in: InvestigationUpdate) -> Investigation:
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    @staticmethod
    def delete(db: Session, investigation_id: uuid.UUID) -> bool:
        db_obj = db.query(Investigation).filter(Investigation.id == investigation_id).first()
        if not db_obj:
            return False
        db.delete(db_obj)
        db.commit()
        return True
