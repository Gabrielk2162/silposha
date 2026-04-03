"""Interactive Silpo OTP login via browser.

Usage: python scripts/login.py [phone_number]
Default phone: +380XXXXXXXXX (prompted if not provided)
"""

import asyncio
import json
import base64
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("DISPLAY", ":99")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

AUTH_FILE = Path(__file__).resolve().parent.parent / ".silpo_auth.json"
LS_FILE = Path(__file__).resolve().parent.parent / ".ls_dump.json"
STATE_FILE = Path(__file__).resolve().parent.parent / ".browser_state.json"


async def login(phone: str):
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.firefox.launch(
        headless=False,
        firefox_user_prefs={"dom.webdriver.enabled": False},
    )
    context = await browser.new_context(locale="uk-UA", viewport={"width": 1280, "height": 720})
    page = await context.new_page()
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

    print("Opening silpo.ua...")
    await page.goto("https://silpo.ua", wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(6)

    print("Clicking login...")
    await page.locator("button").filter(has_text="Увійти").click()
    await asyncio.sleep(8)

    # Find auth iframe
    auth_frame = None
    for f in page.frames:
        if "auth.silpo.ua" in f.url:
            auth_frame = f
            break

    if not auth_frame:
        print("ERROR: auth frame not found!")
        await browser.close()
        await pw.stop()
        return

    # Enter phone (without +380)
    digits = phone.replace("+380", "")
    await auth_frame.locator('input[name="phoneNumber"]').fill(digits)
    await asyncio.sleep(1)
    await auth_frame.locator('button[type="submit"]').click()
    print(f"OTP sent to {phone}")

    # Wait for code
    code = input("Enter OTP code from SMS: ").strip()

    # Enter OTP
    otp_input = auth_frame.locator('input:not([name="phoneNumber"])').first
    await otp_input.fill(code)
    await asyncio.sleep(1)

    submit = auth_frame.locator('button[type="submit"]')
    if await submit.is_visible():
        await submit.click()

    print("Waiting for auth...")
    await asyncio.sleep(10)

    # Check login
    logged_in = not await page.locator("button").filter(has_text="Увійти").is_visible()
    if not logged_in:
        print("ERROR: login failed!")
        await browser.close()
        await pw.stop()
        return

    # Extract tokens
    tokens = await page.evaluate("""() => {
        const result = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            result[key] = localStorage.getItem(key);
        }
        return result;
    }""")

    LS_FILE.write_text(json.dumps(tokens, ensure_ascii=False, indent=2))

    access_token = tokens.get("access_token", "")
    basket_id = tokens.get("basketId", "")

    if access_token and "." in access_token:
        payload = access_token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        jwt = json.loads(base64.b64decode(payload))
        exp = datetime.fromtimestamp(jwt["exp"], tz=timezone.utc)

        auth = {
            "phone": phone,
            "user_id": jwt.get("sub"),
            "access_token": access_token,
            "basket_id": basket_id,
            "expires_at": exp.isoformat(),
        }
        AUTH_FILE.write_text(json.dumps(auth, indent=2))
        print(f"\nLogged in! Token expires: {exp}")
    else:
        print("WARNING: could not extract token")

    await context.storage_state(path=str(STATE_FILE))
    await browser.close()
    await pw.stop()
    print("Done!")


if __name__ == "__main__":
    phone = sys.argv[1] if len(sys.argv) > 1 else input("Phone (+380...): ").strip()
    asyncio.run(login(phone))
