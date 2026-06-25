"""
Optional password authentication middleware.
Enable by setting APP_PASSWORD environment variable.
"""
import os
import base64
import logging
from typing import Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")


class BasicAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, password: str):
        super().__init__(app)
        self.password = password

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Skip auth for non-API routes (frontend assets, index.html, etc.)
        if not path.startswith("/api/"):
            return await call_next(request)



        # 1. Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                _, pwd = decoded.split(":", 1)
                if pwd == self.password:
                    return await call_next(request)
            except Exception:
                pass

        # 2. Check query parameter 'pwd' (useful for direct downloads and audio elements)
        pwd_param = request.query_params.get("pwd", "")
        if pwd_param == self.password:
            return await call_next(request)

        # Return a clean 403 JSON response instead of 401
        # to definitively prevent the browser from popping up its native login modal
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Authentication required"}
        )


def get_auth_middleware() -> Optional[BasicAuthMiddleware]:
    if APP_PASSWORD:
        logger.info("Password protection enabled")
        return BasicAuthMiddleware
    return None

