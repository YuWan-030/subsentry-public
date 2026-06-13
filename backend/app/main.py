import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.cron import router as cron_router
from backend.app.api.v1.customers import router as customers_router
from backend.app.api.v1.dashboard import router as dashboard_router
from backend.app.api.v1.install import router as install_router
from backend.app.api.v1.logs import router as logs_router
from backend.app.api.v1.settings import router as settings_router
from backend.app.api.v1.system import router as system_router
from backend.app.core.config import Settings, load_settings
from backend.app.db.database import ensure_default_settings, init_db
from backend.app.services.settings import probe_all_nodes
from backend.app.services.logs import write_activity_log
from backend.app.services.subscription_listener import LocalSubscriptionListener


routers = [install_router, auth_router, dashboard_router, customers_router, settings_router, cron_router, logs_router, system_router]


def create_app() -> FastAPI:
    settings: Settings = load_settings()

    async def node_probe_loop() -> None:
        interval = settings.node_probe_interval_seconds
        while True:
            await asyncio.sleep(interval)
            try:
                await asyncio.to_thread(probe_all_nodes, settings)
            except Exception as exc:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(
                        write_activity_log,
                        settings,
                        category="node",
                        action="auto_probe",
                        actor="system",
                        target_type="node",
                        status="failed",
                        summary="节点自动探测任务异常",
                        detail=str(exc),
                    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(settings)
        ensure_default_settings(settings)
        probe_task: asyncio.Task | None = None
        subscription_listener = LocalSubscriptionListener(settings)
        subscription_task = asyncio.create_task(subscription_listener.run())
        if settings.node_probe_enabled:
            probe_task = asyncio.create_task(node_probe_loop())
        try:
            yield
        finally:
            subscription_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await subscription_task
            if probe_task:
                probe_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await probe_task

    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins if settings.cors_origins != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=False)

    for router in routers:
        app.include_router(router)


    @app.get("/")
    def root():
        return {"success": True, "message": "SubSentry API is running", "version": settings.app_version}

    @app.get("/api/v1/health")
    def health():
        return {"success": True, "status": "ok"}

    return app


app = create_app()
