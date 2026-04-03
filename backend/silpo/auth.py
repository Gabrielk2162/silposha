"""Real Silpo OTP authentication via auth.silpo.ua OpenID Connect.

Flow:
1. request_otp(phone) -> sends SMS with 6-digit code
2. verify_otp(phone, code) -> verifies code, gets auth cookies
3. openid_authorize(phone) -> uses cookies to get OpenID auth code
4. get_token(phone, auth_code) -> exchanges code for access_token

Based on reverse-engineered pysilpo auth endpoints.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx

AUTH_DOMAIN = "https://auth.silpo.ua"
OPENID_CONFIG_URL = f"{AUTH_DOMAIN}/.well-known/openid-configuration"
REQUEST_OTP_URL = f"{AUTH_DOMAIN}/api/v2/Login/ByPhone"
VERIFY_OTP_URL = f"{AUTH_DOMAIN}/api/v2/Login/LoginWithOTP"

CLIENT_ID = "profile--profile--cabinet"
REDIRECT_URI = "https://id.silpo.ua/signin-oidc"
SCOPE = (
    "openid public-my profile--security--identity-service:internal-api--call "
    "core--core--media-service:media--upload payments--payments--wallet-service:cards--read-my "
    "core--core--media-service:media--upload"
)

PHONE_PATTERN = re.compile(r"^\+380\d{9}$")

# In-memory session store: phone -> {cookies, code_verifier, token, expires_at}
_sessions: dict[str, dict] = {}


def _validate_phone(phone: str) -> None:
    if not PHONE_PATTERN.match(phone):
        raise ValueError("Номер телефону має бути у форматі +380XXXXXXXXX")


async def _get_openid_config() -> dict:
    """Fetch OpenID configuration from Silpo."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(OPENID_CONFIG_URL)
        resp.raise_for_status()
        return resp.json()


async def request_otp(phone: str, delivery_method: str = "sms") -> dict:
    """Request OTP code sent to the phone via SMS/Viber.

    This hits the REAL Silpo auth API.
    """
    _validate_phone(phone)

    # Check if we already have a valid token
    session = _sessions.get(phone, {})
    if session.get("token") and session.get("expires_at", datetime.min.replace(tzinfo=timezone.utc)) > datetime.now(tz=timezone.utc):
        return {"status": "already_authenticated", "phone": phone}

    # Generate PKCE code verifier for this session
    code_verifier = secrets.token_urlsafe(64)
    _sessions[phone] = {"code_verifier": code_verifier, "cookies": {}}

    payload = {
        "phone": phone,
        "recaptcha": None,
        "delivery_method": delivery_method,
        "phoneChannelType": 0,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(REQUEST_OTP_URL, json=payload)
        data = resp.json()

        if not resp.is_success:
            seconds_till_next = data.get("secondsTillNextOTP", 0)
            if seconds_till_next:
                return {
                    "status": "rate_limited",
                    "phone": phone,
                    "retry_after_seconds": seconds_till_next,
                }
            raise RuntimeError(f"Silpo OTP request failed: {data}")

    return {"status": "otp_sent", "phone": phone}


async def verify_otp(phone: str, code: str) -> dict:
    """Verify OTP code and complete OpenID auth flow.

    1. Sends OTP code to Silpo -> gets auth cookies
    2. Uses cookies to get OpenID authorization code (PKCE)
    3. Exchanges auth code for access token
    """
    _validate_phone(phone)
    if not re.match(r"^\d{6}$", code):
        raise ValueError("OTP код має містити 6 цифр")

    session = _sessions.get(phone)
    if not session:
        raise RuntimeError("Спочатку запросіть OTP код")

    # Step 1: Verify OTP -> get auth cookies
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        resp = await client.post(VERIFY_OTP_URL, json={
            "phone": phone,
            "otp": code,
            "phoneChannelType": 0,
        })
        data = resp.json()

        if not resp.is_success or data.get("error"):
            raise ValueError(f"Невірний OTP код: {data}")

        # Save cookies from successful OTP verification
        auth_cookies = dict(resp.cookies)
        session["cookies"] = auth_cookies

    # Step 2: OpenID authorize -> get auth code
    openid_config = await _get_openid_config()
    auth_endpoint = openid_config["authorization_endpoint"]
    token_endpoint = openid_config["token_endpoint"]

    code_verifier = session["code_verifier"]
    code_challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b"=").decode("ascii")
    )

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "state": secrets.token_urlsafe(16),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "response_mode": "query",
    }

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(auth_endpoint, params=params, cookies=auth_cookies)
        resp.raise_for_status()

        # Parse auth code from redirect URL
        parsed = urlparse(str(resp.url))
        query_params = parse_qs(parsed.query)
        auth_code = query_params.get("code", [None])[0]

        if not auth_code:
            raise RuntimeError("Не вдалося отримати код авторизації від Silpo OpenID")

    # Step 3: Exchange auth code for token
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(token_endpoint, data={
            "client_id": CLIENT_ID,
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
        })
        token_data = resp.json()

        if not resp.is_success:
            raise RuntimeError(f"Не вдалося отримати токен: {token_data}")

    access_token = token_data["access_token"]

    # Parse expiry from token (JWT)
    import json as _json
    try:
        payload_b64 = access_token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)  # pad base64
        jwt_payload = _json.loads(base64.b64decode(payload_b64))
        expires_at = datetime.fromtimestamp(jwt_payload["exp"], tz=timezone.utc)
    except Exception:
        from datetime import timedelta
        expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=1)

    # Cache the token
    session["token"] = access_token
    session["id_token"] = token_data.get("id_token")
    session["expires_at"] = expires_at

    return {
        "access_token": access_token,
        "phone": phone,
        "expires_at": expires_at.isoformat(),
    }


def get_silpo_token(phone: str) -> str | None:
    """Get cached Silpo access token for authenticated API calls."""
    session = _sessions.get(phone)
    if not session or not session.get("token"):
        return None
    if session.get("expires_at", datetime.min.replace(tzinfo=timezone.utc)) < datetime.now(tz=timezone.utc):
        return None
    return session["token"]
