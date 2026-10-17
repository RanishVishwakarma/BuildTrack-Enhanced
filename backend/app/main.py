from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.indexes import ensure_indexes
from app.db.mongodb import database, mongo_client, ping_database
from app.modules.monitoring import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: Check database connection
    try:
        await ping_database()
        print("[OK] Database connection successful!")
        await ensure_indexes(database)
        scheduler.start(database)
    except Exception as e:
        print(f"[ERROR] Database connection failed: {str(e)}")

    yield

    # Shutdown: stop background jobs, then close the connection
    await scheduler.stop()
    mongo_client.close()
    print("[INFO] Database connection closed.")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", tags=["Root"])
    async def root():
        return {
            "message": "BuildTrack Backend Running",
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health", tags=["Health"])
    async def health_check():
        return {
            "status": "ok",
            "service": settings.app_name,
        }

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()