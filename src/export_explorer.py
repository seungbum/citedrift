"""Build app/static/explorer.json for the public explorer.

Contains per pair: engine, query, statement, URL, 2023 human label, the
annotator's 2023 evidence (released with Liu et al. 2023 under MIT; cut to
400 characters), link state and drift class, judge scores, and the single
sentence of the current page closest to that evidence (at most 300
characters), and the verdict of the urlhealth link checker for the URL
(NOT_RUN when it was not run). No page bodies are included.

Usage: .venv/bin/python -I src/export_explorer.py <pairs> <drift_jsonl> <drift_summary> <url_features> \
          <liu_dir> <out_json> <urlhealth_jsonl>
"""
import gzip, json, os, re, sys

from nltk.tokenize import sent_tokenize
from rapidfuzz import fuzz, process

CACHE = "data/cache/now_text"
EV_CHARS, NOW_CHARS, MIN_SIM = 400, 300, 50


def sentences(text):
    out = []
    for block in re.split(r"\n+", text or ""):
        out.extend(s for s in sent_tokenize(block) if 20 <= len(s) <= 1200)
    return out


def main():
    pairs_p, drift_p, summ_p, feat_p, liu, out_p, uh_p = sys.argv[1:8]
    uh = {r["url"]: r["url_status"] for r in map(json.loads, open(uh_p))}
    pairs = {(r["split"], r["idx"]): r for r in map(json.loads, open(pairs_p))}
    key = {r["url"]: r["key"] for r in map(json.loads, open(feat_p))}
    summ = json.load(open(summ_p))
    sent_cache = {}
    items = []
    for d in map(json.loads, open(drift_p)):
        p = pairs[(d["split"], d["idx"])]
        ev = (p.get("evidence_2023") or "").strip()
        evn = ""
        if d["link_group"] == "reachable":
            if d["url"] not in sent_cache:
                with gzip.open(os.path.join(CACHE, key[d["url"]] + ".json.gz"), "rt") as f:
                    t = json.load(f)
                sent_cache.clear()
                sent_cache[d["url"]] = sentences(t.get("main_text", "")) + sentences(t.get("dom_text", ""))
            cands = sent_cache[d["url"]]
            target = ev.split("\n")[0] if ev else p["statement"]
            if cands:
                m = process.extractOne(target, cands, scorer=fuzz.token_set_ratio)
                if m and m[1] >= MIN_SIM:
                    evn = m[0][:NOW_CHARS]
        pn = [x for x in (d["score_now_main"], d["score_now_dom"]) if x is not None]
        items.append({"id": f'{d["split"]}-{d["idx"]}', "e": d["engine"], "q": p["query"], "s": p["statement"],
                      "u": d["url"], "l": d["label_2023"], "ev23": re.sub(r"\s+", " ", ev)[:EV_CHARS],
                      "ls": d["link_state"], "lg": d["link_group"], "c": d["class_human"],
                      "p23": round(d["score_2023"], 3), "pn": round(max(pn), 3) if pn else None, "evn": evn,
                      "uh": uh.get(d["url"], "NOT_RUN")})
    order = {"content_changed": 0, "link_lost": 1, "uncertain": 2, "still_supported": 3, "unverifiable": 4,
             "never_supported": 5}
    items.sort(key=lambda x: (order[x["c"]], x["id"]))
    h = summ["human"]
    out = {
        "meta": {"then_label": "2023", "now_label": "Oct 2026", "source": "Liu et al., EMNLP Findings 2023",
                 "threshold": summ["threshold"]},
        "summary": {"n_pairs": summ["n_pairs"], "n_urls": summ["n_urls"], "classes": h["classes"],
                    "checkable": h["checkable"], "lost_any": h["lost_any"], "lost_any_rate": h["lost_any_rate"],
                    "lost_any_ci": h["lost_any_ci"], "by_engine": h["by_engine"],
                    "uncertain": h["uncertain"], "lost_upper_rate": h["lost_upper_rate"]},
        "items": items,
        "example": json.load(open(os.path.join(os.path.dirname(out_p), "example.json"))),
        "about": open(os.path.join(os.path.dirname(out_p), "about.html")).read(),
        "footer": ("Data: verifiability judgments of Liu, Zhang &amp; Liang (2023), MIT licence. Current pages fetched "
                   "2026-10-15 from one network vantage point; page bodies are not redistributed. "
                   "Code: MIT. Judge: MiniCheck-Flan-T5-Large (MIT)."),
    }
    json.dump(out, open(out_p, "w"), separators=(",", ":"))
    print(len(items), os.path.getsize(out_p))


if __name__ == "__main__":
    main()
