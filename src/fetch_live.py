"""Polite live re-fetch of pages cited in Liu et al. (2023) verifiability judgments.

Fetches each unique source_url once, records HTTP outcome and redirect chain,
and stores the HTML (gzip) locally for text extraction. Page bodies are kept
local and never redistributed.

Politeness: honours robots.txt for our UA, at most one request per host every
HOST_GAP seconds, small global concurrency, 20 s timeout, 5 MB cap.

Usage: python3 -I fetch_live.py <judgments_dir> <out_dir> [splits...]
"""
import gzip, hashlib, json, os, sys, threading, time, urllib.parse, urllib.robotparser
from concurrent.futures import ThreadPoolExecutor

import requests

UA = "CiteDriftCheck/0.1 (research prototype; re-checks pages cited by AI search answers)"
HOST_GAP = 5.0
WORKERS = 6
TIMEOUT = 20
MAX_BYTES = 5 * 1024 * 1024

_host_lock = threading.Lock()
_host_next = {}
_robots = {}
_robots_lock = threading.Lock()


def wait_host(host):
    while True:
        with _host_lock:
            now = time.time()
            t = _host_next.get(host, 0)
            if now >= t:
                _host_next[host] = now + HOST_GAP
                return
            delay = t - now
        time.sleep(delay)


def robots_ok(url):
    p = urllib.parse.urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    with _robots_lock:
        rp = _robots.get(base)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            wait_host(p.netloc)
            r = requests.get(base + "/robots.txt", headers={"User-Agent": UA}, timeout=TIMEOUT)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        with _robots_lock:
            _robots[base] = rp
    return rp.can_fetch(UA, url)


def fetch(url, out_dir):
    rec = {"url": url, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        if not robots_ok(url):
            rec["outcome"] = "robots_disallowed"
            return rec
        wait_host(urllib.parse.urlsplit(url).netloc)
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.5"},
                         timeout=TIMEOUT, stream=True, allow_redirects=True)
        body = b""
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > MAX_BYTES:
                rec["truncated"] = True
                break
        rec.update(outcome="http", status=r.status_code, final_url=r.url,
                   history=[(h.status_code, h.headers.get("Location")) for h in r.history],
                   content_type=r.headers.get("Content-Type"), n_bytes=len(body),
                   sha256=hashlib.sha256(body).hexdigest())
        if body:
            name = hashlib.sha1(url.encode()).hexdigest() + ".html.gz"
            with gzip.open(os.path.join(out_dir, "html", name), "wb") as f:
                f.write(body)
            rec["file"] = name
    except requests.exceptions.SSLError as e:
        rec.update(outcome="ssl_error", error=str(e)[:200])
    except requests.exceptions.ConnectionError as e:
        rec.update(outcome="connection_error", error=str(e)[:200])
    except requests.exceptions.Timeout:
        rec.update(outcome="timeout")
    except Exception as e:  # keep going on anything else
        rec.update(outcome="error", error=f"{type(e).__name__}: {str(e)[:200]}")
    return rec


def main():
    jdir, out_dir = sys.argv[1], sys.argv[2]
    splits = sys.argv[3:] or ["dev", "test"]
    os.makedirs(os.path.join(out_dir, "html"), exist_ok=True)
    urls = []
    for sp in splits:
        with gzip.open(os.path.join(jdir, f"verifiability_judgments_{sp}.jsonl.gz"), "rt") as f:
            for line in f:
                urls.append(json.loads(line)["source_url"])
    urls = list(dict.fromkeys(urls))
    log_path = os.path.join(out_dir, "fetch_log.jsonl")
    done = set()
    if os.path.exists(log_path):
        with open(log_path) as f:
            done = {json.loads(l)["url"] for l in f}
    todo = [u for u in urls if u not in done][: int(os.environ.get("LIMIT", "0")) or None]
    print(f"{len(urls)} unique urls, {len(todo)} to fetch", flush=True)
    lock = threading.Lock()
    with open(log_path, "a") as log, ThreadPoolExecutor(WORKERS) as ex:
        for i, rec in enumerate(ex.map(lambda u: fetch(u, out_dir), todo), 1):
            with lock:
                log.write(json.dumps(rec) + "\n")
                log.flush()
            if i % 50 == 0:
                print(f"{i}/{len(todo)}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
