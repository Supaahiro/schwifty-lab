"""Application entry point.

All bootstrap lives in build_app(); importing this module performs no I/O so
tests can build isolated apps and `uvicorn main:app` still works out of the box.
"""

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import router as api_router
from core.config import Settings
from core.pdns import PdnsError


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.http = httpx.AsyncClient(
            base_url=settings.pdns_api_url,
            headers={"X-API-Key": settings.pdns_api_key},
            timeout=10.0,
        )
        yield
        await app.state.http.aclose()

    app = FastAPI(title="pdns-admin-lite", lifespan=lifespan)
    app.state.settings = settings

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(PdnsError)
    async def pdns_error_handler(request: Request, exc: PdnsError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.include_router(api_router, prefix="/api")
    return app


app = build_app()
