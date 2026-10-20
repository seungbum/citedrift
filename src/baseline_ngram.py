"""String-matching baseline: share of the statement's word 4-grams that occur in the page text.

This mirrors the quote/4-gram check used by link-verification tools (no
semantic judgment). Scores are written in the same format as the judge so that
e1_eval.py and the drift scripts can use them unchanged.

Usage: .venv/bin/python -I src/baseline_ngram.py <liu_dir> <pairs_jsonl> <out_jsonl> [now_features_jsonl]
  without the 4th argument the 2023 page text (source_raw_text) is used; with it, the cached current main text.
"""
import gzip, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift.textutil import norm  # noqa: E402

N = 4


def grams(t):
    w = re.findall(r"\w+", norm(t))
    return {" ".join(w[i:i + N]) for i in range(max(0, len(w) - N + 1))}


def ngram_score(statement, page):
    g = grams(statement)
    return len(g & grams(page)) / len(g) if g else 0.0


def main():
    liu, pairs_path, out_path = sys.argv[1:4]
    now = len(sys.argv) > 4
    texts = {}
    if now:
        feats = {r["url"]: r["key"] for r in map(json.loads, open(sys.argv[4]))}
    else:
        for sp in sorted({json.loads(l)["split"] for l in open(pairs_path)}):
            with gzip.open(os.path.join(liu, "verifiability_judgments",
                                        f"verifiability_judgments_{sp}.jsonl.gz"), "rt") as f:
                for i, line in enumerate(f):
                    texts[(sp, i)] = json.loads(line)["source_raw_text"]
    with open(out_path, "w") as out:
        for p in map(json.loads, open(pairs_path)):
            k = (p["split"], p["idx"])
            if now:
                with gzip.open(os.path.join("data/cache/now_text", feats[p["url"]] + ".json.gz"), "rt") as f:
                    page = json.load(f)["main_text"]
            else:
                page = texts[k]
            out.write(json.dumps({"split": k[0], "idx": k[1], "prob": ngram_score(p["statement"], page)}) + "\n")


if __name__ == "__main__":
    main()
