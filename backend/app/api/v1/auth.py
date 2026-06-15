from fastapi import APIRouter, Depends, HTTPException, Request, status
from threading import Lock

from pydantic import BaseModel

from backend.app.core.deps import SESSION_LOGIN_KEY, SESSION_ROLE_KEY, SESSION_USER_KEY, require_admin, require_login
from backend.app.core.config import Settings
from backend.app.services.logs import write_activity_log
from backend.app.services.onauth import (
    SESSION_ONAUTH_STATE_PREFIX,
    build_authorize_url,
    exchange_code_for_token,
    fetch_userinfo,
    normalize_userinfo,
)
from backend.app.services.passkeys import (
    SESSION_PASSKEY_AUTH_PREFIX,
    SESSION_PASSKEY_REG_PREFIX,
    build_authentication_options,
    build_registration_options,
    complete_authentication,
    complete_registration,
    delete_passkey,
    get_passkey_count,
    list_passkeys,
)
from backend.app.services.turnstile import is_turnstile_enabled, verify_turnstile
from backend.app.services.users import (
    authenticate_user,
    bind_onauth_user,
    change_own_password,
    change_password,
    create_user,
    delete_user,
    get_user_by_onauth_sub,
    get_user_by_username,
    list_manager_users,
    list_user_audit,
    list_users,
    reset_password,
    set_enabled,
    unbind_onauth_user,
    update_current_user_profile,
    update_user_nickname,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
PROCESSING_ONAUTH_STATES: set[str] = set()
PROCESSING_ONAUTH_STATES_LOCK = Lock()


class LoginRequest(BaseModel):
    username: str
    password: str
    turnstile_token: str | None = None


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "user"
    nickname: str | None = None


class UserPasswordRequest(BaseModel):
    password: str


class SelfPasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserEnabledRequest(BaseModel):
    enabled: bool


class UserNicknameRequest(BaseModel):
    nickname: str | None = None


class OnAuthStartRequest(BaseModel):
    redirect_uri: str
    mode: str = "login"


class OnAuthCallbackRequest(BaseModel):
    code: str
    state: str
    redirect_uri: str


class PasskeyOptionsRequest(BaseModel):
    origin: str
    username: str | None = None


class PasskeyRegisterVerifyRequest(BaseModel):
    challenge_id: str
    origin: str
    credential: dict
    label: str | None = None


class PasskeyLoginVerifyRequest(BaseModel):
    challenge_id: str
    origin: str
    credential: dict


class PasskeyLoginStartRequest(BaseModel):
    origin: str
    username: str | None = None


class PasskeyRegisterStartRequest(BaseModel):
    origin: str


def _login_session(request: Request, user: dict) -> None:
    request.session[SESSION_LOGIN_KEY] = True
    request.session[SESSION_USER_KEY] = user["username"]
    request.session[SESSION_ROLE_KEY] = user.get("role") or "user"
    request.session["nickname"] = user.get("nickname") or ""


def _challenge_id_from_session_key(session_key: str, prefix: str) -> str:
    return session_key[len(prefix) :] if session_key.startswith(prefix) else session_key


def _request_ip(request: Request) -> str:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    return request.headers.get("cf-connecting-ip") or forwarded_for or (request.client.host if request.client else "")


@router.post("/login")
def login(payload: LoginRequest, request: Request):
    settings: Settings = request.app.state.settings
    remote_ip = _request_ip(request)
    turnstile_ok, turnstile_message = verify_turnstile(settings, payload.turnstile_token, remote_ip)
    if not turnstile_ok:
        write_activity_log(
            settings,
            category="auth",
            action="login",
            actor=payload.username,
            status="failed",
            summary=f"登录失败：{payload.username}，{turnstile_message}",
            ip_address=remote_ip,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=turnstile_message)
    try:
        user = authenticate_user(settings, payload.username, payload.password)
    except HTTPException as exc:
        write_activity_log(
            settings,
            category="auth",
            action="login",
            actor=payload.username,
            status="failed",
            summary=f"登录失败：{payload.username}，{exc.detail}",
            ip_address=request.client.host if request.client else "",
        )
        raise
    if not user:
        write_activity_log(
            settings,
            category="auth",
            action="login",
            actor=payload.username,
            status="failed",
            summary=f"登录失败：{payload.username}",
            ip_address=request.client.host if request.client else "",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")

    _login_session(request, user)
    write_activity_log(
        settings,
        category="auth",
        action="login",
        actor=user["username"],
        target_type="user",
        target_id=str(user.get("id") or ""),
        target_name=user["username"],
        summary=f"用户登录：{user['username']}",
        ip_address=request.client.host if request.client else "",
    )
    return {
        "success": True,
        "message": "登录成功",
        "data": {
            "username": user["username"],
            "nickname": user.get("nickname") or "",
            "role": user.get("role") or "user",
        },
    }


@router.post("/logout")
def logout(request: Request):
    request.session.pop(SESSION_LOGIN_KEY, None)
    request.session.pop(SESSION_USER_KEY, None)
    request.session.pop(SESSION_ROLE_KEY, None)
    request.session.pop("nickname", None)
    return {"success": True, "message": "已退出登录"}


@router.get("/turnstile/config")
def turnstile_config(request: Request):
    settings: Settings = request.app.state.settings
    return {
        "success": True,
        "data": {
            "enabled": is_turnstile_enabled(settings),
            "site_key": settings.turnstile_site_key if is_turnstile_enabled(settings) else "",
        },
    }


@router.get("/me")
def me(request: Request, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    user = get_user_by_username(settings, username)
    return {
        "success": True,
        "data": {
            "username": username,
            "nickname": request.session.get("nickname") or "",
            "role": request.session.get(SESSION_ROLE_KEY) or "user",
            "logged_in": True,
            "onauth_bound": bool(user and user.get("onauth_sub")),
            "onauth_username": (user or {}).get("onauth_username") or "",
            "onauth_bound_at": (user or {}).get("onauth_bound_at") or "",
        },
    }


@router.put("/me")
def update_me(request: Request, payload: UserNicknameRequest, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    result = update_current_user_profile(settings, username, payload.nickname or "", actor=username)
    request.session["nickname"] = (payload.nickname or "").strip()
    write_activity_log(
        settings,
        category="auth",
        action="update_profile",
        actor=username,
        target_type="user",
        target_name=username,
        summary=f"用户更新个人资料：{username}",
        ip_address=request.client.host if request.client else "",
    )
    return {
        **result,
        "data": {
            "username": username,
            "nickname": request.session.get("nickname") or "",
            "role": request.session.get(SESSION_ROLE_KEY) or "user",
        },
    }


@router.put("/me/password")
def update_my_password(request: Request, payload: SelfPasswordRequest, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    result = change_own_password(settings, username, payload.current_password, payload.new_password, actor=username)
    write_activity_log(
        settings,
        category="auth",
        action="change_password",
        actor=username,
        target_type="user",
        target_name=username,
        summary=f"用户修改个人密码：{username}",
        ip_address=request.client.host if request.client else "",
    )
    return result


@router.get("/onauth/config")
def onauth_config(request: Request):
    settings: Settings = request.app.state.settings
    return {
        "success": True,
        "data": {
            "enabled": bool(settings.onauth_base_url and settings.onauth_client_id and settings.onauth_client_secret),
        },
    }


@router.post("/onauth/start")
def onauth_start(request: Request, payload: OnAuthStartRequest):
    settings: Settings = request.app.state.settings
    mode = "bind" if payload.mode == "bind" else "login"
    if mode == "bind" and not request.session.get(SESSION_LOGIN_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录后再绑定 OnAuth")
    authorize_url, state = build_authorize_url(settings, payload.redirect_uri, mode)
    request.session[f"{SESSION_ONAUTH_STATE_PREFIX}{state}"] = {
        "mode": mode,
        "username": request.session.get(SESSION_USER_KEY) or "",
    }
    return {"success": True, "data": {"authorize_url": authorize_url}}


@router.post("/onauth/callback")
def onauth_callback(request: Request, payload: OnAuthCallbackRequest):
    settings: Settings = request.app.state.settings
    state_key = f"{SESSION_ONAUTH_STATE_PREFIX}{payload.state}"
    with PROCESSING_ONAUTH_STATES_LOCK:
        if payload.state in PROCESSING_ONAUTH_STATES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OnAuth 回调正在处理中，请勿重复提交")
        PROCESSING_ONAUTH_STATES.add(payload.state)
    state_data = request.session.pop(state_key, None)
    try:
        if not state_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OnAuth state 无效或已过期")
        token_data = exchange_code_for_token(settings, payload.code, payload.redirect_uri)
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OnAuth token 响应缺少 access_token")
        onauth_user = normalize_userinfo(fetch_userinfo(settings, str(access_token)))
        mode = state_data.get("mode") or "login"

        if mode == "bind":
            bind_username = state_data.get("username") or request.session.get(SESSION_USER_KEY)
            if not bind_username or not request.session.get(SESSION_LOGIN_KEY):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="绑定会话已失效，请重新登录")
            result = bind_onauth_user(settings, str(bind_username), onauth_user["sub"], onauth_user["username"], actor=str(bind_username))
            write_activity_log(
                settings,
                category="auth",
                action="bind_onauth",
                actor=str(bind_username),
                target_type="user",
                target_name=str(bind_username),
                summary=f"用户绑定 OnAuth：{bind_username}",
                ip_address=request.client.host if request.client else "",
            )
            return {**result, "data": {"mode": "bind", "onauth_username": onauth_user["username"]}}

        user = get_user_by_onauth_sub(settings, onauth_user["sub"])
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="该 OnAuth 账号尚未绑定本地用户")
        enabled_value = user.get("enabled")
        if enabled_value is None:
            enabled_value = 1
        if int(enabled_value) != 1:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
        _login_session(request, user)
        write_activity_log(
            settings,
            category="auth",
            action="onauth_login",
            actor=user["username"],
            target_type="user",
            target_id=str(user.get("id") or ""),
            target_name=user["username"],
            summary=f"OnAuth 登录：{user['username']}",
            ip_address=request.client.host if request.client else "",
        )
        return {
            "success": True,
            "message": "OnAuth 登录成功",
            "data": {
                "mode": "login",
                "username": user["username"],
                "nickname": user.get("nickname") or "",
                "role": user.get("role") or "user",
            },
        }
    finally:
        PROCESSING_ONAUTH_STATES.discard(payload.state)


@router.delete("/onauth/binding")
def onauth_unbind(request: Request, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    result = unbind_onauth_user(settings, username, actor=username)
    write_activity_log(
        settings,
        category="auth",
        action="unbind_onauth",
        actor=username,
        target_type="user",
        target_name=username,
        summary=f"用户解绑 OnAuth：{username}",
        ip_address=request.client.host if request.client else "",
    )
    return result


@router.get("/passkeys")
def my_passkeys(request: Request, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    return {"success": True, "data": {"items": list_passkeys(settings, username), "count": get_passkey_count(settings, username)}}


@router.post("/passkeys/register/start")
def passkey_register_start(request: Request, payload: PasskeyRegisterStartRequest, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    result = build_registration_options(settings, username, payload.origin)
    request.session[result["session_key"]] = result["state"]
    return {"success": True, "data": {"challenge_id": _challenge_id_from_session_key(result["session_key"], SESSION_PASSKEY_REG_PREFIX), "options": result["options"]}}


@router.post("/passkeys/register/complete")
def passkey_register_complete(request: Request, payload: PasskeyRegisterVerifyRequest, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    session_key = f"{SESSION_PASSKEY_REG_PREFIX}{payload.challenge_id}"
    state = request.session.pop(session_key, None)
    if not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey 注册已过期，请重新开始")
    result = complete_registration(settings, state, payload.credential, payload.label, payload.origin)
    return result


@router.post("/passkeys/authenticate/start")
def passkey_authenticate_start(request: Request, payload: PasskeyLoginStartRequest):
    settings: Settings = request.app.state.settings
    result = build_authentication_options(settings, payload.origin, payload.username)
    request.session[result["session_key"]] = result["state"]
    return {"success": True, "data": {"challenge_id": _challenge_id_from_session_key(result["session_key"], SESSION_PASSKEY_AUTH_PREFIX), "options": result["options"]}}


@router.post("/passkeys/authenticate/complete")
def passkey_authenticate_complete(request: Request, payload: PasskeyLoginVerifyRequest):
    settings: Settings = request.app.state.settings
    session_key = f"{SESSION_PASSKEY_AUTH_PREFIX}{payload.challenge_id}"
    state = request.session.pop(session_key, None)
    if not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey 登录已过期，请重新开始")
    result = complete_authentication(settings, state, payload.credential, payload.origin)
    user = get_user_by_username(settings, result["data"]["username"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未找到绑定用户")
    _login_session(request, user)
    return result


@router.delete("/passkeys/{credential_id}")
def passkey_delete(request: Request, credential_id: int, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    return delete_passkey(settings, username, credential_id)


@router.get("/users")
def users(request: Request, page: int = 1, per_page: int = 20, keyword: str = "", role: str = "", username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    data = list_users(settings, page=page, per_page=per_page, keyword=keyword, role=role)
    return {"success": True, "data": data}


@router.get("/managers")
def managers(request: Request, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    return {"success": True, "data": list_manager_users(settings)}


@router.post("/users")
def add_user(request: Request, payload: UserCreateRequest, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return create_user(settings, payload.username, payload.password, payload.role, payload.nickname, actor=username)


@router.delete("/users/{user_id}")
def remove_user(request: Request, user_id: int, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return delete_user(settings, user_id, actor=username)


@router.put("/users/{user_id}/password")
def change_user_password(request: Request, user_id: int, payload: UserPasswordRequest, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return change_password(settings, user_id, payload.password, actor=username)


@router.post("/users/{user_id}/reset-password")
def reset_user_password(request: Request, user_id: int, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return reset_password(settings, user_id, actor=username)


@router.put("/users/{user_id}/enabled")
def toggle_user_enabled(request: Request, user_id: int, payload: UserEnabledRequest, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return set_enabled(settings, user_id, payload.enabled, actor=username)


@router.put("/users/{user_id}/nickname")
def change_user_nickname(request: Request, user_id: int, payload: UserNicknameRequest, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return update_user_nickname(settings, user_id, payload.nickname or "", actor=username)


@router.get("/users/{user_id}/audit")
def user_audit(request: Request, user_id: int, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return {"success": True, "data": list_user_audit(settings, user_id)}
