"""Re-query the Internet Archive for URLs that urlhealth labelled LIKELY_HALLUCINATED.

All of these URLs were cited and read by annotators in 2023, so a "never
existed" label is a false positive by construction. This script records the raw
responses of the availability API (as used by urlhealth) and of the CDX API,
so that archive gaps can be separated from failed lookups. One request every
GAP seconds.

Usage: REQUESTS_CA_BUNDLE=... .venv/bin/python -I src/check_wayback_gaps.py <urlhealth_jsonl> <out_jsonl>
"""
import json, sys, time

import requests

GAP = 6.0
UA = "CiteDriftCheck/0.1 (research prototype; archive coverage check)"


def get(url, params):
    time.sleep(GAP)
    try:
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=30)
        return r.status_code, r.text[:2000]
    except requests.RequestException as e:
        return None, f"{type(e).__name__}: {e}"[:300]


def main():
    src, out_p = sys.argv[1:3]
    urls = [r["url"] for r in map(json.loads, open(src)) if r["url_status"] == "LIKELY_HALLUCINATED"]
    with open(out_p, "w") as out:
        for u in urls:
            a_st, a_body = get("https://archive.org/wayback/available", {"url": u})
            c_st, c_body = get("https://web.archive.org/cdx/search/cdx", {"url": u, "limit": "3", "output": "json"})
            avail = None
            try:
                avail = bool(json.loads(a_body).get("archived_snapshots", {}).get("closest", {}).get("available"))
            except (ValueError, AttributeError):
                pass
            cdx_rows = None
            try:
                cdx_rows = max(0, len(json.loads(c_body)) - 1) if c_st == 200 else None
            except ValueError:
                pass
            out.write(json.dumps({"url": u, "avail_status": a_st, "avail_found": avail, "cdx_status": c_st,
                                  "cdx_rows": cdx_rows, "avail_body": a_body[:300], "cdx_body": c_body[:300],
                                  "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
