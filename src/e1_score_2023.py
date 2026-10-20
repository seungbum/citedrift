"""E1: score every statement against its 2023 cited-page text with the local judge.

Writes one line per pair: support probability, best chunk index, number of
chunks and wall-clock seconds (the latter feed E3). Page text is read from the
original Liu et al. files and is not copied into the output.

Usage: .venv/bin/python -I src/e1_score_2023.py <liu_dir> <pairs_jsonl> <out_jsonl> [text_field]
  text_field: source_text (default, keeps line breaks) or source_raw_text
"""
import gzip, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift.judge import MiniCheckFT5  # noqa: E402


def main():
    liu, pairs_path, out_path = sys.argv[1:4]
    field = sys.argv[4] if len(sys.argv) > 4 else "source_text"
    texts = {}
    for sp in sorted({json.loads(l)["split"] for l in open(pairs_path)}):
        with gzip.open(os.path.join(liu, "verifiability_judgments",
                                    f"verifiability_judgments_{sp}.jsonl.gz"), "rt") as f:
            for i, line in enumerate(f):
                texts[(sp, i)] = json.loads(line)[field]
    pairs = [json.loads(l) for l in open(pairs_path)]
    done = set()
    if os.path.exists(out_path):
        done = {(r["split"], r["idx"]) for r in map(json.loads, open(out_path))}
    judge = MiniCheckFT5()
    with open(out_path, "a") as out:
        for n, p in enumerate(pairs, 1):
            k = (p["split"], p["idx"])
            if k in done:
                continue
            r = judge.score(texts[k], p["statement"])
            out.write(json.dumps({"split": k[0], "idx": k[1], "field": field, "prob": r["prob"],
                                  "best_chunk": r["best_chunk"], "n_chunks": r["n_chunks"],
                                  "chunk_probs": [round(x, 5) for x in r["chunk_probs"]],
                                  "seconds": r["seconds"], "n_chars": len(texts[k])}) + "\n")
            if n % 200 == 0:
                out.flush()
                print(n, flush=True)


if __name__ == "__main__":
    main()
