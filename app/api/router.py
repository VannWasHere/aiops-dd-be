from fastapi import APIRouter
from app.api.endpoints import services, investigations, chat, test, traces, bedrock_usage, dashboards

api_router = APIRouter()

api_router.include_router(services.router, prefix="/services", tags=["services"])
api_router.include_router(investigations.router, prefix="/investigations", tags=["investigations"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(test.router, prefix="/test", tags=["test"])
api_router.include_router(traces.router, prefix="/traces", tags=["traces"])
api_router.include_router(bedrock_usage.router, prefix="/bedrock-usage", tags=["bedrock-usage"])
api_router.include_router(dashboards.router, prefix="/dashboards", tags=["dashboards"])
