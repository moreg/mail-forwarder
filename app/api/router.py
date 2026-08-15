from fastapi import APIRouter, Depends
from app.core.auth import require_auth
from app.api.auth import router as auth_router
from app.api.emails import router as emails_router
from app.api.codes import router as codes_router
from app.api.webhook import router as webhook_router
from app.api.stream import router as stream_router
from app.api.stats import router as stats_router
from app.api.config_api import router as config_router

from app.api.groups import router as groups_router
from app.api.guest import router as guest_router

api_router = APIRouter(prefix="/api/v1")

# Public routes (免鉴权)
api_router.include_router(auth_router)
api_router.include_router(webhook_router)
api_router.include_router(guest_router)

# Protected routes (当配置了 admin_password 或 api_key 时强制校验鉴权)
api_router.include_router(emails_router, dependencies=[Depends(require_auth)])
api_router.include_router(codes_router, dependencies=[Depends(require_auth)])
api_router.include_router(groups_router, dependencies=[Depends(require_auth)])
api_router.include_router(stream_router, dependencies=[Depends(require_auth)])
api_router.include_router(stats_router, dependencies=[Depends(require_auth)])
api_router.include_router(config_router, dependencies=[Depends(require_auth)])

