"""Build app/static/replays.json: recorded checks and highlighted cases for the public (static) explorer.

A replay is one AI search answer of Liu et al. (2023) with every statement-citation pair and the outcome the October
2026 re-check gave it, taken from explorer.json. The static explorer plays it back in check mode, page by page,
so that visitors without a GPU can see what a check returns. Cases are single pairs shown on top of the explorer.

Usage: .venv/bin/python -I src/export_replays.py <explorer_json> <out_json>
"""
import json, os, sys

# (engine, query) of the answers to replay, in menu order
REPLAYS = [
    ("bing_chat", "who is the top ranked female tennis player in the world"),
    ("perplexity", "who is the most paid player in the nba"),
    ("neeva", "difference between stand up india and startup india"),
    ("bing_chat", "what are the effects of a dog bite"),
    ("neeva", "how to get the u with two dots above it"),
]
# (pair id, headline): one content change, one changed figure, one link a link checker reports as live
CASES = [
    ("dev-880", "American Idol: the finalist count the answer quotes is gone from the page"),
    ("dev-1067", "New Jersey colleges: “66 institutions (2014)” became “96 (2026)”"),
    ("test-311", "U.S. foreign aid dashboard: a link checker says live, but the page now redirects elsewhere"),
]
CITED_AT = "2023-03-15"  # Liu et al. collected the answers in early 2023


def main():
    exp_p, out_p = sys.argv[1:3]
    d = json.load(open(exp_p))
    by_id = {it["id"]: it for it in d["items"]}
    order = lambda it: (it["id"].split("-")[0], int(it["id"].split("-")[1]))
    replays = []
    for eng, q in REPLAYS:
        its = sorted((it for it in d["items"] if it["e"] == eng and it["q"].lower().startswith(q)), key=order)
        assert its, (eng, q)
        urls = list(dict.fromkeys(it["u"] for it in its))
        stmts = list(dict.fromkeys(it["s"] for it in its))
        marks = {s: sorted({urls.index(it["u"]) + 1 for it in its if it["s"] == s}) for s in stmts}
        answer = " ".join(s + " " + " ".join(f"[{m}]" for m in marks[s]) for s in stmts)
        pairs = [{"order": [stmts.index(it["s"]), urls.index(it["u"])], "statement": it["s"],
                  "citation": urls.index(it["u"]) + 1, "url": it["u"], "class": it["c"], "link_state": it["ls"],
                  "score_then": it["p23"], "score_now": it["pn"], "excerpt_then": it["ev23"], "excerpt_now": it["evn"],
                  "archive": "provided"} for it in its]
        replays.append({"engine": eng, "query": its[0]["q"], "answer": answer, "urls": urls, "cited_at": CITED_AT,
                        "pairs": pairs})
    cases = []
    for pid, title in CASES:
        it = by_id[pid]
        cases.append({"id": pid, "title": title, "class": it["c"], "statement": it["s"]})
    json.dump({"replays": replays, "cases": cases}, open(out_p, "w"), separators=(",", ":"))
    print(len(replays), sum(len(r["pairs"]) for r in replays), len(cases), os.path.getsize(out_p))


if __name__ == "__main__":
    main()
