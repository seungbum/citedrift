"""E1 (second stage): Qwen2.5-7B-Instruct 4-bit on the top-k MiniCheck chunks of the 2023 text.

Chunks are recomputed deterministically (citedrift.judge.chunk_document) and
ranked by the per-chunk MiniCheck probabilities stored by e1_score_2023.py.

Usage: .venv/bin/python -I src/e1_qwen.py <liu_dir> <pairs_jsonl> <minicheck_scores_with_chunks> <out_jsonl> [field] [k]
"""
import gzip, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift.explain import QwenVerifier  # noqa: E402
from citedrift.judge import chunk_document  # noqa: E402


def main():
    liu, pairs_p, mc_p, out_p = sys.argv[1:5]
    field = sys.argv[5] if len(sys.argv) > 5 else "source_raw_text"
    k = int(sys.argv[6]) if len(sys.argv) > 6 else 3
    texts = {}
    for sp in ("dev", "test"):
        with gzip.open(os.path.join(liu, "verifiability_judgments",
                                    f"verifiability_judgments_{sp}.jsonl.gz"), "rt") as f:
            for i, line in enumerate(f):
                texts[(sp, i)] = json.loads(line)[field]
    mc = {(r["split"], r["idx"]): r for r in map(json.loads, open(mc_p))}
    done = set()
    if os.path.exists(out_p):
        done = {(r["split"], r["idx"]) for r in map(json.loads, open(out_p))}
    q = QwenVerifier()
    with open(out_p, "a") as out:
        for n, p in enumerate(map(json.loads, open(pairs_p)), 1):
            key = (p["split"], p["idx"])
            if key in done:
                continue
            chunks = chunk_document(texts[key])
            probs = mc[key]["chunk_probs"]
            assert len(probs) == len(chunks), key
            top = sorted(range(len(chunks)), key=lambda i: -probs[i])[:k]
            r = q.verify(p["statement"], [chunks[i] for i in sorted(top)])
            out.write(json.dumps({"split": key[0], "idx": key[1], "verdict": r["verdict"],
                                  "reason": r["reason"], "n_input_tokens": r["n_input_tokens"],
                                  "seconds": r["seconds"]}) + "\n")
            out.flush()
            if n % 100 == 0:
                print(n, flush=True)


if __name__ == "__main__":
    main()
