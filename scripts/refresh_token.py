"""Token refresh script — run via cron or systemd timer.

Checks token expiry. If <4h left, refreshes via browser.
If token fully expired, logs warning (needs manual OTP login).
"""

import asyncio
import sys
import os

os.environ.setdefault("DISPLAY", ":99")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.silpo.browser import _token_hours_left, refresh_token, close


async def main():
    hours = _token_hours_left()
    print(f"Token: {hours:.1f}h remaining")

    if hours > 4:
        print("OK — no refresh needed")
        return

    if hours <= 0:
        print("EXPIRED — need manual OTP login!")
        return

    print("Refreshing token via browser...")
    ok = await refresh_token()
    await close()

    new_hours = _token_hours_left()
    if ok and new_hours > hours:
        print(f"OK — refreshed to {new_hours:.1f}h")
    else:
        print(f"WARN — refresh may have failed ({new_hours:.1f}h)")


asyncio.run(main())
