from dataclasses import dataclass, field
from typing import Dict, List
import os
from pathlib import Path


def _load_env_file() -> None:
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    app_name: str = "SubSentry API"
    app_version: str = "0.1.1"
    db_type: str = "sqlite"
    sqlite_file: str = "subsentry.db"
    mysql_config: Dict[str, object] = field(default_factory=dict)
    secret_key: str = "change-me-to-a-long-random-string"
    admin_user: str = "admin"
    admin_pass: str = "change-me"
    cron_token: str = "change-me"
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True
    csrf_enabled: bool = True
    csrf_trusted_origins: List[str] = field(default_factory=list)
    session_same_site: str = "lax"
    session_https_only: bool = False
    allow_private_targets: bool = True
    onauth_base_url: str = ""
    onauth_client_id: str = ""
    onauth_client_secret: str = ""
    onauth_scope: str = "read"
    onauth_verify_ssl: bool = True
    turnstile_enabled: bool = True
    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""
    node_probe_enabled: bool = True
    node_probe_interval_seconds: int = 300
    dashboard_cache_ttl_seconds: int = 20
    public_subscription_base_url: str = "http://127.0.0.1:10883"
    available_nodes: List[str] = field(default_factory=list)
    default_managers: List[str] = field(default_factory=list)
    default_webhook_url: str = ""
    default_notification_template: str = (
        "### <font color=\"warning\">SubSentry 到期提醒</font>\n"
        "> 客户：<font color=\"info\">{name}</font>\n"
        "> 客户经理：{manager}\n"
        "> 节点：{node}\n"
        "> 续费价：{price}\n"
        "> 到期日：<font color=\"warning\">{expiry}</font>\n"
        "> 剩余：<font color=\"warning\">{rem}</font>\n"
        "> 状态：<font color=\"warning\">{status}</font>\n"
        "> 流量：{traffic}\n"
        "> 检测时间：<font color=\"comment\">{time}</font>\n\n"
        "请及时跟进续费。"
    )
    default_push_mode: str = "summary"
    default_max_detail_rows: int = 30
    default_fixed_push_time: str = "09:00"
    default_push_time_enabled: str = "0"
    default_push_time_window_minutes: int = 20


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(value, minimum)
    return value


def load_settings() -> Settings:
    _load_env_file()
    db_type = (os.getenv("SUBSENTRY_DB_TYPE") or os.getenv("DB_TYPE") or "sqlite").strip().lower()
    mysql_config = {
        "host": os.getenv("SUBSENTRY_MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("SUBSENTRY_MYSQL_PORT", "3306")),
        "user": os.getenv("SUBSENTRY_MYSQL_USER", "subsentry"),
        "password": os.getenv("SUBSENTRY_MYSQL_PASSWORD", ""),
        "database": os.getenv("SUBSENTRY_MYSQL_DATABASE", "subsentry"),
        "charset": "utf8mb4",
    }
    cors_origins = [x.strip() for x in (os.getenv("SUBSENTRY_CORS_ORIGINS", "*").split(",")) if x.strip()]
    if not cors_origins:
        cors_origins = ["*"]
    csrf_trusted_origins = [x.strip().rstrip("/") for x in (os.getenv("SUBSENTRY_CSRF_TRUSTED_ORIGINS", "").split(",")) if x.strip()]
    session_same_site = (os.getenv("SUBSENTRY_SESSION_SAME_SITE", "lax") or "lax").strip().lower()
    if session_same_site not in ("lax", "strict", "none"):
        session_same_site = "lax"

    return Settings(
        app_name=os.getenv("SUBSENTRY_APP_NAME", "SubSentry API"),
        app_version=os.getenv("SUBSENTRY_APP_VERSION", "0.1.0"),
        db_type=db_type,
        sqlite_file=os.getenv("SUBSENTRY_SQLITE_FILE", "subsentry.db"),
        mysql_config=mysql_config,
        secret_key=os.getenv("SUBSENTRY_SECRET_KEY", "change-me-to-a-long-random-string"),
        admin_user=os.getenv("SUBSENTRY_ADMIN_USER", "admin"),
        admin_pass=os.getenv("SUBSENTRY_ADMIN_PASS", "change-me"),
        cron_token=os.getenv("SUBSENTRY_CRON_TOKEN", "change-me"),
        cors_origins=cors_origins,
        cors_allow_credentials=_env_bool("SUBSENTRY_CORS_ALLOW_CREDENTIALS", True),
        csrf_enabled=_env_bool("SUBSENTRY_CSRF_ENABLED", True),
        csrf_trusted_origins=csrf_trusted_origins,
        session_same_site=session_same_site,
        session_https_only=_env_bool("SUBSENTRY_SESSION_HTTPS_ONLY", False),
        allow_private_targets=_env_bool("SUBSENTRY_ALLOW_PRIVATE_TARGETS", True),
        onauth_base_url=os.getenv("SUBSENTRY_ONAUTH_BASE_URL", "").rstrip("/"),
        onauth_client_id=os.getenv("SUBSENTRY_ONAUTH_CLIENT_ID", ""),
        onauth_client_secret=os.getenv("SUBSENTRY_ONAUTH_CLIENT_SECRET", ""),
        onauth_scope=os.getenv("SUBSENTRY_ONAUTH_SCOPE", "read"),
        onauth_verify_ssl=_env_bool("SUBSENTRY_ONAUTH_VERIFY_SSL", True),
        turnstile_enabled=_env_bool("SUBSENTRY_TURNSTILE_ENABLED", True),
        turnstile_site_key=os.getenv("SUBSENTRY_TURNSTILE_SITE_KEY", "").strip(),
        turnstile_secret_key=os.getenv("SUBSENTRY_TURNSTILE_SECRET_KEY", "").strip(),
        node_probe_enabled=_env_bool("SUBSENTRY_NODE_PROBE_ENABLED", True),
        node_probe_interval_seconds=_env_int("SUBSENTRY_NODE_PROBE_INTERVAL_SECONDS", 300, 30),
        dashboard_cache_ttl_seconds=_env_int("SUBSENTRY_DASHBOARD_CACHE_TTL_SECONDS", 20, 0),
        public_subscription_base_url=os.getenv("SUBSENTRY_PUBLIC_SUBSCRIPTION_BASE_URL", "http://127.0.0.1:10883").rstrip("/"),
        default_webhook_url=os.getenv("SUBSENTRY_DEFAULT_WEBHOOK_URL", "").strip(),
    )
