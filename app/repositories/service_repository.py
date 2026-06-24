from sqlalchemy.orm import Session
from app.models.service import Service
from app.schemas.service import ServiceCreate, ServiceUpdate
from typing import List, Optional
import uuid

class ServiceRepository:
    @staticmethod
    def get_all(db: Session) -> List[Service]:
        return db.query(Service).order_by(Service.name).all()

    @staticmethod
    def get_by_id(db: Session, service_id: uuid.UUID) -> Optional[Service]:
        return db.query(Service).filter(Service.id == service_id).first()

    @staticmethod
    def create(db: Session, obj_in: ServiceCreate) -> Service:
        db_obj = Service(
            name=obj_in.name,
            description=obj_in.description,
            environment=obj_in.environment,
            owner=obj_in.owner,
            status=obj_in.status
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    @staticmethod
    def update(db: Session, db_obj: Service, obj_in: ServiceUpdate) -> Service:
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    @staticmethod
    def delete(db: Session, service_id: uuid.UUID) -> bool:
        db_obj = db.query(Service).filter(Service.id == service_id).first()
        if not db_obj:
            return False
        db.delete(db_obj)
        db.commit()
        return True
