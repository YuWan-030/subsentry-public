import sqlite3
import os
from contextlib import closing
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Sequence

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:  # pragma: no cover
    pymysql = None
    DictCursor = None

from backend.app.core.config import Settings
from backend.app.core.security import hash_password


def _placeholder(db_type: str) -> str:
    return "%s" if db_type == "mysql" else "?"


def _ensure_mysql_index(cursor, table_name: str, index_name: str, ddl: str) -> None:
    cursor.execute(f"SHOW INDEX FROM {table_name} WHERE Key_name = %s", (index_name,))
    if not cursor.fetchone():
        cursor.execute(ddl)


def get_connection(settings: Settings):
    if settings.db_type == "mysql":
        if pymysql is None:
            raise RuntimeError("配置为 mysql，但未安装 pymysql")
        return pymysql.connect(**settings.mysql_config, cursorclass=DictCursor)
    conn = sqlite3.connect(settings.sqlite_file)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_db_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def _normalize_db_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {key: _normalize_db_value(value) for key, value in row.items()}


def _rows_to_dicts(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    return [_normalize_db_row(dict(r)) for r in rows]


def query(settings: Settings, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    conn = get_connection(settings)
    sql = sql.replace("?", _placeholder(settings.db_type))
    try:
        if settings.db_type == "mysql":
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return [_normalize_db_row(dict(row)) for row in cursor.fetchall()]
        with closing(conn.cursor()) as cursor:
            cursor.execute(sql, params)
            return _rows_to_dicts(cursor.fetchall())
    finally:
        conn.close()


def execute(settings: Settings, sql: str, params: Sequence[Any] = ()) -> int | None:
    conn = get_connection(settings)
    sql = sql.replace("?", _placeholder(settings.db_type))
    try:
        if settings.db_type == "mysql":
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                lastrowid = cursor.lastrowid
        else:
            with closing(conn.cursor()) as cursor:
                cursor.execute(sql, params)
                lastrowid = cursor.lastrowid
        conn.commit()
        return lastrowid
    finally:
        conn.close()


def scalar(settings: Settings, sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
    rows = query(settings, sql, params)
    if not rows:
        return default
    first = rows[0]
    return next(iter(first.values())) if first else default


def init_db(settings: Settings) -> None:
    conn = get_connection(settings)
    try:
        if settings.db_type == "mysql":
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS customers (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        manager VARCHAR(255) DEFAULT '未分配',
                        node VARCHAR(255) NOT NULL,
                        expiry_date VARCHAR(50) NOT NULL,
                        duration VARCHAR(255) NOT NULL,
                        traffic VARCHAR(255) NOT NULL,
                        renew_price VARCHAR(255) DEFAULT '未设置',
                        webhook_url TEXT,
                        last_notified VARCHAR(50)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute("SHOW COLUMNS FROM customers LIKE 'manager'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE customers ADD COLUMN manager VARCHAR(255) DEFAULT '未分配' AFTER name;")
                cursor.execute("SHOW COLUMNS FROM customers LIKE 'renew_price'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE customers ADD COLUMN renew_price VARCHAR(255) DEFAULT '未设置' AFTER traffic;")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS system_settings (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        `key` VARCHAR(100) NOT NULL UNIQUE,
                        `value` TEXT
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS financial_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        customer_id INT,
                        customer_name VARCHAR(255) NOT NULL,
                        renew_price VARCHAR(255) NOT NULL,
                        amount DECIMAL(12,2) NULL,
                        renew_days INT NOT NULL,
                        new_expiry VARCHAR(50) NOT NULL,
                        created_at DATETIME NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS catalog_nodes (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(255) NOT NULL UNIQUE,
                        created_at DATETIME NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'scheme'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN scheme VARCHAR(16) NOT NULL DEFAULT 'https' AFTER name;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'address'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN address VARCHAR(255) NOT NULL DEFAULT '' AFTER scheme;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'port'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN port INT NOT NULL DEFAULT 443 AFTER address;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'base_path'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN base_path VARCHAR(255) NOT NULL DEFAULT '/' AFTER port;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'api_token'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN api_token TEXT AFTER base_path;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'allow_insecure'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN allow_insecure TINYINT(1) NOT NULL DEFAULT 0 AFTER api_token;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'subscription_scheme'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN subscription_scheme VARCHAR(16) NOT NULL DEFAULT 'https' AFTER allow_insecure;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'subscription_address'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN subscription_address VARCHAR(255) NOT NULL DEFAULT '' AFTER subscription_scheme;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'subscription_port'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN subscription_port INT NOT NULL DEFAULT 10882 AFTER subscription_address;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'subscription_sub_path'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN subscription_sub_path VARCHAR(255) NOT NULL DEFAULT '/sub' AFTER subscription_port;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'subscription_json_path'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN subscription_json_path VARCHAR(255) NOT NULL DEFAULT '/json' AFTER subscription_sub_path;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'subscription_clash_path'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN subscription_clash_path VARCHAR(255) NOT NULL DEFAULT '/clash' AFTER subscription_json_path;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'last_status'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN last_status VARCHAR(32) DEFAULT 'unknown' AFTER allow_insecure;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'last_message'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN last_message TEXT AFTER last_status;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'last_checked_at'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN last_checked_at DATETIME NULL AFTER last_message;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'last_latency_ms'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN last_latency_ms INT NULL AFTER last_checked_at;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'consecutive_failures'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN consecutive_failures INT NOT NULL DEFAULT 0 AFTER last_latency_ms;")
                cursor.execute("SHOW COLUMNS FROM catalog_nodes LIKE 'abnormal_notified_at'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE catalog_nodes ADD COLUMN abnormal_notified_at DATETIME NULL AFTER consecutive_failures;")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS catalog_managers (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(255) NOT NULL UNIQUE,
                        created_at DATETIME NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS remote_customer_profiles (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        node_id INT NOT NULL,
                        node_name VARCHAR(255) NOT NULL,
                        remote_email VARCHAR(255) NOT NULL,
                        display_name VARCHAR(255) NOT NULL,
                        manager VARCHAR(255) DEFAULT '未分配',
                        renew_price VARCHAR(255) DEFAULT '未设置',
                        traffic_multiplier DOUBLE NOT NULL DEFAULT 1,
                        webhook_url TEXT,
                        notes TEXT,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        UNIQUE KEY uniq_node_remote_email (node_id, remote_email)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS customer_audit_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        customer_id INT NOT NULL,
                        customer_name VARCHAR(255) NOT NULL,
                        action VARCHAR(32) NOT NULL,
                        actor VARCHAR(255) NOT NULL,
                        change_summary TEXT NOT NULL,
                        created_at DATETIME NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute("SHOW COLUMNS FROM customer_audit_logs LIKE 'node_id'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE customer_audit_logs ADD COLUMN node_id INT NULL AFTER customer_id;")
                cursor.execute("SHOW COLUMNS FROM customer_audit_logs LIKE 'remote_email'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE customer_audit_logs ADD COLUMN remote_email VARCHAR(255) NULL AFTER node_id;")
                _ensure_mysql_index(cursor, "customer_audit_logs", "idx_customer_audit_lookup", "CREATE INDEX idx_customer_audit_lookup ON customer_audit_logs (node_id, remote_email, action, id)")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS customer_renewal_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        customer_id INT NOT NULL,
                        customer_name VARCHAR(255) NOT NULL,
                        actor VARCHAR(255) NOT NULL,
                        renew_days INT NOT NULL,
                        old_expiry VARCHAR(50) NOT NULL,
                        new_expiry VARCHAR(50) NOT NULL,
                        renew_price VARCHAR(255) NOT NULL,
                        created_at DATETIME NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute("SHOW COLUMNS FROM customer_renewal_logs LIKE 'node_id'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE customer_renewal_logs ADD COLUMN node_id INT NULL AFTER customer_id;")
                cursor.execute("SHOW COLUMNS FROM customer_renewal_logs LIKE 'remote_email'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE customer_renewal_logs ADD COLUMN remote_email VARCHAR(255) NULL AFTER node_id;")
                cursor.execute("SHOW COLUMNS FROM financial_logs LIKE 'node_id'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE financial_logs ADD COLUMN node_id INT NULL AFTER customer_id;")
                cursor.execute("SHOW COLUMNS FROM financial_logs LIKE 'owner_username'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE financial_logs ADD COLUMN owner_username VARCHAR(255) NULL AFTER customer_id;")
                cursor.execute("SHOW COLUMNS FROM financial_logs LIKE 'remote_email'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE financial_logs ADD COLUMN remote_email VARCHAR(255) NULL AFTER node_id;")
                cursor.execute("SHOW COLUMNS FROM remote_customer_profiles LIKE 'owner_username'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE remote_customer_profiles ADD COLUMN owner_username VARCHAR(255) NULL AFTER display_name;")
                cursor.execute("SHOW COLUMNS FROM remote_customer_profiles LIKE 'traffic_multiplier'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE remote_customer_profiles ADD COLUMN traffic_multiplier DOUBLE NOT NULL DEFAULT 1 AFTER renew_price;")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        username VARCHAR(255) NOT NULL UNIQUE,
                        nickname VARCHAR(255) NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        onauth_sub VARCHAR(255) NULL UNIQUE,
                        onauth_username VARCHAR(255) NULL,
                        onauth_bound_at DATETIME NULL,
                        role VARCHAR(32) NOT NULL DEFAULT 'user',
                        enabled TINYINT(1) NOT NULL DEFAULT 1,
                        updated_at DATETIME NULL,
                        created_at DATETIME NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute("SHOW COLUMNS FROM users LIKE 'nickname'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE users ADD COLUMN nickname VARCHAR(255) NULL AFTER username;")
                cursor.execute("SHOW COLUMNS FROM users LIKE 'onauth_sub'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE users ADD COLUMN onauth_sub VARCHAR(255) NULL UNIQUE AFTER password_hash;")
                cursor.execute("SHOW COLUMNS FROM users LIKE 'onauth_username'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE users ADD COLUMN onauth_username VARCHAR(255) NULL AFTER onauth_sub;")
                cursor.execute("SHOW COLUMNS FROM users LIKE 'onauth_bound_at'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE users ADD COLUMN onauth_bound_at DATETIME NULL AFTER onauth_username;")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS passkey_credentials (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL,
                        username VARCHAR(255) NOT NULL,
                        credential_id VARCHAR(512) NOT NULL UNIQUE,
                        public_key LONGTEXT NOT NULL,
                        label VARCHAR(255) NOT NULL,
                        device_type VARCHAR(64) NOT NULL,
                        backed_up TINYINT(1) NOT NULL DEFAULT 0,
                        sign_count INT NOT NULL DEFAULT 0,
                        aaguid VARCHAR(128) NULL,
                        created_at DATETIME NOT NULL,
                        last_used_at DATETIME NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users_audit_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        target_user_id INT NOT NULL,
                        target_username VARCHAR(255) NOT NULL,
                        action VARCHAR(64) NOT NULL,
                        actor VARCHAR(255) NOT NULL,
                        change_summary TEXT NOT NULL,
                        created_at DATETIME NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS activity_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        category VARCHAR(64) NOT NULL,
                        action VARCHAR(64) NOT NULL,
                        actor VARCHAR(255),
                        target_type VARCHAR(64),
                        target_id VARCHAR(255),
                        target_name VARCHAR(255),
                        status VARCHAR(32) NOT NULL DEFAULT 'success',
                        summary TEXT NOT NULL,
                        detail TEXT,
                        ip_address VARCHAR(64),
                        created_at DATETIME NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notification_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        event_type VARCHAR(64) NOT NULL,
                        send_mode VARCHAR(64) NOT NULL,
                        customer_id VARCHAR(255),
                        node_id INT NULL,
                        remote_email VARCHAR(255),
                        customer_name VARCHAR(255),
                        manager VARCHAR(255),
                        webhook_url TEXT,
                        payload TEXT,
                        status VARCHAR(32) NOT NULL DEFAULT 'pending',
                        response_status INT NULL,
                        response_text TEXT,
                        error_message TEXT,
                        retry_count INT NOT NULL DEFAULT 0,
                        last_retry_at DATETIME NULL,
                        created_at DATETIME NOT NULL,
                        sent_at DATETIME NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
        else:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    manager TEXT DEFAULT '未分配',
                    node TEXT NOT NULL,
                    expiry_date TEXT NOT NULL,
                    duration TEXT NOT NULL,
                    traffic TEXT NOT NULL,
                    renew_price TEXT DEFAULT '未设置',
                    webhook_url TEXT,
                    last_notified TEXT
                )
                """
            )
            cursor = conn.execute("PRAGMA table_info(customers)")
            columns = [row[1] for row in cursor.fetchall()]
            if "manager" not in columns:
                conn.execute("ALTER TABLE customers ADD COLUMN manager TEXT DEFAULT '未分配';")
            if "renew_price" not in columns:
                conn.execute("ALTER TABLE customers ADD COLUMN renew_price TEXT DEFAULT '未设置';")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS financial_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER,
                    customer_name TEXT NOT NULL,
                    renew_price TEXT NOT NULL,
                    amount REAL,
                    renew_days INTEGER NOT NULL,
                    new_expiry TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS catalog_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                )
                """
            )
            node_columns = [row[1] for row in conn.execute("PRAGMA table_info(catalog_nodes)").fetchall()]
            if "scheme" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN scheme TEXT NOT NULL DEFAULT 'https';")
            if "address" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN address TEXT NOT NULL DEFAULT '';")
            if "port" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN port INTEGER NOT NULL DEFAULT 443;")
            if "base_path" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN base_path TEXT NOT NULL DEFAULT '/';")
            if "api_token" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN api_token TEXT;")
            if "allow_insecure" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN allow_insecure INTEGER NOT NULL DEFAULT 0;")
            if "subscription_scheme" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN subscription_scheme TEXT NOT NULL DEFAULT 'https';")
            if "subscription_address" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN subscription_address TEXT NOT NULL DEFAULT '';")
            if "subscription_port" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN subscription_port INTEGER NOT NULL DEFAULT 10882;")
            if "subscription_sub_path" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN subscription_sub_path TEXT NOT NULL DEFAULT '/sub';")
            if "subscription_json_path" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN subscription_json_path TEXT NOT NULL DEFAULT '/json';")
            if "subscription_clash_path" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN subscription_clash_path TEXT NOT NULL DEFAULT '/clash';")
            if "last_status" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN last_status TEXT DEFAULT 'unknown';")
            if "last_message" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN last_message TEXT;")
            if "last_checked_at" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN last_checked_at TEXT;")
            if "last_latency_ms" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN last_latency_ms INTEGER;")
            if "consecutive_failures" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0;")
            if "abnormal_notified_at" not in node_columns:
                conn.execute("ALTER TABLE catalog_nodes ADD COLUMN abnormal_notified_at TEXT;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS catalog_managers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS remote_customer_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id INTEGER NOT NULL,
                    node_name TEXT NOT NULL,
                    remote_email TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    manager TEXT DEFAULT '未分配',
                    renew_price TEXT DEFAULT '未设置',
                    traffic_multiplier REAL NOT NULL DEFAULT 1,
                    webhook_url TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(node_id, remote_email)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customer_audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL,
                    customer_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    change_summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customer_renewal_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL,
                    customer_name TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    renew_days INTEGER NOT NULL,
                    old_expiry TEXT NOT NULL,
                    new_expiry TEXT NOT NULL,
                    renew_price TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    nickname TEXT,
                    password_hash TEXT NOT NULL,
                    onauth_sub TEXT UNIQUE,
                    onauth_username TEXT,
                    onauth_bound_at TEXT,
                    role TEXT NOT NULL DEFAULT 'user',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users_audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_user_id INTEGER NOT NULL,
                    target_username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    change_summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT,
                    target_type TEXT,
                    target_id TEXT,
                    target_name TEXT,
                    status TEXT NOT NULL DEFAULT 'success',
                    summary TEXT NOT NULL,
                    detail TEXT,
                    ip_address TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    send_mode TEXT NOT NULL,
                    customer_id TEXT,
                    node_id INTEGER,
                    remote_email TEXT,
                    customer_name TEXT,
                    manager TEXT,
                    webhook_url TEXT,
                    payload TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    response_status INTEGER,
                    response_text TEXT,
                    error_message TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_retry_at TEXT,
                    created_at TEXT NOT NULL,
                    sent_at TEXT
                )
                """
            )

            user_columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
            if "role" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user';")
            if "enabled" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1;")
            if "updated_at" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN updated_at TEXT;")
            if "nickname" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN nickname TEXT;")
            if "onauth_sub" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN onauth_sub TEXT;")
            if "onauth_username" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN onauth_username TEXT;")
            if "onauth_bound_at" not in user_columns:
                conn.execute("ALTER TABLE users ADD COLUMN onauth_bound_at TEXT;")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS passkey_credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    credential_id TEXT NOT NULL UNIQUE,
                    public_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    backed_up INTEGER NOT NULL DEFAULT 0,
                    sign_count INTEGER NOT NULL DEFAULT 0,
                    aaguid TEXT,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT
                )
                """
            )

            audit_columns = [row[1] for row in conn.execute("PRAGMA table_info(customer_audit_logs)").fetchall()]
            if "customer_name" not in audit_columns:
                conn.execute("ALTER TABLE customer_audit_logs ADD COLUMN customer_name TEXT NOT NULL DEFAULT '';")
            if "action" not in audit_columns:
                conn.execute("ALTER TABLE customer_audit_logs ADD COLUMN action TEXT NOT NULL DEFAULT '未知';")

            if "node_id" not in audit_columns:
                conn.execute("ALTER TABLE customer_audit_logs ADD COLUMN node_id INTEGER;")
            if "remote_email" not in audit_columns:
                conn.execute("ALTER TABLE customer_audit_logs ADD COLUMN remote_email TEXT;")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_customer_audit_lookup ON customer_audit_logs (node_id, remote_email, action, id);")

            renewal_columns = [row[1] for row in conn.execute("PRAGMA table_info(customer_renewal_logs)").fetchall()]
            if "node_id" not in renewal_columns:
                conn.execute("ALTER TABLE customer_renewal_logs ADD COLUMN node_id INTEGER;")
            if "remote_email" not in renewal_columns:
                conn.execute("ALTER TABLE customer_renewal_logs ADD COLUMN remote_email TEXT;")

            financial_columns = [row[1] for row in conn.execute("PRAGMA table_info(financial_logs)").fetchall()]
            if "node_id" not in financial_columns:
                conn.execute("ALTER TABLE financial_logs ADD COLUMN node_id INTEGER;")
            if "owner_username" not in financial_columns:
                conn.execute("ALTER TABLE financial_logs ADD COLUMN owner_username TEXT;")
            if "remote_email" not in financial_columns:
                conn.execute("ALTER TABLE financial_logs ADD COLUMN remote_email TEXT;")
            profile_columns = [row[1] for row in conn.execute("PRAGMA table_info(remote_customer_profiles)").fetchall()]
            if "owner_username" not in profile_columns:
                conn.execute("ALTER TABLE remote_customer_profiles ADD COLUMN owner_username TEXT;")
            if "traffic_multiplier" not in profile_columns:
                conn.execute("ALTER TABLE remote_customer_profiles ADD COLUMN traffic_multiplier REAL NOT NULL DEFAULT 1;")

        ensure_setting(conn, settings, "notification_template", settings.default_notification_template)
        if (os.getenv("SUBSENTRY_CREATE_DEFAULT_ADMIN") or "").strip().lower() in ("1", "true", "yes", "on"):
            ensure_default_admin_user(conn, settings)
        conn.commit()
    finally:
        conn.close()


def ensure_setting(conn, settings: Settings, key: str, value: str) -> None:
    if settings.db_type == "mysql":
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM system_settings WHERE `key` = %s", (key,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO system_settings (`key`, `value`) VALUES (%s, %s)", (key, value))
    else:
        cursor = conn.execute("SELECT id FROM system_settings WHERE key = ?", (key,))
        if not cursor.fetchone():
            conn.execute("INSERT INTO system_settings (key, value) VALUES (?, ?)", (key, value))


def ensure_default_admin_user(conn, settings: Settings) -> None:
    if settings.db_type == "mysql":
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
            if cursor.fetchone():
                return
            cursor.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (%s, %s, %s, %s)",
                (settings.admin_user, hash_password(settings.admin_pass), "admin", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
    else:
        cursor = conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        if cursor.fetchone():
            return
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (settings.admin_user, hash_password(settings.admin_pass), "admin", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )


def upsert_setting(settings: Settings, key: str, value: str) -> None:
    existing = query(settings, "SELECT id FROM system_settings WHERE `key` = ?", (key,))
    if existing:
        execute(settings, "UPDATE system_settings SET value = ? WHERE `key` = ?", (value, key))
    else:
        execute(settings, "INSERT INTO system_settings (`key`, value) VALUES (?, ?)", (key, value))


def get_setting(settings: Settings, key: str, default_value: str = "") -> str:
    rows = query(settings, "SELECT value FROM system_settings WHERE `key` = ?", (key,))
    if not rows:
        return default_value
    return rows[0].get("value") or default_value


def upsert_setting_once(settings: Settings, key: str, value: str) -> None:
    existing = query(settings, "SELECT id FROM system_settings WHERE `key` = ?", (key,))
    if not existing:
        execute(settings, "INSERT INTO system_settings (`key`, value) VALUES (?, ?)", (key, value))


def ensure_default_settings(settings: Settings) -> None:
    upsert_setting_once(settings, "push_mode", settings.default_push_mode)
    upsert_setting_once(settings, "max_detail_rows", str(settings.default_max_detail_rows))
    upsert_setting_once(settings, "fixed_push_time", settings.default_fixed_push_time)
    upsert_setting_once(settings, "fixed_push_time_enabled", settings.default_push_time_enabled)
    upsert_setting_once(settings, "push_time_window_minutes", str(settings.default_push_time_window_minutes))
    upsert_setting_once(settings, "local_subscription_enabled", "0")
    upsert_setting_once(settings, "local_subscription_base_url", settings.public_subscription_base_url)
    upsert_setting_once(settings, "local_subscription_port", "10883")
    upsert_setting_once(settings, "local_subscription_title", "SubSentry")
