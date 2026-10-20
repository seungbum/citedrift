"""Text normalisation, page-text extraction and overlap measures."""
import re, unicodedata

import lxml.html
import trafilatura
from rapidfuzz import fuzz

FUZZY_OK = 90  # rapidfuzz partial_ratio for "evidence sentence still present"
SHINGLE = 5


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[‘’“”]", "'", s)
    return re.sub(r"\s+", " ", s).strip()


def main_text(html):
    """Main-content text (what the judge reads)."""
    if not html:
        return ""
    return trafilatura.extract(html, favor_recall=True) or ""


def dom_text(html):
    """All visible-ish text in the DOM (no script/style), for extraction-loss checks."""
    if not html:
        return ""
    try:
        root = lxml.html.fromstring(html)
    except Exception:
        return ""
    for bad in root.xpath("//script|//style|//noscript|//template|//svg"):
        bad.drop_tree()
    return re.sub(r"\s+", " ", root.text_content() or "").strip()


def html_title(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def shingles(text, k=SHINGLE):
    w = re.findall(r"\w+", norm(text))
    return {" ".join(w[i:i + k]) for i in range(max(0, len(w) - k + 1))}


def containment(old, new):
    """Share of the old text's word 5-grams that still occur in the new text."""
    a = shingles(old)
    if not a:
        return None
    return len(a & shingles(new)) / len(a)


def evidence_sentences(evidence):
    return [s for s in (norm(x) for x in (evidence or "").split("\n")) if len(s) >= 20]


def evidence_survival(evidence, text):
    """(exact share, fuzzy share) of evidence sentences found in text; (None, None) if no evidence."""
    sents = evidence_sentences(evidence)
    if not sents:
        return None, None
    t = norm(text)
    if not t:
        return 0.0, 0.0
    exact = sum(s in t for s in sents) / len(sents)
    fuzzy = sum(fuzz.partial_ratio(s, t) >= FUZZY_OK for s in sents) / len(sents)
    return exact, fuzzy
