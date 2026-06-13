import secrets
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import HTTPException, status

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json_dict, parse_authentication_credential_json, parse_registration_credential_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from backend.app.core.config import Settings
from backend.app.db.database import execute, query
from backend.app.services.users import get_user_by_username


SESSION_PASSKEY_REG_PREFIX = "passkey:registration:"
SESSION_PASSKEY_AUTH_PREFIX = "passkey:authentication:"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _origin_host(origin: str) -> str:
    value = (origin or "").strip()
    if "//" not in value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey 需要有效的页面 Origin")
    host_port = value.split("//", 1)[1]
    host = host_port.split("/", 1)[0].split(":", 1)[0].strip()
    if not host:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey 需要有效的页面 Origin")
    return host


def _normalize_origin(origin: str) -> str:
    value = (origin or "").strip().rstrip("/")
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey 需要有效的页面 Origin")
    return value


def _session_token() -> str:
    return secrets.token_urlsafe(24)


def _user_handle(user: Dict) -> bytes:
    return f"subsentry-user:{user['id']}:{user['username']}".encode("utf-8")


def _decode_credential_id(value: str) -> bytes:
    try:
        return base64url_to_bytes(value)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey 凭证格式无效") from exc


def list_passkeys(settings: Settings, username: str) -> List[Dict]:
    return query(
        settings,
        """
        SELECT id, user_id, username, credential_id, label, device_type, backed_up, sign_count, created_at, last_used_at
        FROM passkey_credentials
        WHERE username = ?
        ORDER BY id DESC
        """,
        (username,),
    )


def get_passkey_count(settings: Settings, username: str) -> int:
    rows = query(settings, "SELECT COUNT(1) AS cnt FROM passkey_credentials WHERE username = ?", (username,))
    return int((rows[0].get("cnt") if rows else 0) or 0)


def get_passkey_by_credential_id(settings: Settings, credential_id: str) -> Optional[Dict]:
    rows = query(
        settings,
        "SELECT id, user_id, username, credential_id, public_key, label, device_type, backed_up, sign_count, created_at, last_used_at FROM passkey_credentials WHERE credential_id = ?",
        (credential_id,),
    )
    return rows[0] if rows else None


def delete_passkey(settings: Settings, username: str, credential_row_id: int) -> Dict:
    row = query(
        settings,
        "SELECT id FROM passkey_credentials WHERE id = ? AND username = ?",
        (credential_row_id, username),
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该 Passkey")
    execute(settings, "DELETE FROM passkey_credentials WHERE id = ?", (credential_row_id,))
    return {"success": True, "message": "Passkey 已删除"}


def build_registration_options(settings: Settings, username: str, origin: str) -> Dict:
    user = get_user_by_username(settings, username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到当前用户")
    normalized_origin = _normalize_origin(origin)
    rp_id = _origin_host(normalized_origin)
    passkeys = list_passkeys(settings, username)
    exclude_credentials = [PublicKeyCredentialDescriptor(id=_decode_credential_id(item["credential_id"])) for item in passkeys]
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=settings.app_name,
        user_name=username,
        user_id=_user_handle(user),
        user_display_name=user.get("nickname") or username,
        exclude_credentials=exclude_credentials or None,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    token = _session_token()
    return {
        "session_key": f"{SESSION_PASSKEY_REG_PREFIX}{token}",
        "state": {
            "username": username,
            "origin": normalized_origin,
            "rp_id": rp_id,
            "challenge": bytes_to_base64url(options.challenge),
        },
        "options": options_to_json_dict(options),
    }


def complete_registration(settings: Settings, state: Dict, credential_payload: Dict, label: str | None = None, origin: str | None = None) -> Dict:
    username = str(state.get("username") or "").strip()
    user = get_user_by_username(settings, username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到当前用户")
    expected_origin = _normalize_origin(origin or state.get("origin") or "")
    expected_rp_id = str(state.get("rp_id") or "").strip()
    expected_challenge = base64url_to_bytes(str(state.get("challenge") or ""))
    credential = parse_registration_credential_json(credential_payload)
    verified = verify_registration_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_rp_id=expected_rp_id,
        expected_origin=expected_origin,
        require_user_presence=True,
        require_user_verification=False,
    )
    credential_id = bytes_to_base64url(verified.credential_id)
    public_key = bytes_to_base64url(verified.credential_public_key)
    now_text = _now_text()
    execute(
        settings,
        """
        INSERT INTO passkey_credentials (
            user_id, username, credential_id, public_key, label, device_type, backed_up, sign_count, aaguid, created_at, last_used_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user["id"]),
            username,
            credential_id,
            public_key,
            (label or "").strip() or "未命名 Passkey",
            str(verified.credential_device_type.value if hasattr(verified.credential_device_type, "value") else verified.credential_device_type),
            1 if verified.credential_backed_up else 0,
            int(verified.sign_count),
            str(verified.aaguid),
            now_text,
            now_text,
        ),
    )
    return {"success": True, "message": "Passkey 已绑定", "data": {"credential_id": credential_id}}


def build_authentication_options(settings: Settings, origin: str, username: str | None = None) -> Dict:
    normalized_origin = _normalize_origin(origin)
    rp_id = _origin_host(normalized_origin)
    allow_credentials = None
    clean_username = (username or "").strip()
    if clean_username:
        user = get_user_by_username(settings, clean_username)
        if user:
            passkeys = list_passkeys(settings, clean_username)
            allow_credentials = [PublicKeyCredentialDescriptor(id=_decode_credential_id(item["credential_id"])) for item in passkeys] or None
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    token = _session_token()
    return {
        "session_key": f"{SESSION_PASSKEY_AUTH_PREFIX}{token}",
        "state": {
            "username": clean_username,
            "origin": normalized_origin,
            "rp_id": rp_id,
            "challenge": bytes_to_base64url(options.challenge),
        },
        "options": options_to_json_dict(options),
    }


def complete_authentication(settings: Settings, state: Dict, credential_payload: Dict, origin: str | None = None) -> Dict:
    expected_origin = _normalize_origin(origin or state.get("origin") or "")
    expected_rp_id = str(state.get("rp_id") or "").strip()
    expected_challenge = base64url_to_bytes(str(state.get("challenge") or ""))
    credential = parse_authentication_credential_json(credential_payload)
    credential_id = bytes_to_base64url(credential.raw_id)
    stored = get_passkey_by_credential_id(settings, credential_id)
    if not stored:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未找到该 Passkey")
    if str(stored.get("username") or "") and str(state.get("username") or "") and str(stored.get("username")) != str(state.get("username")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Passkey 不属于当前登录入口")
    public_key = base64url_to_bytes(str(stored.get("public_key") or ""))
    verified = verify_authentication_response(
        credential=credential,
        expected_challenge=expected_challenge,
        expected_rp_id=expected_rp_id,
        expected_origin=expected_origin,
        credential_public_key=public_key,
        credential_current_sign_count=int(stored.get("sign_count") or 0),
        require_user_verification=False,
    )
    now_text = _now_text()
    execute(
        settings,
        "UPDATE passkey_credentials SET sign_count = ?, last_used_at = ? WHERE credential_id = ?",
        (int(verified.new_sign_count), now_text, credential_id),
    )
    user = get_user_by_username(settings, str(stored.get("username") or ""))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未找到绑定的用户")
    enabled_value = user.get("enabled")
    if enabled_value is None:
        enabled_value = 1
    if int(enabled_value) != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    return {
        "success": True,
        "message": "Passkey 登录成功",
        "data": {
            "username": user["username"],
            "nickname": user.get("nickname") or "",
            "role": user.get("role") or "user",
        },
    }
