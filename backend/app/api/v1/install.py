from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.app.core.config import Settings
from backend.app.services.installer import complete_install, install_status, save_database_config, test_database_payload


router = APIRouter(prefix="/api/v1/install", tags=["install"])


class DatabasePayload(BaseModel):
    db_type: str = "sqlite"
    sqlite_file: str | None = "subsentry.db"
    mysql_host: str | None = None
    mysql_port: int | None = 3306
    mysql_user: str | None = None
    mysql_password: str | None = None
    mysql_database: str | None = None


class CompletePayload(BaseModel):
    admin_username: str
    admin_password: str
    admin_nickname: str | None = None
    site_url: str | None = None
    webhook_url: str | None = None


def _ensure_install_open(settings: Settings) -> None:
    if not install_status(settings).get("required"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="系统已完成安装")


@router.get("/status")
def status(request: Request):
    settings: Settings = request.app.state.settings
    return {"success": True, "data": install_status(settings)}


@router.post("/database/test")
def test_database(request: Request, payload: DatabasePayload):
    settings: Settings = request.app.state.settings
    _ensure_install_open(settings)
    return test_database_payload(settings, payload.model_dump())


@router.post("/database")
def save_database(request: Request, payload: DatabasePayload):
    settings: Settings = request.app.state.settings
    _ensure_install_open(settings)
    return save_database_config(settings, payload.model_dump())


@router.post("/complete")
def complete(request: Request, payload: CompletePayload):
    settings: Settings = request.app.state.settings
    _ensure_install_open(settings)
    return complete_install(settings, request, payload.model_dump())
