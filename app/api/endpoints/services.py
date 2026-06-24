from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.service import ServiceCreate, ServiceUpdate, ServiceOut
from app.repositories.service_repository import ServiceRepository
from typing import List
import uuid

router = APIRouter()

@router.get("/", response_model=List[ServiceOut])
def read_services(db: Session = Depends(get_db)):
    return ServiceRepository.get_all(db)

@router.get("/{id}", response_model=ServiceOut)
def read_service(id: uuid.UUID, db: Session = Depends(get_db)):
    db_obj = ServiceRepository.get_by_id(db, id)
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )
    return db_obj

@router.post("/", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(service_in: ServiceCreate, db: Session = Depends(get_db)):
    return ServiceRepository.create(db, service_in)

@router.put("/{id}", response_model=ServiceOut)
def update_service(id: uuid.UUID, service_in: ServiceUpdate, db: Session = Depends(get_db)):
    db_obj = ServiceRepository.get_by_id(db, id)
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )
    return ServiceRepository.update(db, db_obj, service_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(id: uuid.UUID, db: Session = Depends(get_db)):
    success = ServiceRepository.delete(db, id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )
    return None
