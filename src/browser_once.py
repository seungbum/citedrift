"""Open one URL once in an ordinary (headed) Chrome and write the result as JSON.

Used by check mode for pages that refused the plain client; same procedure as the
batch re-check (src/recheck_browser.py): fresh tab, wait for interstitials up to
MAX_SETTLES x SETTLE_MS, no challenge solving, no login, no paywall bypass.
Run it under xvfb-run so no window appears on the user's screen.

Usage: xvfb-run -a .venv/bin/python -I src/browser_once.py <url> <out.json>
"""
import json, os, sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift.markers import FILTER_MARKERS  # noqa: E402
from recheck_browser import MAX_SETTLES, NAV_TIMEOUT_MS, SETTLE_MS, is_challenge, proxy_cfg  # noqa: E402


def main():
    url, out = sys.argv[1], sys.argv[2]
    rec = {"url": url}
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=False, proxy=proxy_cfg())
        page = b.new_context(locale="en-US", viewport={"width": 1280, "height": 900}).new_page()
        status = []
        page.on("response", lambda r: status.append(r.status) if r.request.is_navigation_request()
                and r.frame == page.main_frame else None)
        try:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            except Exception as e:  # interstitials that reload themselves interrupt goto
                if "interrupted by another navigation" not in str(e):
                    raise
            html = title = body = ""
            for _ in range(MAX_SETTLES):
                page.wait_for_timeout(SETTLE_MS)
                try:
                    html, title = page.content(), page.title()
                    body = page.evaluate("document.body ? document.body.innerText : ''")
                except Exception:
                    continue
                if not is_challenge(title, body):
                    break
            rec.update(outcome="browser", status=status[-1] if status else None, statuses=status, final_url=page.url,
                       challenge=is_challenge(title, body), html=html,
                       network_filtered=any(m in html for m in FILTER_MARKERS))
        except Exception as e:
            rec.update(outcome="browser_error", error=f"{type(e).__name__}: {str(e)[:200]}")
        b.close()
    json.dump(rec, open(out, "w"))


if __name__ == "__main__":
    main()
