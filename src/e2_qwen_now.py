"""E2 second opinion: Qwen2.5-7B (4-bit) on today's page for every candidate content change.

Candidates: complete_support pairs on reachable pages that the combined judge
does not support today (main or DOM text). For each, MiniCheck re-scores the
current main text to select the top-3 chunks, and Qwen gives a verdict.

Usage: .venv/bin/python -I src/e2_qwen_now.py <pairs> <drift_jsonl> <url_features> <out_jsonl>
"""
import gzip, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift.explain import QwenVerifier  # noqa: E402
from citedrift.judge import MiniCheckFT5  # noqa: E402

CACHE = "data/cache/now_text"


def main():
    pairs_p, drift_p, feat_p, out_p = sys.argv[1:5]
    P = {(r["split"], r["idx"]): r for r in map(json.loads, open(pairs_p))}
    key = {r["url"]: r["key"] for r in map(json.loads, open(feat_p))}
    cands = []
    for r in map(json.loads, open(drift_p)):
        if r["label_2023"] != "complete_support" or r["link_group"] != "reachable":
            continue
        cands.append(r)
    mc, q = MiniCheckFT5(token_budget=4096), QwenVerifier()
    done = set()
    if os.path.exists(out_p):
        done = {(r["split"], r["idx"]) for r in map(json.loads, open(out_p))}
    with open(out_p, "a") as out:
        for r in cands:
            k = (r["split"], r["idx"])
            if k in done:
                continue
            with gzip.open(os.path.join(CACHE, key[r["url"]] + ".json.gz"), "rt") as f:
                d = json.load(f)
            text = d["main_text"] if len(d.get("main_text") or "") >= 50 else d.get("dom_text", "")
            s = mc.score(text, P[k]["statement"])
            top = sorted(range(s["n_chunks"]), key=lambda i: -s["chunk_probs"][i])[:3]
            v = q.verify(P[k]["statement"], [s["chunks"][i] for i in sorted(top)])
            out.write(json.dumps({"split": k[0], "idx": k[1], "verdict": v["verdict"], "reason": v["reason"],
                                  "seconds": v["seconds"]}) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
