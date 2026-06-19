from datetime import datetime
from typing import Dict, List, Optional

from fastapi import HTTPException, status

from backend.app.core.config import Settings
from backend.app.core.security import hash_password, verify_password
from backend.app.db.database import execute, query, scalar


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def list_users(settings: Settings, page: int = 1, per_page: int = 20, keyword: str = "", role: str = "") -> Dict:
    params: list = []
    where_clauses: list = []
    if keyword:
        where_clauses.append("username LIKE ?")
        params.append(f"%{keyword}%")
    if role:
        where_clauses.append("role = ?")
        params.append(role)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    total = scalar(settings, f"SELECT COUNT(1) AS cnt FROM users {where_sql}", tuple(params), default=0) or 0
    offset = (page - 1) * per_page
    params_with_limit = params + [per_page, offset]
    rows = query(
        settings,
        f"SELECT id, username, nickname, role, enabled, created_at, updated_at FROM users {where_sql} ORDER BY id ASC LIMIT ? OFFSET ?",
        tuple(params_with_limit),
    )
    return {"items": rows, "total": total, "page": page, "per_page": per_page}


def get_user_by_username(settings: Settings, username: str) -> Optional[Dict]:
    rows = query(
        settings,
        "SELECT id, username, nickname, password_hash, onauth_sub, onauth_username, onauth_bound_at, role, enabled, created_at, updated_at FROM users WHERE username = ?",
        (username,),
    )
    return rows[0] if rows else None


def get_user_by_id(settings: Settings, user_id: int) -> Optional[Dict]:
    rows = query(
        settings,
        "SELECT id, username, nickname, password_hash, onauth_sub, onauth_username, onauth_bound_at, role, enabled, created_at, updated_at FROM users WHERE id = ?",
        (user_id,),
    )
    return rows[0] if rows else None


def get_user_by_onauth_sub(settings: Settings, onauth_sub: str) -> Optional[Dict]:
    rows = query(
        settings,
        "SELECT id, username, nickname, password_hash, onauth_sub, onauth_username, onauth_bound_at, role, enabled, created_at, updated_at FROM users WHERE onauth_sub = ?",
        ((onauth_sub or "").strip(),),
    )
    return rows[0] if rows else None


def authenticate_user(settings: Settings, username: str, password: str) -> Optional[Dict]:
    user = get_user_by_username(settings, username)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    enabled_value = user.get("enabled")
    if enabled_value is None:
        enabled_value = 1
    if int(enabled_value) != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    return user


def create_user(
    settings: Settings,
    username: str,
    password: str,
    role: str = "user",
    nickname: str | None = None,
    actor: str | None = None,
) -> Dict:
    clean_username = (username or "").strip()
    clean_role = (role or "user").strip().lower()
    clean_nickname = (nickname or "").strip()
    if clean_role not in ("admin", "user"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色不合法")
    if not clean_username or not (password or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名和密码不能为空")
    if get_user_by_username(settings, clean_username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")

    execute(
        settings,
        "INSERT INTO users (username, nickname, password_hash, role, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (clean_username, clean_nickname, hash_password(password), clean_role, 1, _now_text()),
    )
    try:
        uid = scalar(settings, "SELECT id FROM users WHERE username = ?", (clean_username,))
        execute(
            settings,
            "INSERT INTO users_audit_logs (target_user_id, target_username, action, actor, change_summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, clean_username, "create", actor or "system", f"创建用户 {clean_username}", _now_text()),
        )
    except Exception:
        pass
    return {"success": True, "message": "用户已创建"}


def delete_user(settings: Settings, user_id: int, actor: str | None = None) -> Dict:
    target = get_user_by_id(settings, user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该用户")

    if target["role"] == "admin":
        admin_count = scalar(settings, "SELECT COUNT(1) AS cnt FROM users WHERE role = 'admin'", default=0) or 0
        if admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少保留一个管理员账号")

    execute(settings, "DELETE FROM users WHERE id = ?", (user_id,))
    try:
        execute(
            settings,
            "INSERT INTO users_audit_logs (target_user_id, target_username, action, actor, change_summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, target["username"], "delete", actor or "system", f"删除用户 {target['username']}", _now_text()),
        )
    except Exception:
        pass
    return {"success": True, "message": "用户已删除"}


def change_password(settings: Settings, user_id: int, new_password: str, actor: str | None = None) -> Dict:
    if not (new_password or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能为空")
    target = get_user_by_id(settings, user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该用户")
    execute(
        settings,
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (hash_password(new_password), _now_text(), user_id),
    )
    try:
        execute(
            settings,
            "INSERT INTO users_audit_logs (target_user_id, target_username, action, actor, change_summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, target["username"], "change_password", actor or "system", "修改密码", _now_text()),
        )
    except Exception:
        pass
    return {"success": True, "message": "密码已修改"}


def reset_password(settings: Settings, user_id: int, actor: str | None = None) -> Dict:
    target = get_user_by_id(settings, user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该用户")
    default_password = f"{target['username']}@123456"
    execute(
        settings,
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (hash_password(default_password), _now_text(), user_id),
    )
    try:
        execute(
            settings,
            "INSERT INTO users_audit_logs (target_user_id, target_username, action, actor, change_summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, target["username"], "reset_password", actor or "system", "重置密码", _now_text()),
        )
    except Exception:
        pass
    return {"success": True, "message": "密码已重置", "default_password": default_password}


def set_enabled(settings: Settings, user_id: int, enabled: bool, actor: str | None = None) -> Dict:
    target = get_user_by_id(settings, user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该用户")
    if not enabled and str(target.get("username") or "") == (actor or ""):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员不能禁用自己")
    if target["role"] == "admin" and not enabled:
        admin_count = scalar(settings, "SELECT COUNT(1) AS cnt FROM users WHERE role = 'admin' AND enabled = 1", default=0) or 0
        if admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少保留一个启用中的管理员账号")
    execute(
        settings,
        "UPDATE users SET enabled = ?, updated_at = ? WHERE id = ?",
        (1 if enabled else 0, _now_text(), user_id),
    )
    try:
        execute(
            settings,
            "INSERT INTO users_audit_logs (target_user_id, target_username, action, actor, change_summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, target["username"], "set_enabled", actor or "system", f"设置启用={enabled}", _now_text()),
        )
    except Exception:
        pass
    return {"success": True, "message": "用户状态已更新", "enabled": enabled}


def update_user_role(settings: Settings, user_id: int, role: str, actor: str | None = None) -> Dict:
    target = get_user_by_id(settings, user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该用户")

    clean_role = (role or "").strip().lower()
    if clean_role not in ("admin", "user"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色不合法")
    old_role = str(target.get("role") or "user")
    if old_role == clean_role:
        return {"success": True, "message": "用户角色未变化", "role": clean_role}
    if str(target.get("username") or "") == (actor or "") and clean_role != "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员不能修改自己的管理员角色")

    if old_role == "admin" and clean_role != "admin":
        admin_count = scalar(settings, "SELECT COUNT(1) AS cnt FROM users WHERE role = 'admin'", default=0) or 0
        if admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少保留一个管理员账号")

    now_text = _now_text()
    execute(settings, "UPDATE users SET role = ?, updated_at = ? WHERE id = ?", (clean_role, now_text, user_id))
    try:
        execute(
            settings,
            "INSERT INTO users_audit_logs (target_user_id, target_username, action, actor, change_summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, target["username"], "set_role", actor or "system", f"修改角色：{old_role} -> {clean_role}", now_text),
        )
    except Exception:
        pass
    return {"success": True, "message": "用户角色已更新", "role": clean_role}


def list_user_audit(settings: Settings, user_id: int):
    return query(
        settings,
        "SELECT id, target_user_id, target_username, action, actor, change_summary, created_at FROM users_audit_logs WHERE target_user_id = ? ORDER BY id DESC",
        (user_id,),
    )


def list_manager_users(settings: Settings) -> List[Dict]:
    return query(
        settings,
        "SELECT id, username, nickname, enabled, role, created_at, updated_at FROM users WHERE role IN ('admin','user') ORDER BY enabled DESC, id ASC",
    )


def update_user_nickname(settings: Settings, user_id: int, nickname: str, actor: str | None = None) -> Dict:
    user = get_user_by_id(settings, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该用户")

    username = user["username"]
    clean_nickname = (nickname or "").strip()
    display_name = clean_nickname or username
    now_text = _now_text()

    execute(settings, "UPDATE users SET nickname = ?, updated_at = ? WHERE id = ?", (clean_nickname, now_text, user_id))
    execute(settings, "UPDATE remote_customer_profiles SET manager = ? WHERE owner_username = ?", (display_name, username))

    try:
        execute(
            settings,
            "INSERT INTO users_audit_logs (target_user_id, target_username, action, actor, change_summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, "set_nickname", actor or "system", f"设置客户经理昵称为 {display_name}", now_text),
        )
    except Exception:
        pass

    return {"success": True, "message": "客户经理昵称已更新"}


def update_current_user_profile(settings: Settings, username: str, nickname: str, actor: str | None = None) -> Dict:
    user = get_user_by_username(settings, username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到当前用户")
    return update_user_nickname(settings, int(user["id"]), nickname, actor=actor or username)


def bind_onauth_user(settings: Settings, username: str, onauth_sub: str, onauth_username: str = "", actor: str | None = None) -> Dict:
    user = get_user_by_username(settings, username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到当前用户")
    clean_sub = (onauth_sub or "").strip()
    if not clean_sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OnAuth 用户标识为空")
    existing = get_user_by_onauth_sub(settings, clean_sub)
    if existing and str(existing.get("username")) != username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该 OnAuth 账号已绑定其他用户")
    execute(
        settings,
        "UPDATE users SET onauth_sub = ?, onauth_username = ?, onauth_bound_at = ?, updated_at = ? WHERE username = ?",
        (clean_sub, (onauth_username or "").strip(), _now_text(), _now_text(), username),
    )
    try:
        execute(
            settings,
            "INSERT INTO users_audit_logs (target_user_id, target_username, action, actor, change_summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], username, "bind_onauth", actor or username, f"绑定 OnAuth 账号 {onauth_username or clean_sub}", _now_text()),
        )
    except Exception:
        pass
    return {"success": True, "message": "OnAuth 已绑定"}


def unbind_onauth_user(settings: Settings, username: str, actor: str | None = None) -> Dict:
    user = get_user_by_username(settings, username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到当前用户")
    execute(settings, "UPDATE users SET onauth_sub = NULL, onauth_username = NULL, onauth_bound_at = NULL, updated_at = ? WHERE username = ?", (_now_text(), username))
    try:
        execute(
            settings,
            "INSERT INTO users_audit_logs (target_user_id, target_username, action, actor, change_summary, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], username, "unbind_onauth", actor or username, "解绑 OnAuth 账号", _now_text()),
        )
    except Exception:
        pass
    return {"success": True, "message": "OnAuth 已解绑"}


def change_own_password(settings: Settings, username: str, current_password: str, new_password: str, actor: str | None = None) -> Dict:
    user = get_user_by_username(settings, username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到当前用户")
    if not (current_password or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入当前密码")
    if not (new_password or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入新密码")
    if not verify_password(current_password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码不正确")
    if current_password == new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与当前密码相同")
    return change_password(settings, int(user["id"]), new_password, actor=actor or username)
