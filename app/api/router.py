from fastapi import APIRouter
from app.api.endpoints import services, investigations, chat

api_router = APIRouter()

api_router.include_router(services.router, prefix="/services", tags=["services"])
api_router.include_router(investigations.router, prefix="/investigations", tags=["investigations"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
