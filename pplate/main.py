"""FastAPI application factory and entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pplate import __version__
from pplate.config import get_settings
from pplate.db import init_db
from pplate.routes import api_cars, api_tools, ui

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.auto_create_tables:
        # Idempotent: safe alongside `alembic upgrade head`.
        init_db()
        logging.getLogger("pplate").info("Database tables ensured.")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version=__version__,
        lifespan=lifespan,
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(api_cars.router)
    app.include_router(api_tools.router)
    app.include_router(ui.router)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
