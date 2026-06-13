from fastapi import HTTPException, Request, status

from backend.app.db.database import query


SESSION_USER_KEY = "username"
SESSION_LOGIN_KEY = "logged_in"
SESSION_ROLE_KEY = "role"


def require_login(request: Request) -> str:
    if not request.session.get(SESSION_LOGIN_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    username = request.session.get(SESSION_USER_KEY) or "admin"
    settings = request.app.state.settings
    rows = query(
        settings,
        "SELECT username, nickname, role, enabled FROM users WHERE username = ? LIMIT 1",
        (str(username),),
    )
    if not rows:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    user = rows[0]
    enabled_value = user.get("enabled")
    if enabled_value is None:
        enabled_value = 1
    if int(enabled_value) != 1:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    username = str(user.get("username") or username)
    request.session[SESSION_USER_KEY] = username
    request.session[SESSION_ROLE_KEY] = user.get("role") or "user"
    request.session["nickname"] = user.get("nickname") or ""
    return username


def require_admin(request: Request) -> str:
    username = require_login(request)
    role = request.session.get(SESSION_ROLE_KEY) or "user"
    if str(role) != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return username
