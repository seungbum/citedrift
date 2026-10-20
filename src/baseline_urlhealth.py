"""Baseline: run urlhealth 0.1.0 (Rao, Wong, Callison-Burch 2026; MIT) on every cited URL.

urlhealth sends HEAD (GET on 405/403/501) with a browser User-Agent and labels
a URL LIVE (200), DEAD (404 with a Wayback snapshot), LIKELY_HALLUCINATED
(404, no snapshot) or UNKNOWN (anything else). We call it unchanged and only
add politeness: one request per host every HOST_GAP seconds, Wayback lookups
spaced WAYBACK_GAP seconds apart, and the same URL exclusions as our own
fetch (URLs our fetcher did not request are not requested here either).

Usage: .venv/bin/python -I src/baseline_urlhealth.py <live_dir> <pairs_jsonl> <out_jsonl>
"""
import json, os, sys, threading, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor

import urlhealth
import urlhealth.checker as uc

HOST_GAP = 5.0
WAYBACK_GAP = 4.0
WORKERS = 6

_lock = threading.Lock()
_next = {}


def wait(key, gap):
    while True:
        with _lock:
            now = time.time()
            t = _next.get(key, 0)
            if now >= t:
                _next[key] = now + gap
                return
            d = t - now
        time.sleep(d)


_orig_wayback = uc._get_wayback_snapshot


def _polite_wayback(url, timeout=10):
    wait("__wayback__", WAYBACK_GAP)
    return _orig_wayback(url, timeout=timeout)


uc._get_wayback_snapshot = _polite_wayback


def check(url):
    wait(urllib.parse.urlsplit(url).netloc, HOST_GAP)
    t0 = time.time()
    r = urlhealth.inspect(url)
    return {"url": url, "url_status": str(r["url_status"].value), "status_code": r["status_code"],
            "wayback_url": r["wayback_url"], "seconds": time.time() - t0,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def main():
    live_dir, pairs_path, out_path = sys.argv[1:4]
    skip = {r["url"] for r in map(json.loads, open(os.path.join(live_dir, "fetch_log.jsonl")))
            if r.get("outcome") == "robots_disallowed"}
    urls = [u for u in dict.fromkeys(json.loads(l)["url"] for l in open(pairs_path)) if u not in skip]
    done = set()
    if os.path.exists(out_path):
        done = {json.loads(l)["url"] for l in open(out_path)}
    todo = [u for u in urls if u not in done]
    print(f"{len(todo)} urls ({len(skip)} excluded)", flush=True)
    with open(out_path, "a") as out, ThreadPoolExecutor(WORKERS) as ex:
        for i, rec in enumerate(ex.map(check, todo), 1):
            out.write(json.dumps(rec) + "\n")
            out.flush()
            if i % 100 == 0:
                print(i, flush=True)


if __name__ == "__main__":
    main()
