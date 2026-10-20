"""Link-state classification for a cited URL at check time.

Three groups:
  reachable    ok        same URL serves a readable page
               moved     redirect to another URL whose content matches the cited page
  lost         dead      4xx/410/DNS or connection failure that persists in a browser
               soft404   200 but an error/empty page
               away      redirect to a home page or a different document
  unverifiable blocked   bot wall or 401/403/429 that persists in an ordinary browser, or a page that the
                         browser reached only after a bot interstitial (we do not count passing one as access)
               filtered  answered by the checker's own network filter, not by the site
               skipped   not requested (the site asks automated clients not to)
               transient 5xx, timeout or TLS error in both attempts
               empty     page loads but yields no readable text and no error signal

Decisions use the plain HTTP fetch, overridden by the one-time browser re-check
when it ran. Redirect targets count as "moved" when the old text's word
5-gram containment >= MOVED_CONTAINMENT or the title similarity >= MOVED_TITLE.
"""
import re, urllib.parse

from .markers import CHALLENGE_MARKERS, INTERSTITIAL_STATUSES

GROUP = {"ok": "reachable", "moved": "reachable", "dead": "lost", "soft404": "lost", "away": "lost",
         "blocked": "unverifiable", "filtered": "unverifiable", "skipped": "unverifiable",
         "transient": "unverifiable", "empty": "unverifiable"}
MOVED_CONTAINMENT = 0.3
MOVED_TITLE = 90
MIN_TEXT = 200
SOFT404 = re.compile(r"\b(page not found|404|no longer available|doesn.t exist|does not exist|"
                     r"has been removed|cannot be found|could not be found|page you requested)\b", re.I)


def _host(u):
    return urllib.parse.urlsplit(u).netloc.lower().removeprefix("www.")


def same_doc(a, b):
    pa, pb = urllib.parse.urlsplit(a), urllib.parse.urlsplit(b)
    return _host(a) == _host(b) and pa.path.rstrip("/") == pb.path.rstrip("/")


def _status_state(status):
    if status in (401, 402, 403, 429, 451):
        return "blocked"
    if status is not None and 500 <= status < 600:
        return "transient"
    if status is not None and status >= 400:
        return "dead"
    return None


def classify(f, now_text_head=""):
    """f: one record of url_features.jsonl. now_text_head: first ~500 chars of current main text."""
    if f["http_outcome"] == "robots_disallowed":
        return "skipped"
    if f["network_filtered_http"] and f["browser_outcome"] is None:
        return "filtered"
    if f["browser_outcome"] is not None:  # browser re-check overrides the plain fetch
        if f["browser_outcome"] == "browser_error":
            e = f["browser_error"] or ""
            if "ERR_NAME_NOT_RESOLVED" in e or "ERR_CONNECTION_REFUSED" in e:
                return "dead"
            return "transient"
        if f["browser_challenge"]:
            return "blocked"
        if any(st in INTERSTITIAL_STATUSES for st in (f.get("browser_statuses") or [])[:-1]):
            return "blocked"  # the page appeared only after a bot interstitial ran in the automated browser
        status, final = f["browser_status"], f["browser_final_url"]
    else:
        if f["http_outcome"] in ("timeout", "error"):
            return "transient"
        if f["http_outcome"] == "connection_error":
            return "dead"
        if f["http_outcome"] == "ssl_error":
            return "transient"
        status, final = f["http_status"], f["http_final_url"]
    head = (now_text_head or "")[:500].lower()
    if f["len_main_now"] < 1500 and any(m in head for m in CHALLENGE_MARKERS):
        return "blocked"
    s = _status_state(status)
    if s:
        return s
    if final and not same_doc(f["url"], final):
        c, t = f.get("containment_dom") or 0, f.get("title_sim") or 0
        if c >= MOVED_CONTAINMENT or t >= MOVED_TITLE:
            return "moved"
        return "away"
    n = f["len_main_now"]
    title = f.get("title_now") or ""
    if n < 2000 and (SOFT404.search(now_text_head[:500]) or SOFT404.search(title)):
        return "soft404"
    if n < MIN_TEXT:
        return "empty"
    return "ok"
