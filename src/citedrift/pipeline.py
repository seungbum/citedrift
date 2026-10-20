"""Check one AI-search answer: statement -> cited URL -> support then and now.

Input: answer text with [n] markers and a list of citation URLs (1-based),
optionally the date the answer was produced. For every (statement, citation):
  1. fetch the current page once (identified client, per-host spacing);
  2. optionally fetch the archived snapshot closest to the citation date from
     the Internet Archive (the "then" page);
  3. classify the link state, judge support on both versions, and assign
     one of the drift classes; the best-matching passage is returned as a
     short excerpt for display.
"""
import re, time, urllib.parse, urllib.robotparser

import requests
from nltk.tokenize import sent_tokenize
from rapidfuzz import fuzz

from .linkstate import GROUP, classify, same_doc
from .markers import CHALLENGE_MARKERS, FILTER_MARKERS
from .textutil import containment, dom_text, html_title, main_text

UA = "CiteDrift/0.1 (research prototype; checks pages cited in an AI answer on user request)"
TIMEOUT = 20
HOST_GAP = 2.0
MAX_BYTES = 5 * 1024 * 1024
EXCERPT_CHARS = 300
MARK = re.compile(r"\[(\d+)\]")
NO_SPLIT = re.compile(r"\b(No|no|Nos|vol|Vol|pp|p|vs|approx|Fig|fig)\.\s+(?=\d)")

_last = {}
_robots = {}


def _wait(host):
    d = HOST_GAP - (time.time() - _last.get(host, 0))
    if d > 0:
        time.sleep(d)
    _last[host] = time.time()


def _allowed(url):
    p = urllib.parse.urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            _wait(p.netloc)
            r = requests.get(base + "/robots.txt", headers={"User-Agent": UA}, timeout=TIMEOUT)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except requests.RequestException:
            rp.parse([])
        _robots[base] = rp
    return _robots[base].can_fetch(UA, url)


def fetch(url):
    """Return a url_features-like record plus html for the current page."""
    rec = {"url": url, "http_outcome": None, "http_status": None, "http_final_url": None,
           "network_filtered_http": False, "browser_outcome": None, "browser_status": None,
           "browser_final_url": None, "browser_challenge": None, "browser_error": None}
    html = ""
    try:
        if not _allowed(url):
            rec["http_outcome"] = "robots_disallowed"
            return rec, html
        _wait(urllib.parse.urlsplit(url).netloc)
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.5"},
                         timeout=TIMEOUT, stream=True)
        body = b""
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > MAX_BYTES:
                break
        html = body.decode(r.encoding or "utf-8", errors="replace")
        rec.update(http_outcome="http", http_status=r.status_code, http_final_url=r.url,
                   network_filtered_http=any(m in html[:30000] for m in FILTER_MARKERS))
        if r.status_code in (401, 403, 429) and any(m in html[:50000].lower() for m in CHALLENGE_MARKERS):
            rec["bot_wall"] = True
    except requests.exceptions.Timeout:
        rec["http_outcome"] = "timeout"
    except requests.exceptions.SSLError:
        rec["http_outcome"] = "ssl_error"
    except requests.exceptions.ConnectionError:
        rec["http_outcome"] = "connection_error"
    except requests.RequestException:
        rec["http_outcome"] = "error"
    return rec, html


def wayback(url, when, retries=1):
    """Like _wayback_once, with `retries` retries after a short pause when the lookup fails."""
    for k in range(retries + 1):
        out = _wayback_once(url, when)
        if not out[2].startswith("lookup_failed") or k == retries:
            return out
        time.sleep(3)


def _wayback_once(url, when):
    """(html, snapshot timestamp, status) for the archived capture closest to `when` (YYYYMMDD).

    Uses the CDX API and keeps "no capture" apart from "lookup failed" (e.g. HTTP 429),
    which must not be read as evidence that the page never existed.
    """
    try:
        _wait("web.archive.org")
        r = requests.get("https://web.archive.org/cdx/search/cdx",
                         params={"url": url, "output": "json", "limit": "1", "closest": when,
                                 "sort": "closest", "filter": "statuscode:200", "fl": "timestamp"},
                         headers={"User-Agent": UA}, timeout=TIMEOUT)
        if r.status_code != 200:
            return "", None, f"lookup_failed_{r.status_code}"
        rows = r.json() if r.text.strip() else []
        if len(rows) < 2:
            return "", None, "no_capture"
        ts = rows[1][0]
        _wait("web.archive.org")
        h = requests.get(f"https://web.archive.org/web/{ts}id_/{url}", headers={"User-Agent": UA}, timeout=TIMEOUT)
        return (h.text if h.status_code == 200 else ""), ts, ("ok" if h.status_code == 200 else f"fetch_failed_{h.status_code}")
    except requests.exceptions.Timeout:
        return "", None, "lookup_failed_timeout"
    except requests.exceptions.ConnectionError:
        return "", None, "lookup_failed_connection"
    except (requests.RequestException, ValueError) as e:
        return "", None, f"lookup_failed_{type(e).__name__}"


def split_answer(answer, n_citations):
    """[(statement_without_markers, [citation indexes 0-based])] for sentences that cite something.

    Markers placed right after a sentence's final period ("... tall.[1] Next sentence") end up at the
    start of the next sentence after splitting; they are given back to the sentence before.
    """
    lead = re.compile(r"^\s*((?:\[\d+\]\s*)+)")
    sents = []
    for block in answer.split("\n"):
        block = NO_SPLIT.sub(lambda m: m.group(1) + ".\u2060", block)  # "No. 1" is not a sentence end
        for s in sent_tokenize(block):
            s = s.replace("\u2060", " ")
            m = lead.match(s)
            if m and sents:
                sents[-1] += " " + m.group(1).strip()
                s = s[m.end():]
            sents.append(s)
    out = []
    for s in sents:
        refs = [int(m) - 1 for m in MARK.findall(s) if 0 < int(m) <= n_citations]
        clean = re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s+", " ", MARK.sub("", s).replace("**", ""))).strip()
        if refs and clean:
            out.append((clean, sorted(set(refs))))
    return out


def best_sentence(text, query):
    best, score = "", 0
    for s in sent_tokenize(text or ""):
        if 20 <= len(s) <= 1000:
            v = fuzz.token_set_ratio(query, s)
            if v > score:
                best, score = s, v
    return best[:EXCERPT_CHARS], score


class Checker:
    def __init__(self, judge, params, threshold, explainer=None):
        from e1_combo import combine  # noqa: F401  (src/ on sys.path)
        from baseline_ngram import ngram_score  # noqa: F401
        self.judge, self.params, self.thr, self.explainer = judge, params, threshold, explainer
        self._combine, self._ngram = combine, ngram_score

    def support(self, text, claim):
        if not text or len(text) < 50:
            return None, None
        r = self.judge.score(text, claim)
        s = float(self._combine(self.params, r["prob"], self._ngram(claim, text)))
        return s, r["chunks"][r["best_chunk"]]

    def page(self, u, cited_at=None, then_text=None, browser=None):
        """Fetch and classify one cited URL. then_text: page text saved at citation time, if any.
        browser: optional callable url -> html used once when the plain fetch is refused or empty."""
        rec, html = fetch(u)
        rechecked = False
        if browser is not None and (rec.get("bot_wall") or rec.get("http_outcome") in ("timeout", "error", "connection_error")
                                    or rec.get("http_status") in (401, 403, 429) or (rec.get("http_status") or 0) >= 500
                                    or len(main_text(html)) < 200) and rec.get("http_outcome") != "robots_disallowed" \
                and not rec.get("network_filtered_http"):
            b = browser(u)
            if b is not None:
                rechecked = True
                rec.update(browser_outcome=b["outcome"], browser_status=b.get("status"),
                           browser_final_url=b.get("final_url"), browser_challenge=b.get("challenge"),
                           browser_statuses=b.get("statuses"),
                           browser_error=b.get("error"))
                rec.pop("bot_wall", None)
                html = b.get("html") or ""
        if then_text is not None:
            then_html, ts, arch = "", None, "provided"
        else:
            then_html, ts, arch = wayback(u, cited_at) if cited_at else ("", None, "not_requested")
            then_text = main_text(then_html)
        now_main, now_dom = main_text(html), dom_text(html)
        rec.update(len_main_now=len(now_main), containment_dom=containment(then_text, now_dom) if then_text else None,
                   title_sim=None, title_now=html_title(html))
        if then_html and html:
            rec["title_sim"] = fuzz.token_set_ratio(html_title(then_html).lower(), html_title(html).lower())
        final = rec.get("browser_final_url") or rec.get("http_final_url")
        if not then_text and final and not same_doc(u, final):
            # nothing to compare the redirect target with: a redirect to a site root counts as lost,
            # any other redirect as a move whose support the judge then decides
            rec["title_sim"] = 0 if not urllib.parse.urlsplit(final).path.strip("/") else 100
        state = "blocked" if rec.get("bot_wall") else classify(rec, now_main[:500])
        return {"state": state, "group": GROUP[state], "now_main": now_main, "now_dom": now_dom,
                "then_text": then_text, "snapshot": ts, "archive": arch, "final_url": final,
                "status": rec.get("browser_status") or rec.get("http_status"), "browser_rechecked": rechecked}

    def judge_pair(self, stmt, i, u, pg, explain=False):
        then_s, then_chunk = self.support(pg["then_text"], stmt)
        now_s = now_chunk = None
        if pg["group"] == "reachable":
            now_s, now_chunk = self.support(pg["now_main"], stmt)
            dom_s, dom_chunk = self.support(pg["now_dom"], stmt)
            if dom_s is not None and (now_s is None or dom_s > now_s):
                now_s, now_chunk = dom_s, dom_chunk
        then_ok = None if then_s is None else then_s >= self.thr
        now_ok = None if now_s is None else now_s >= self.thr
        ev = best_sentence(then_chunk, stmt)[0] if then_chunk else ""
        if then_ok is False:
            cls = "never_supported"
        elif pg["group"] == "unverifiable":
            cls = "unverifiable"
        elif pg["group"] == "lost":
            cls = "link_lost"
        elif now_ok:
            cls = "still_supported"
        elif then_ok is None or not ev:
            cls = "uncertain"  # no "then" page (or passage) to compare with
        else:
            # both signals: supported then, not now, AND the passage that supported it then is gone
            still_there = fuzz.partial_ratio(ev.lower(), (pg["now_dom"] or "").lower()) >= 90
            cls = "still_supported" if still_there else "content_changed"
        item = {"statement": stmt, "citation": i + 1, "url": u, "link_state": pg["state"],
                "snapshot": pg["snapshot"], "archive": pg["archive"], "score_then": then_s, "score_now": now_s,
                "class": cls, "excerpt_then": ev, "browser_rechecked": pg["browser_rechecked"],
                "excerpt_now": best_sentence(now_chunk, stmt)[0] if now_chunk else ""}
        if explain and self.explainer and cls in ("content_changed", "uncertain", "never_supported"):
            passages = [c for c in (now_chunk if cls != "never_supported" else then_chunk,) if c]
            if passages:
                item["explanation"] = self.explainer.verify(stmt, passages)["reason"]
        return item

    def check_iter(self, answer, urls, cited_at=None, explain=False, then_texts=None, browser=None):
        """Yield events as work completes: {"type": "plan"}, then per URL {"type": "page"} followed by
        {"type": "item"} for every statement citing it, and finally {"type": "done"}."""
        t0 = time.time()
        then_texts = then_texts or {}
        pairs = [(k, stmt, i) for k, (stmt, refs) in enumerate(split_answer(answer, len(urls))) for i in refs]
        uniq = list(dict.fromkeys(urls))
        yield {"type": "plan", "n_urls": len(uniq), "n_pairs": len(pairs)}
        for n, u in enumerate(uniq, 1):
            pg = self.page(u, cited_at, then_texts.get(u), browser)
            yield {"type": "page", "i": n, "url": u, "link_state": pg["state"], "archive": pg["archive"],
                   "browser_rechecked": pg["browser_rechecked"]}
            for k, stmt, i in pairs:
                if urls[i] == u:
                    item = self.judge_pair(stmt, i, u, pg, explain)
                    item["order"] = [k, i]
                    yield {"type": "item", "item": item}
        yield {"type": "done", "seconds": time.time() - t0, "threshold": self.thr}

    def check(self, answer, urls, cited_at=None, explain=False, then_texts=None, browser=None):
        """then_texts: optional {url: text of the page as cited} (e.g. the text saved with a dataset);
        it replaces the archive lookup for those URLs."""
        items, done = [], {}
        for ev in self.check_iter(answer, urls, cited_at, explain, then_texts, browser):
            if ev["type"] == "item":
                items.append(ev["item"])
            elif ev["type"] == "done":
                done = ev
        items.sort(key=lambda x: x.pop("order"))
        return {"items": items, "seconds": done.get("seconds"), "threshold": self.thr}
