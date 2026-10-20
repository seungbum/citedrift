"""E2: score every statement against the current (2026) page with the local judge.

Reads the cached current texts written by url_features.py. Two views of the
current page are scored: the main-content text (same extractor family as the
2023 text) and the full DOM text (robustness check for extraction misses).
Pairs whose URL has no current text get no line.

Usage: .venv/bin/python -I src/e2_score_now.py <pairs_jsonl> <url_features_jsonl> <out_jsonl> [--complete-only] [--lazy-dom] [--exclude-urls FILE | --only-urls FILE]
  --complete-only  score only pairs labelled complete_support in 2023 (the population of the human-mode outcome)
  --exclude-urls / --only-urls  skip / keep pairs whose URL is listed (to score pages whose text is final first)
  --lazy-dom       score the DOM view only if the combined score on the main text is below the dev threshold;
                   the outcome uses the higher of the two scores, so this changes no outcome (used for the train split)
"""
import gzip, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift.judge import MiniCheckFT5  # noqa: E402

CACHE = "data/cache/now_text"


def main():
    pairs_path, feat_path, out_path = sys.argv[1:4]
    key = {r["url"]: r["key"] for r in map(json.loads, open(feat_path))}
    complete_only, lazy = "--complete-only" in sys.argv, "--lazy-dom" in sys.argv
    opt = lambda f: {l.strip() for l in open(sys.argv[sys.argv.index(f) + 1]) if l.strip()} if f in sys.argv else None
    excl, only = opt("--exclude-urls"), opt("--only-urls")
    if lazy:
        from baseline_ngram import ngram_score
        from e1_combo import combine
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        params = json.load(open(os.path.join(root, "results", "judge_combo_params.json")))
        thr = json.load(open(os.path.join(root, "results", "e1_eval_combo.json")))["complete"]["threshold_dev"]
    judge = MiniCheckFT5()
    text_cache = {}
    with open(out_path, "w") as out:
        for n, p in enumerate(map(json.loads, open(pairs_path)), 1):
            if complete_only and p["label_2023"] != "complete_support":
                continue
            u = p["url"]
            if (excl is not None and u in excl) or (only is not None and u not in only):
                continue
            if u not in text_cache:
                with gzip.open(os.path.join(CACHE, key[u] + ".json.gz"), "rt") as f:
                    d = json.load(f)
                text_cache = {u: d}  # pairs are grouped by query, so a one-entry cache suffices
            d = text_cache[u]
            rec = {"split": p["split"], "idx": p["idx"]}
            for view in ("main_text", "dom_text"):
                t = d.get(view) or ""
                if len(t) < 50:
                    continue
                if lazy and view == "dom_text" and "main_text" in rec and \
                        combine(params, rec["main_text"]["prob"], ngram_score(p["statement"], d["main_text"])) >= thr:
                    continue
                r = judge.score(t, p["statement"])
                rec[view] = {"prob": r["prob"], "best_chunk": r["best_chunk"], "n_chunks": r["n_chunks"],
                             "seconds": r["seconds"]}
            if len(rec) > 2:
                out.write(json.dumps(rec) + "\n")
            if n % 200 == 0:
                out.flush()
                print(n, flush=True)


if __name__ == "__main__":
    main()
