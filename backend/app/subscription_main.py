from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.v1.subscriptions import router as subscriptions_router
from backend.app.core.config import Settings, load_settings
from backend.app.db.database import ensure_default_settings, init_db


def create_subscription_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(settings)
        ensure_default_settings(settings)
        yield

    app = FastAPI(title=f"{settings.app_name} Subscription", version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    app.include_router(subscriptions_router)

    @app.get("/")
    def root():
        return {"success": True, "message": "SubSentry subscription service is running", "version": settings.app_version}

    @app.get("/health")
    def health():
        return {"success": True, "status": "ok"}

    return app


app = create_subscription_app()
