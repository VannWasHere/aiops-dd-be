from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.config import settings
from app.core.database import get_db
from app.api.router import api_router

app = FastAPI(
    title="Cable3 Ops API",
    description="Backend for Cable3 Ops - AI-powered incident investigation platform",
    version="1.0.0"
)

# Set up CORS middleware to allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to actual origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["health"])
def health_check(db: Session = Depends(get_db)):
    db_status = "healthy"
    try:
        # Execute simple query to verify database connection
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return {
        "status": "online",
        "database": db_status
    }

# Register the routes router
app.include_router(api_router)
