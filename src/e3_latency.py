"""E3: end-to-end cost of checking whole answers on one RTX 5070 (12 GB).

Samples N test-split answers (seed 0) with at least two citations from the
Liu et al. human-evaluation file (which keeps the [n] markers), runs the full
local pipeline (fetch, archived "then" page closest to 2023-03-15, extraction,
judging) and records wall-clock time per answer and per stage, plus peak GPU
memory. Optionally times the Qwen explanation step.

Usage: REQUESTS_CA_BUNDLE=... .venv/bin/python -I src/e3_latency.py <liu_dir> <pairs_jsonl> <out_json> [N] [--explain]
"""
import json, os, random, sys, time

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift import pipeline  # noqa: E402
from citedrift.judge import MiniCheckFT5  # noqa: E402
from citedrift.pipeline import Checker  # noqa: E402

CITED_AT = "20230315"


def main():
    liu, pairs_p, out_p = sys.argv[1:4]
    n = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4].isdigit() else 20
    explain = "--explain" in sys.argv
    test_q = {json.loads(l)["query"].strip().lower() for l in open(pairs_p) if json.loads(l)["split"] == "test"}
    answers = [h for h in map(json.loads, open(os.path.join(liu, "human_evaluation_annotations.jsonl")))
               if h["query"].strip().lower() in test_q and len({c["link_target"] for c in h["citations"]}) >= 2]
    random.Random(0).shuffle(answers)
    answers = answers[:n]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    params = json.load(open(os.path.join(root, "results", "judge_combo_params.json")))
    thr = json.load(open(os.path.join(root, "results", "e1_eval_combo.json")))["complete"]["threshold_dev"]
    ex = None
    if explain:
        from citedrift.explain import QwenVerifier
        ex = QwenVerifier()
    checker = Checker(MiniCheckFT5(token_budget=4096), params, thr, ex)
    torch.cuda.reset_peak_memory_stats()

    # time the stages by wrapping the module functions
    stage = {"fetch": 0.0, "archive": 0.0}

    def timed(name, fn):
        def w(*a, **k):
            t = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                stage[name] += time.perf_counter() - t
        return w
    pipeline.fetch = timed("fetch", pipeline.fetch)
    pipeline.wayback = timed("archive", pipeline.wayback)

    runs = []
    for h in answers:
        urls = []
        for c in sorted(h["citations"], key=lambda c: int(c["text"].strip("[]"))):
            if c["link_target"] not in urls:
                urls.append(c["link_target"])
        marks = {c["text"]: urls.index(c["link_target"]) + 1 for c in h["citations"]}
        answer = h["response"]
        for old, new in sorted(marks.items(), key=lambda x: -len(x[0])):  # renumber to unique-URL order
            answer = answer.replace(old, f"[#{new}]")
        answer = answer.replace("[#", "[")
        stage.update(fetch=0.0, archive=0.0)
        t0 = time.perf_counter()
        out = checker.check(answer, urls, CITED_AT, explain=explain)
        total = time.perf_counter() - t0
        runs.append({"id": h["id"], "system": h["system_name"], "n_urls": len(urls), "n_pairs": len(out["items"]),
                     "total_s": total, "fetch_s": stage["fetch"], "archive_s": stage["archive"],
                     "judge_and_rest_s": total - stage["fetch"] - stage["archive"],
                     "classes": [i["class"] for i in out["items"]],
                     "archive_status": [i["archive"] for i in out["items"]]})
        print(runs[-1]["id"], round(total, 1), flush=True)
    res = {"n_answers": len(runs), "explain": explain, "peak_gpu_gb": torch.cuda.max_memory_allocated() / 1e9,
           "gpu": torch.cuda.get_device_name(0), "runs": runs}
    json.dump(res, open(out_p, "w"), indent=1)


if __name__ == "__main__":
    main()
