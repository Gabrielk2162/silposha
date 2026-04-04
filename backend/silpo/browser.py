"""Persistent browser session for Silpo interactions.

Keeps Firefox running in background to avoid 12s cold start on each request.
Uses Xvfb virtual display on headless servers.
Auto-refreshes auth token before expiry.
"""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright, Page, BrowserContext

STATE_FILE = Path(__file__).resolve().parent.parent.parent / ".browser_state.json"
AUTH_FILE = Path(__file__).resolve().parent.parent.parent / ".silpo_auth.json"
LS_FILE = Path(__file__).resolve().parent.parent.parent / ".ls_dump.json"

_pw = None
_browser = None
_context: BrowserContext | None = None
_page: Page | None = None


def _ensure_xvfb():
    """Start Xvfb if no display available."""
    if os.environ.get("DISPLAY"):
        return
    try:
        subprocess.Popen(
            ["Xvfb", ":99", "-screen", "0", "1280x720x24"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        os.environ["DISPLAY"] = ":99"
    except FileNotFoundError:
        pass


def _token_hours_left() -> float:
    """Check how many hours the current token has left."""
    for path in (LS_FILE, AUTH_FILE):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
            token = data.get("access_token", "")
            if not token or "." not in token:
                continue
            payload = token.split(".")[1]
            payload += "=" * (4 - len(payload) % 4)
            jwt = json.loads(base64.b64decode(payload))
            exp = datetime.fromtimestamp(jwt["exp"], tz=timezone.utc)
            return (exp - datetime.now(tz=timezone.utc)).total_seconds() / 3600
        except Exception:
            continue
    return 0.0


async def _save_tokens(page: Page) -> None:
    """Extract tokens from browser localStorage and save to files."""
    tokens = await page.evaluate("""() => {
        const result = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            result[key] = localStorage.getItem(key);
        }
        return result;
    }""")

    # Save full localStorage dump
    LS_FILE.write_text(json.dumps(tokens, ensure_ascii=False, indent=2))

    # Save structured auth file
    access_token = tokens.get("access_token", "")
    basket_id = tokens.get("basketId", "")
    if access_token and "." in access_token:
        try:
            payload = access_token.split(".")[1]
            payload += "=" * (4 - len(payload) % 4)
            jwt = json.loads(base64.b64decode(payload))
            exp = datetime.fromtimestamp(jwt["exp"], tz=timezone.utc)
            auth = {
                "phone": "",
                "user_id": jwt.get("sub"),
                "access_token": access_token,
                "basket_id": basket_id,
                "expires_at": exp.isoformat(),
            }
            AUTH_FILE.write_text(json.dumps(auth, indent=2))
        except Exception:
            pass


async def refresh_token() -> bool:
    """Refresh auth token via browser silent refresh.

    Opens silpo.ua with saved cookies — the SPA auto-refreshes
    the token via an invisible iframe to auth.silpo.ua.
    """
    page = await get_page()

    # Navigate triggers silent refresh automatically
    await page.goto("https://silpo.ua", wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(8)

    await _save_tokens(page)

    hours = _token_hours_left()
    return hours > 1


async def ensure_fresh_token(min_hours: float = 2.0) -> str:
    """Return a valid access token, refreshing if needed."""
    hours = _token_hours_left()
    if hours < min_hours:
        await refresh_token()

    # Return current token
    if LS_FILE.exists():
        data = json.loads(LS_FILE.read_text())
        return data.get("access_token", "")
    if AUTH_FILE.exists():
        data = json.loads(AUTH_FILE.read_text())
        return data.get("access_token", "")
    return ""


async def get_page() -> Page:
    """Get or create a persistent browser page."""
    global _pw, _browser, _context, _page

    if _page and not _page.is_closed():
        return _page

    _ensure_xvfb()

    _pw = await async_playwright().start()
    _browser = await _pw.firefox.launch(
        headless=False,
        firefox_user_prefs={"dom.webdriver.enabled": False},
    )

    storage = str(STATE_FILE) if STATE_FILE.exists() else None
    _context = await _browser.new_context(
        locale="uk-UA",
        viewport={"width": 1280, "height": 720},
        storage_state=storage,
    )
    _page = await _context.new_page()
    await _page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )

    # Block images, fonts, analytics — speeds up navigation 2-3x
    await _page.route("**/*.{png,jpg,jpeg,webp,gif,svg,woff,woff2,ttf,eot}", lambda r: r.abort())
    await _page.route("**/google*/**", lambda r: r.abort())
    await _page.route("**/doubleclick**", lambda r: r.abort())
    await _page.route("**/analytics**", lambda r: r.abort())
    await _page.route("**/sentry**", lambda r: r.abort())
    await _page.route("**/facebook**", lambda r: r.abort())
    await _page.route("**/gtm**", lambda r: r.abort())

    # Navigate once to pass Cloudflare
    await _page.goto("https://silpo.ua", wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(5)

    # Save tokens on first load
    await _save_tokens(_page)

    return _page


async def close():
    """Close browser and save state."""
    global _pw, _browser, _context, _page
    if _page and not _page.is_closed():
        await _save_tokens(_page)
    if _browser:
        if _context:
            await _context.storage_state(path=str(STATE_FILE))
        await _browser.close()
    if _pw:
        await _pw.stop()
    _pw = _browser = _context = _page = None
