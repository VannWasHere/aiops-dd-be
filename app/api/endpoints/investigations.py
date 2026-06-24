from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.investigation import InvestigationCreate, InvestigationUpdate, InvestigationOut, InvestigationDetailedOut
from app.repositories.investigation_repository import InvestigationRepository
from typing import List
import uuid

router = APIRouter()

@router.get("/", response_model=List[InvestigationOut])
def read_investigations(db: Session = Depends(get_db)):
    return InvestigationRepository.get_all(db)

@router.get("/{id}", response_model=InvestigationDetailedOut)
def read_investigation(id: uuid.UUID, db: Session = Depends(get_db)):
    db_obj = InvestigationRepository.get_by_id(db, id)
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation not found"
        )
    return db_obj

@router.post("/", response_model=InvestigationDetailedOut, status_code=status.HTTP_201_CREATED)
def create_investigation(investigation_in: InvestigationCreate, db: Session = Depends(get_db)):
    return InvestigationRepository.create(db, investigation_in)

@router.put("/{id}", response_model=InvestigationOut)
def update_investigation(id: uuid.UUID, investigation_in: InvestigationUpdate, db: Session = Depends(get_db)):
    db_obj = InvestigationRepository.get_by_id(db, id)
    if not db_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation not found"
        )
    return InvestigationRepository.update(db, db_obj, investigation_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_investigation(id: uuid.UUID, db: Session = Depends(get_db)):
    success = InvestigationRepository.delete(db, id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigation not found"
        )
    return None
