from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException, Request, status

from backend.app.core.config import Settings
from backend.app.core.deps import SESSION_LOGIN_KEY, SESSION_ROLE_KEY, SESSION_USER_KEY
from backend.app.core.security import hash_password
from backend.app.db.database import execute, get_connection, get_setting, query, scalar, upsert_setting
from backend.app.services.logs import write_activity_log


ENV_KEYS = {
    "SUBSENTRY_DB_TYPE",
    "SUBSENTRY_SQLITE_FILE",
    "SUBSENTRY_MYSQL_HOST",
    "SUBSENTRY_MYSQL_PORT",
    "SUBSENTRY_MYSQL_USER",
    "SUBSENTRY_MYSQL_PASSWORD",
    "SUBSENTRY_MYSQL_DATABASE",
    "SUBSENTRY_PUBLIC_SUBSCRIPTION_BASE_URL",
}


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _project_env_path() -> Path:
    return Path.cwd() / ".env"


def _admin_count(settings: Settings) -> int:
    try:
        return int(scalar(settings, "SELECT COUNT(1) AS cnt FROM users WHERE role = 'admin'", default=0) or 0)
    except Exception:
        return 0


def is_setup_required(settings: Settings) -> bool:
    return _admin_count(settings) == 0 and get_setting(settings, "setup_completed", "0") != "1"


def install_status(settings: Settings) -> Dict[str, Any]:
    admin_count = _admin_count(settings)
    return {
        "required": admin_count == 0 and get_setting(settings, "setup_completed", "0") != "1",
        "completed": get_setting(settings, "setup_completed", "0") == "1" or admin_count > 0,
        "admin_count": admin_count,
        "database": {
            "type": settings.db_type,
            "sqlite_file": settings.sqlite_file if settings.db_type == "sqlite" else "",
            "mysql": {
                "host": settings.mysql_config.get("host", ""),
                "port": settings.mysql_config.get("port", 3306),
                "user": settings.mysql_config.get("user", ""),
                "database": settings.mysql_config.get("database", ""),
            },
        },
        "site_url": get_setting(settings, "site_url", settings.public_subscription_base_url),
        "webhook_configured": bool(get_setting(settings, "default_webhook_url", "")),
    }


def _quote_env_value(value: Any) -> str:
    text = str(value or "")
    if not text or any(ch.isspace() for ch in text) or any(ch in text for ch in ['"', "#", "="]):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def _write_env(updates: Dict[str, Any]) -> None:
    env_path = _project_env_path()
    existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    next_lines: list[str] = []
    seen: set[str] = set()
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            next_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            next_lines.append(f"{key}={_quote_env_value(updates[key])}")
            seen.add(key)
        else:
            next_lines.append(line)
    if next_lines and next_lines[-1].strip():
        next_lines.append("")
    for key, value in updates.items():
        if key not in seen:
            next_lines.append(f"{key}={_quote_env_value(value)}")
    env_path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")


def _settings_from_database_payload(settings: Settings, payload: Dict[str, Any]) -> Settings:
    db_type = str(payload.get("db_type") or "sqlite").strip().lower()
    if db_type not in ("sqlite", "mysql"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="数据库类型只支持 sqlite 或 mysql")
    if db_type == "sqlite":
        sqlite_file = str(payload.get("sqlite_file") or "subsentry.db").strip()
        if not sqlite_file:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SQLite 文件路径不能为空")
        return replace(settings, db_type="sqlite", sqlite_file=sqlite_file)

    mysql_config = {
        "host": str(payload.get("mysql_host") or "").strip(),
        "port": int(payload.get("mysql_port") or 3306),
        "user": str(payload.get("mysql_user") or "").strip(),
        "password": str(payload.get("mysql_password") or ""),
        "database": str(payload.get("mysql_database") or "").strip(),
        "charset": "utf8mb4",
    }
    if not mysql_config["host"] or not mysql_config["user"] or not mysql_config["password"] or not mysql_config["database"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MySQL 主机、用户、密码和数据库名不能为空")
    return replace(settings, db_type="mysql", mysql_config=mysql_config)


def test_database_payload(settings: Settings, payload: Dict[str, Any]) -> Dict[str, Any]:
    candidate = _settings_from_database_payload(settings, payload)
    try:
        conn = get_connection(candidate)
        conn.close()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"数据库连接失败：{exc}") from exc
    return {"success": True, "message": "数据库连接正常"}


def save_database_config(settings: Settings, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not is_setup_required(settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="系统已安装，数据库配置请通过部署环境修改")
    candidate = _settings_from_database_payload(settings, payload)
    test_database_payload(settings, payload)

    updates: Dict[str, Any] = {"SUBSENTRY_DB_TYPE": candidate.db_type}
    if candidate.db_type == "sqlite":
        updates["SUBSENTRY_SQLITE_FILE"] = candidate.sqlite_file
    else:
        updates.update(
            {
                "SUBSENTRY_MYSQL_HOST": candidate.mysql_config["host"],
                "SUBSENTRY_MYSQL_PORT": candidate.mysql_config["port"],
                "SUBSENTRY_MYSQL_USER": candidate.mysql_config["user"],
                "SUBSENTRY_MYSQL_PASSWORD": candidate.mysql_config["password"],
                "SUBSENTRY_MYSQL_DATABASE": candidate.mysql_config["database"],
            }
        )
    _write_env(updates)

    restart_required = candidate.db_type != settings.db_type
    if candidate.db_type == "sqlite":
        restart_required = restart_required or candidate.sqlite_file != settings.sqlite_file
    else:
        restart_required = restart_required or any(candidate.mysql_config.get(key) != settings.mysql_config.get(key) for key in ("host", "port", "user", "password", "database"))
    return {
        "success": True,
        "message": "数据库配置已写入 .env" + ("，请重启后继续安装" if restart_required else ""),
        "restart_required": restart_required,
        "database": install_status(candidate)["database"],
    }


def complete_install(settings: Settings, request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not is_setup_required(settings):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="系统已完成安装")

    username = str(payload.get("admin_username") or "").strip()
    password = str(payload.get("admin_password") or "")
    nickname = str(payload.get("admin_nickname") or "").strip()
    site_url = str(payload.get("site_url") or settings.public_subscription_base_url).strip().rstrip("/")
    webhook_url = str(payload.get("webhook_url") or "").strip()

    if not username or not password.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员账号和密码不能为空")
    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员密码至少需要 8 位")
    if query(settings, "SELECT id FROM users WHERE username = ? LIMIT 1", (username,)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员账号已存在")

    execute(
        settings,
        "INSERT INTO users (username, nickname, password_hash, role, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (username, nickname, hash_password(password), "admin", 1, _now_text()),
    )
    upsert_setting(settings, "setup_completed", "1")
    upsert_setting(settings, "setup_completed_at", _now_text())
    upsert_setting(settings, "site_url", site_url)
    upsert_setting(settings, "local_subscription_base_url", site_url)
    upsert_setting(settings, "default_webhook_url", webhook_url)
    write_activity_log(
        settings,
        category="settings",
        action="install_complete",
        actor=username,
        target_type="system",
        status="success",
        summary="完成安装向导",
        detail={"site_url": site_url, "webhook_configured": bool(webhook_url), "database": settings.db_type},
        ip_address=request.client.host if request.client else "",
    )

    request.session[SESSION_LOGIN_KEY] = True
    request.session[SESSION_USER_KEY] = username
    request.session[SESSION_ROLE_KEY] = "admin"
    request.session["nickname"] = nickname
    return {
        "success": True,
        "message": "安装完成",
        "data": {"username": username, "nickname": nickname, "role": "admin"},
    }
