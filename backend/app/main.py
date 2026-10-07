"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import files
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.db import models  # noqa: F401  (registers tables on Base.metadata)
from app.db.database import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Create the upload folder and database tables on startup."""
    get_settings().upload_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = FastAPI(
        title=settings.app_name,
        description=(
            "Upload a KML or zipped Shapefile and get the area of every polygon and the "
            "length of every line, always calculated in a metric projected CRS."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    # Added last so it is the outermost middleware and also covers error responses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(files.router)
    return app


app = create_app()
