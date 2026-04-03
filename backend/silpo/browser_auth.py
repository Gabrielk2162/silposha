"""Silpo authentication via Playwright to bypass Cloudflare."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright

AUTH_STATE_PATH = Path(__file__).resolve().parent.parent.parent / ".silpo_auth.json"

SILPO_LOGIN_URL = "https://silpo.ua"
AUTH_API_PATTERN = re.compile(r"auth\.silpo\.ua/api/v2/Login")


async def request_otp(phone: str) -> dict:
    """Open Silpo in a real browser, enter phone, trigger OTP.

    Returns browser context info to continue with verify_otp().
    """
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        locale="uk-UA",
    )
    page = await context.new_page()

    # Go to silpo.ua and click login
    await page.goto(SILPO_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    # Find and click login/profile button
    login_btn = page.locator('[data-marker="Header Profile"]').first
    if not await login_btn.is_visible():
        # Try alternative selectors
        login_btn = page.locator('button:has-text("Увійти")').first
    if not await login_btn.is_visible():
        login_btn = page.locator('[href*="login"], [href*="auth"], .header-profile, .login-btn').first

    await login_btn.click()
    await page.wait_for_timeout(2000)

    # Enter phone number
    phone_input = page.locator('input[type="tel"]').first
    await phone_input.wait_for(state="visible", timeout=10000)

    # Clear and type phone - strip +380 prefix if the input already has it
    digits = phone.replace("+380", "")
    await phone_input.click()
    await phone_input.fill(digits)
    await page.wait_for_timeout(500)

    # Click send OTP button
    submit_btn = page.locator('button[type="submit"]').first
    if not await submit_btn.is_visible():
        submit_btn = page.locator('button:has-text("Отримати код")').first
    if not await submit_btn.is_visible():
        submit_btn = page.locator('button:has-text("Надіслати")').first

    await submit_btn.click()
    await page.wait_for_timeout(3000)

    # Save state for verify step - store context reference
    state = await context.storage_state()

    # We need to keep the browser alive, so save references globally
    _active_sessions[phone] = {
        "pw": pw,
        "browser": browser,
        "context": context,
        "page": page,
    }

    # Check if there's an error message
    error = page.locator('.error-message, .form-error, [class*="error"]').first
    if await error.is_visible():
        error_text = await error.text_content()
        return {"status": "error", "message": error_text}

    return {"status": "otp_sent", "phone": phone}


async def verify_otp(phone: str, code: str) -> dict:
    """Enter OTP code in the browser and complete auth."""
    session = _active_sessions.get(phone)
    if not session:
        return {"status": "error", "message": "No active session. Call request_otp first."}

    page = session["page"]
    context = session["context"]

    # Find OTP input(s) and enter code
    otp_inputs = page.locator('input[type="tel"], input[type="number"], input[inputmode="numeric"]')
    count = await otp_inputs.count()

    if count >= 6:
        # Individual digit inputs
        for i, digit in enumerate(code[:6]):
            await otp_inputs.nth(i).fill(digit)
            await page.wait_for_timeout(100)
    elif count >= 1:
        # Single input field
        await otp_inputs.first.fill(code)
    else:
        # Try generic text input
        inp = page.locator('input').first
        await inp.fill(code)

    await page.wait_for_timeout(1000)

    # Click verify/confirm button if present
    confirm_btn = page.locator('button[type="submit"]').first
    if await confirm_btn.is_visible():
        await confirm_btn.click()

    # Wait for auth to complete - look for redirect or token
    await page.wait_for_timeout(5000)

    # Extract tokens from cookies and localStorage
    cookies = await context.cookies()

    # Get localStorage tokens
    tokens = await page.evaluate("""() => {
        const result = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key.toLowerCase().includes('token') ||
                key.toLowerCase().includes('auth') ||
                key.toLowerCase().includes('user') ||
                key.toLowerCase().includes('oidc')) {
                result[key] = localStorage.getItem(key);
            }
        }
        return result;
    }""")

    # Save auth state
    auth_data = {
        "phone": phone,
        "cookies": {c["name"]: c["value"] for c in cookies},
        "tokens": tokens,
        "url": page.url,
    }

    AUTH_STATE_PATH.write_text(json.dumps(auth_data, ensure_ascii=False, indent=2))

    # Cleanup browser
    await session["browser"].close()
    await session["pw"].stop()
    del _active_sessions[phone]

    return {
        "status": "authenticated",
        "phone": phone,
        "saved_to": str(AUTH_STATE_PATH),
        "cookies_count": len(cookies),
        "tokens_found": list(tokens.keys()),
    }


def get_saved_auth() -> dict | None:
    """Load saved auth state."""
    if AUTH_STATE_PATH.exists():
        return json.loads(AUTH_STATE_PATH.read_text())
    return None


# Keep browser sessions alive between OTP request and verify
_active_sessions: dict[str, dict] = {}
