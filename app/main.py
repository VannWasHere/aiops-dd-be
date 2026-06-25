import logging
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from ddtrace.llmobs import LLMObs
from app.core.config import settings
from app.core.database import get_db
from app.api.router import api_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Cable3 Ops API",
    description="Backend for Cable3 Ops - AI-powered incident investigation platform",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Initialize LLM Observability on application startup."""
    if settings.DD_API_KEY:
        LLMObs.enable(
            ml_app=settings.DD_LLMOBS_ML_APP,
            agentless_enabled=True,
            api_key=settings.DD_API_KEY,
            site=settings.DD_SITE
        )
        logger.info("Datadog LLM Observability enabled")
    else:
        logger.warning("Datadog LLM Observability not configured (DD_API_KEY missing)")

@app.on_event("shutdown")
async def shutdown_event():
    """Flush remaining traces on application shutdown."""
    if settings.DD_API_KEY:
        try:
            LLMObs.flush()
            logger.info("Flushed LLM Observability traces")
        except Exception as e:
            logger.error(f"Error flushing LLMObs traces: {e}")


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
