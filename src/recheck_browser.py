"""One-time browser re-check of URLs that the plain HTTP fetch could not read.

Separates bot-blocking (the page opens in an ordinary browser) from real loss.
Targets: HTTP 401/403/429/5xx, timeouts and connection/TLS errors in
data/live/fetch_log.jsonl, excluding pages answered by the local network
filter (those are unverifiable from our vantage point and are not retried),
plus an optional list of extra URLs (pages that returned 200 but almost no
text to a plain HTTP client, typically script-rendered).

Politeness: one visit per URL, one tab, at least HOST_GAP seconds between
requests to the same host, no CAPTCHA solving, no paywall circumvention, no
retries. The rendered HTML is kept locally (gzip) and never redistributed.

Usage: xvfb-run -a .venv/bin/python -I src/recheck_browser.py <live_dir> <out_dir> [extra_urls.txt]
"""
import gzip, hashlib, json, os, sys, time, urllib.parse

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift.markers import CHALLENGE_MARKERS, FILTER_MARKERS  # noqa: E402

HOST_GAP = 5.0
SETTLE_MS = 7000  # let JS interstitials finish before reading the DOM
MAX_SETTLES = 3  # re-read up to three times while an interstitial is still shown
NAV_TIMEOUT_MS = 30000


def is_challenge(title, body_text):
    """Interstitial or block page: marker in the title, or in a short visible body."""
    t = (title or "").lower()
    b = (body_text or "").lower()
    return any(m in t for m in CHALLENGE_MARKERS) or \
        (len(b) < 1500 and any(m in b for m in CHALLENGE_MARKERS))


def is_network_filtered(live_dir, rec):
    if not rec.get("file"):
        return False
    with gzip.open(os.path.join(live_dir, "html", rec["file"]), "rt", errors="replace") as h:
        head = h.read(30000)
    return any(m in head for m in FILTER_MARKERS)


def targets(live_dir):
    out = []
    with open(os.path.join(live_dir, "fetch_log.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            o, st = r.get("outcome"), r.get("status", 0)
            retry = (o in ("timeout", "connection_error", "ssl_error", "error")) or \
                    (o == "http" and (st in (401, 403, 429) or st >= 500))
            if retry and not is_network_filtered(live_dir, r):
                out.append(r["url"])
    return out


def proxy_cfg():
    p = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not p:
        return None
    bypass = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    return {"server": p, "bypass": bypass}


def main():
    live_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.join(out_dir, "html"), exist_ok=True)
    log_path = os.path.join(out_dir, "browser_log.jsonl")
    done = set()
    if os.path.exists(log_path):
        with open(log_path) as f:
            done = {json.loads(l)["url"] for l in f}
    todo = targets(live_dir)
    if len(sys.argv) > 3:  # optional file of extra URLs (e.g. pages whose plain-fetch text was empty)
        todo += [l.strip() for l in open(sys.argv[3]) if l.strip()]
    todo = [u for u in dict.fromkeys(todo) if u not in done]
    print(f"{len(todo)} urls to re-check", flush=True)
    last = {}
    with sync_playwright() as pw, open(log_path, "a") as log:
        # Ordinary (headed) Chrome inside a virtual display: run under xvfb-run.
        browser = pw.chromium.launch(channel="chrome", headless=False, proxy=proxy_cfg())
        ctx = browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
        for i, url in enumerate(todo, 1):
            host = urllib.parse.urlsplit(url).netloc
            gap = HOST_GAP - (time.time() - last.get(host, 0))
            if gap > 0:
                time.sleep(gap)
            last[host] = time.time()
            rec = {"url": url, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            page = ctx.new_page()  # fresh tab so a previous page's scripts cannot interfere
            status = []
            page.on("response", lambda r: status.append(r.status) if r.request.is_navigation_request()
                    and r.frame == page.main_frame else None)
            try:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                except Exception as e:  # interstitials that reload themselves interrupt goto
                    if "interrupted by another navigation" not in str(e):
                        raise
                html, title, body = "", "", ""
                for _ in range(MAX_SETTLES):
                    page.wait_for_timeout(SETTLE_MS)
                    try:
                        html, title = page.content(), page.title()
                        body = page.evaluate("document.body ? document.body.innerText : ''")
                    except Exception:  # page is mid-navigation; try again after the next settle
                        continue
                    if not is_challenge(title, body):
                        break
                rec.update(outcome="browser", status=status[-1] if status else None, statuses=status,
                           final_url=page.url, title=title[:200], n_bytes=len(html),
                           n_text=len(body), challenge=is_challenge(title, body),
                           network_filtered=any(m in html for m in FILTER_MARKERS))
                name = hashlib.sha1(url.encode()).hexdigest() + ".html.gz"
                with gzip.open(os.path.join(out_dir, "html", name), "wt") as f:
                    f.write(html)
                rec["file"] = name
            except Exception as e:
                rec.update(outcome="browser_error", error=f"{type(e).__name__}: {str(e)[:200]}")
            finally:
                page.close()
            log.write(json.dumps(rec) + "\n")
            log.flush()
            if i % 20 == 0:
                print(f"{i}/{len(todo)}", flush=True)
        browser.close()
    print("done", flush=True)


if __name__ == "__main__":
    main()
