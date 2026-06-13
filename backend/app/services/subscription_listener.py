import asyncio
import contextlib

import uvicorn

from backend.app.core.config import Settings
from backend.app.services.logs import write_activity_log
from backend.app.services.subscriptions import local_subscription_config
from backend.app.subscription_main import create_subscription_app


class LocalSubscriptionListener:
    def __init__(self, settings: Settings, *, host: str = "0.0.0.0", poll_seconds: int = 3) -> None:
        self.settings = settings
        self.host = host
        self.poll_seconds = poll_seconds
        self.server: uvicorn.Server | None = None
        self.server_task: asyncio.Task | None = None
        self.current_port: int | None = None

    async def run(self) -> None:
        try:
            while True:
                await self.sync()
                await asyncio.sleep(self.poll_seconds)
        finally:
            await self.stop_server()

    async def sync(self) -> None:
        config = await asyncio.to_thread(local_subscription_config, self.settings)
        enabled = bool(config.get("enabled"))
        port = int(config.get("port") or 10883)

        if enabled:
            if self.server_task and self.server_task.done():
                await self.log("failed", f"本地订阅监听异常退出：{self.current_port}")
                self.server_task = None
                self.server = None
                self.current_port = None
            if self.current_port != port or not self.server_task:
                await self.stop_server()
                await self.start_server(port)
            return

        if self.server_task:
            await self.stop_server()

    async def start_server(self, port: int) -> None:
        app = create_subscription_app(self.settings)
        uvicorn_config = uvicorn.Config(
            app,
            host=self.host,
            port=port,
            log_level="info",
            lifespan="on",
        )
        self.server = uvicorn.Server(uvicorn_config)
        self.current_port = port
        self.server_task = asyncio.create_task(self.server.serve())
        await self.log("success", f"本地订阅监听已启动：{self.host}:{port}")

    async def stop_server(self) -> None:
        if not self.server_task:
            self.server = None
            self.current_port = None
            return

        port = self.current_port
        if self.server:
            self.server.should_exit = True

        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self.server_task, timeout=8)

        if not self.server_task.done():
            self.server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.server_task

        self.server_task = None
        self.server = None
        self.current_port = None
        await self.log("success", f"本地订阅监听已停止：{port}")

    async def log(self, status: str, summary: str) -> None:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(
                write_activity_log,
                self.settings,
                category="subscription",
                action="listener",
                actor="system",
                target_type="local_subscription",
                status=status,
                summary=summary,
            )
