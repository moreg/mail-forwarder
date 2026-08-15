from fastapi import APIRouter
from app.api.emails import router as emails_router
from app.api.codes import router as codes_router
from app.api.webhook import router as webhook_router
from app.api.stream import router as stream_router
from app.api.stats import router as stats_router
from app.api.config_api import router as config_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(emails_router)
api_router.include_router(codes_router)
api_router.include_router(webhook_router)
api_router.include_router(stream_router)
api_router.include_router(stats_router)
api_router.include_router(config_router)
