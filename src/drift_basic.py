"""Link-state classification and evidence survival for re-fetched cited pages.

For each statement-citation pair in the Liu et al. (2023) verifiability
judgments (dev+test by default), joins the 2026 live fetch, extracts the
current page text with trafilatura, classifies the link state, and checks
whether the annotator's 2023 evidence still appears in the current text
(exact after normalisation, or fuzzy partial match).

Usage: .venv/bin/python -I src/drift_basic.py <judgments_dir> <live_dir> <out_jsonl> [splits...]
"""
import gzip, json, os, re, sys, unicodedata, urllib.parse

import trafilatura
from rapidfuzz import fuzz

FUZZY_OK = 90  # partial_ratio threshold for "evidence still present"
SOFT404 = re.compile(r"\b(page not found|404|no longer available|doesn.t exist|does not exist|"
                     r"has been removed|cannot be found|could not be found)\b", re.I)


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[‘’“”]", "'", s)
    return re.sub(r"\s+", " ", s).strip()


def same_doc(orig, final):
    a, b = urllib.parse.urlsplit(orig), urllib.parse.urlsplit(final)
    strip = lambda h: h.lower().removeprefix("www.")
    return strip(a.netloc) == strip(b.netloc) and a.path.rstrip("/") == b.path.rstrip("/")


def link_state(rec, text):
    if rec is None:
        return "not_fetched"
    o = rec.get("outcome")
    if o == "robots_disallowed":
        return "robots_disallowed"
    if o != "http":
        return "unreachable"  # DNS/TCP/TLS/timeout
    st = rec.get("status", 0)
    if st in (401, 402, 403, 429, 451):
        return "blocked_or_paywalled"
    if st >= 400:
        return "dead_http"
    final = rec.get("final_url") or rec["url"]
    if not same_doc(rec["url"], final):
        path = urllib.parse.urlsplit(final).path.strip("/")
        if not path:
            return "redirect_home"
        if urllib.parse.urlsplit(rec["url"]).netloc.lower().removeprefix("www.") != \
                urllib.parse.urlsplit(final).netloc.lower().removeprefix("www."):
            return "redirect_other_site"
        return "redirect_other_page"
    if not text or len(text) < 200 or (len(text) < 2000 and SOFT404.search(text[:500])):
        return "soft404_or_empty"
    return "alive"


def evidence_survival(evidence, text):
    if not evidence:
        return None, None
    sents = [norm(x) for x in evidence.split("\n") if len(norm(x)) >= 20]
    if not sents:
        return None, None
    t = norm(text)
    exact = sum(s in t for s in sents) / len(sents)
    fuzzy = sum(fuzz.partial_ratio(s, t) >= FUZZY_OK for s in sents) / len(sents) if t else 0.0
    return exact, fuzzy


def main():
    jdir, live_dir, out_path = sys.argv[1:4]
    splits = sys.argv[4:] or ["dev", "test"]
    fetched = {}
    with open(os.path.join(live_dir, "fetch_log.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            fetched[r["url"]] = r
    text_cache = {}
    with open(out_path, "w") as out:
        for sp in splits:
            with gzip.open(os.path.join(jdir, f"verifiability_judgments_{sp}.jsonl.gz"), "rt") as f:
                for i, line in enumerate(f):
                    j = json.loads(line)
                    url = j["source_url"]
                    rec = fetched.get(url)
                    if url not in text_cache:
                        text = ""
                        if rec and rec.get("file"):
                            with gzip.open(os.path.join(live_dir, "html", rec["file"]), "rt",
                                           errors="replace") as h:
                                text = trafilatura.extract(h.read(), favor_recall=True) or ""
                        text_cache[url] = text
                    text = text_cache[url]
                    state = link_state(rec, text)
                    ex, fz = evidence_survival(j.get("source_localized_evidence"), text) \
                        if state == "alive" else (None, None)
                    ex23, fz23 = evidence_survival(j.get("source_localized_evidence"), j["source_raw_text"])
                    out.write(json.dumps({
                        "split": sp, "idx": i, "url": url, "label_2023": j["source_supports_statement"],
                        "link_state": state, "status": rec.get("status") if rec else None,
                        "final_url": rec.get("final_url") if rec else None,
                        "len_text_2023": len(j["source_raw_text"]), "len_text_now": len(text),
                        "evid_exact_2023": ex23, "evid_fuzzy_2023": fz23,
                        "evid_exact_now": ex, "evid_fuzzy_now": fz,
                    }) + "\n")


if __name__ == "__main__":
    main()
