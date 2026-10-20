"""Unit tests for the rules that decide CiteDrift's outcomes (no network, no GPU)."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pytest  # noqa: E402

from citedrift.judge import chunk_document  # noqa: E402
from citedrift.linkstate import GROUP, classify, same_doc  # noqa: E402
from citedrift.pipeline import Checker, best_sentence, split_answer  # noqa: E402
from citedrift.textutil import containment, evidence_survival, norm  # noqa: E402
from e1_combo import combine  # noqa: E402


# ---------- answer splitting ----------
def test_split_marker_inside_sentence():
    assert split_answer("A is B [1]. C is D [2].", 2) == [("A is B.", [0]), ("C is D.", [1])]


def test_split_marker_after_period_goes_to_previous_sentence():
    out = split_answer("It is tall.[1] According to X, it grows.[2]", 2)
    assert out == [("It is tall.", [0]), ("According to X, it grows.", [1])]


def test_split_no_abbreviation_before_number():
    out = split_answer("She holds the No. 1 position [1]. Next [1].", 1)
    assert out[0][0] == "She holds the No. 1 position."


def test_split_multiple_refs_and_bold():
    assert split_answer("**Iga** is first [1] [2].", 2) == [("Iga is first.", [0, 1])]


def test_split_ignores_out_of_range_and_uncited():
    assert split_answer("Uncited sentence. Cited one [3].", 2) == []


# ---------- link state ----------
def base(**kw):
    f = {"url": "https://a.com/x", "http_outcome": "http", "http_status": 200, "http_final_url": "https://a.com/x",
         "network_filtered_http": False, "browser_outcome": None, "browser_status": None, "browser_final_url": None,
         "browser_challenge": None, "browser_error": None, "len_main_now": 5000, "containment_dom": None,
         "title_sim": None, "title_now": "Page"}
    f.update(kw)
    return f


@pytest.mark.parametrize("kw,expected", [
    ({}, "ok"),
    ({"http_outcome": "robots_disallowed"}, "skipped"),
    ({"network_filtered_http": True}, "filtered"),
    ({"http_status": 404}, "dead"),
    ({"http_status": 410}, "dead"),
    ({"http_status": 403}, "blocked"),
    ({"http_status": 503}, "transient"),
    ({"http_outcome": "timeout"}, "transient"),
    ({"http_outcome": "ssl_error"}, "transient"),
    ({"http_outcome": "connection_error"}, "dead"),
    ({"len_main_now": 50}, "empty"),
    ({"len_main_now": 900, "title_now": "Page not found"}, "soft404"),
    ({"http_final_url": "https://a.com/new", "containment_dom": 0.8}, "moved"),
    ({"http_final_url": "https://a.com/new", "containment_dom": 0.1, "title_sim": 95}, "moved"),
    ({"http_final_url": "https://a.com/", "containment_dom": 0.0, "title_sim": 20}, "away"),
    ({"http_status": 403, "browser_outcome": "browser", "browser_status": 200, "browser_final_url": "https://a.com/x",
      "browser_challenge": False}, "ok"),
    ({"http_status": 403, "browser_outcome": "browser", "browser_challenge": True}, "blocked"),
    ({"browser_outcome": "browser_error", "browser_error": "net::ERR_NAME_NOT_RESOLVED"}, "dead"),
    ({"http_status": 202, "browser_outcome": "browser", "browser_status": 200, "browser_final_url": "https://a.com/x",
      "browser_challenge": False, "browser_statuses": [202, 200]}, "blocked"),
    ({"http_status": 403, "browser_outcome": "browser", "browser_status": 200, "browser_final_url": "https://a.com/x",
      "browser_challenge": False, "browser_statuses": [301, 200]}, "ok"),
    ({"browser_outcome": "browser_error", "browser_error": "Timeout 30000ms"}, "transient"),
])
def test_classify(kw, expected):
    assert classify(base(**kw)) == expected


def test_classify_bot_wall_text_on_200():
    assert classify(base(len_main_now=300), "JavaScript is disabled. Verify that you're not a robot") == "blocked"


def test_groups_cover_all_states():
    for s in ("ok", "moved", "dead", "soft404", "away", "blocked", "filtered", "skipped", "transient", "empty"):
        assert GROUP[s] in ("reachable", "lost", "unverifiable")


def test_same_doc_ignores_www_and_trailing_slash():
    assert same_doc("https://www.a.com/x/", "https://a.com/x")
    assert not same_doc("https://a.com/x", "https://a.com/y")


# ---------- text overlap ----------
def test_norm_quotes_and_space():
    assert norm("It’s  “A”\n") == "it's 'a'"


def test_containment():
    old = "the quick brown fox jumps over the lazy dog today"
    assert containment(old, old) == 1.0
    assert containment(old, "something else entirely here and there now") == 0.0
    assert containment("", "x") is None


def test_evidence_survival_exact_fuzzy_none():
    ev = "Silicon melts at 1414 degrees Celsius in normal conditions."
    assert evidence_survival(ev, "Intro. " + ev + " More.") == (1.0, 1.0)
    assert evidence_survival(ev, "Nothing related to the element at all is said here.") == (0.0, 0.0)
    assert evidence_survival(None, "x") == (None, None)


def test_best_sentence_picks_closest():
    s, score = best_sentence("Cats sleep a lot. Iga Swiatek is world number one in tennis.", "Iga Swiatek is No. 1")
    assert s.startswith("Iga Swiatek") and score > 50


# ---------- judge chunking and combination ----------
def test_chunk_document_word_budget():
    doc = " ".join(f"Sentence number {i} has exactly seven words." for i in range(400))
    chunks = chunk_document(doc)
    assert len(chunks) >= 5 and all(len(c.split()) <= 500 for c in chunks)
    assert chunk_document("") == [""]


def test_combine_monotonic():
    p = {"intercept": 0.0, "w_minicheck_logit": 0.4, "w_ngram": 3.0}
    assert combine(p, 0.9, 0.5) > combine(p, 0.5, 0.5) > combine(p, 0.5, 0.0)


# ---------- outcome rule (stub judge) ----------
class Stub(Checker):
    def __init__(self, scores):
        self.thr, self.explainer, self.scores = 0.75, None, scores

    def support(self, text, claim):
        if not text:
            return None, None
        return self.scores[text], text


def page(group="reachable", then="T", now="N", dom="", state="ok"):
    return {"state": state, "group": group, "now_main": now, "now_dom": dom, "then_text": then, "snapshot": None,
            "archive": "provided", "browser_rechecked": False}


STMT = "The tower is 300 metres tall."


def test_outcome_never_supported():
    c = Stub({"T": 0.2, "N": 0.9})
    assert c.judge_pair(STMT, 0, "u", page())["class"] == "never_supported"


def test_outcome_link_lost_and_unverifiable():
    c = Stub({"T": 0.9})
    assert c.judge_pair(STMT, 0, "u", page(group="lost", state="dead"))["class"] == "link_lost"
    assert c.judge_pair(STMT, 0, "u", page(group="unverifiable", state="blocked"))["class"] == "unverifiable"


def test_outcome_still_supported():
    c = Stub({"T": 0.9, "N": 0.9})
    assert c.judge_pair(STMT, 0, "u", page())["class"] == "still_supported"


def test_outcome_content_changed_needs_passage_gone():
    then = "The tower is 300 metres tall and was built in 1889."
    gone = Stub({then: 0.9, "N": 0.2, "The tower is now 330 metres tall.": 0.2})
    pg = page(then=then, now="N", dom="The tower is now 330 metres tall.")
    assert gone.judge_pair(STMT, 0, "u", pg)["class"] == "content_changed"
    kept = Stub({then: 0.9, "N": 0.2, then: 0.9})
    pg2 = page(then=then, now="N", dom="Intro. " + then)
    kept.scores[pg2["now_dom"]] = 0.2
    assert kept.judge_pair(STMT, 0, "u", pg2)["class"] == "still_supported"


def test_outcome_uncertain_without_then_page():
    c = Stub({"N": 0.2})
    assert c.judge_pair(STMT, 0, "u", page(then=""))["class"] == "uncertain"
