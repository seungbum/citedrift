"""E4: does the interactive check mode reproduce the batch measurement?

Runs the live pipeline (citedrift.pipeline.Checker: plain fetch, no browser re-check) on N
test answers (seed 0, at least two citations) with the 2023 page text of the Liu et al.
data as the "then" page, and matches its statement-citation outcomes to E2 tool-mode
outcomes (same then-text, judge and rule, but the calibrated batch link states).
Pairs are matched on (normalised statement, URL).

Usage: REQUESTS_CA_BUNDLE=... .venv/bin/python -I src/e4_checkmode.py <liu_dir> <pairs_jsonl> <drift_jsonl> <out_json> [N]
"""
import collections, gzip, json, os, random, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift.judge import MiniCheckFT5  # noqa: E402
from citedrift.pipeline import Checker  # noqa: E402


def norm(s):
    return re.sub(r"\W+", "", (s or "").lower())


def main():
    liu, pairs_p, drift_p, out_p = sys.argv[1:5]
    n = int(sys.argv[5]) if len(sys.argv) > 5 else 60
    P = {(r["split"], r["idx"]): r for r in map(json.loads, open(pairs_p))}
    D = {(r["split"], r["idx"]): r for r in map(json.loads, open(drift_p))}
    e2 = {(norm(P[k]["statement"]), P[k]["url"]): D[k] for k in P if k[0] == "test"}
    then = {}
    with gzip.open(os.path.join(liu, "verifiability_judgments", "verifiability_judgments_test.jsonl.gz"), "rt") as f:
        for line in f:
            j = json.loads(line)
            if len(j["source_raw_text"]) > len(then.get(j["source_url"], "")):
                then[j["source_url"]] = j["source_raw_text"]
    test_q = {P[k]["query"].strip().lower() for k in P if k[0] == "test"}
    answers = [h for h in map(json.loads, open(os.path.join(liu, "human_evaluation_annotations.jsonl")))
               if h["query"].strip().lower() in test_q and len({c["link_target"] for c in h["citations"]}) >= 2]
    random.Random(0).shuffle(answers)
    answers = answers[:n]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    params = json.load(open(os.path.join(root, "results", "judge_combo_params.json")))
    thr = json.load(open(os.path.join(root, "results", "e1_eval_combo.json")))["complete"]["threshold_dev"]
    checker = Checker(MiniCheckFT5(token_budget=4096), params, thr)
    matched, unmatched, secs = [], 0, []
    for h in answers:
        urls = []
        for c in sorted(h["citations"], key=lambda c: int(c["text"].strip("[]"))):
            if c["link_target"] not in urls:
                urls.append(c["link_target"])
        marks = {c["text"]: urls.index(c["link_target"]) + 1 for c in h["citations"]}
        ans = h["response"]
        for old, new in sorted(marks.items(), key=lambda x: -len(x[0])):
            ans = ans.replace(old, f"[#{new}]")
        ans = re.sub(r"\](?=[A-Za-z])", "] ", ans.replace("[#", "["))
        t0 = time.time()
        out = checker.check(ans, urls, then_texts={u: then[u] for u in urls if u in then})
        secs.append(time.time() - t0)
        for it in out["items"]:
            d = e2.get((norm(it["statement"]), it["url"]))
            if d is None:
                unmatched += 1
                continue
            matched.append({"check": it["class"], "e2_tool": d["class_tool"], "e2_human": d["class_human"],
                            "check_link": it["link_state"], "e2_link": d["link_state"]})
        print(h["id"][-20:], round(secs[-1], 1), flush=True)
    agree = sum(m["check"] == m["e2_tool"] for m in matched)
    link_agree = sum(m["check_link"] == m["e2_link"] for m in matched)
    res = {"n_answers": len(answers), "n_matched_pairs": len(matched), "n_unmatched": unmatched,
           "outcome_agreement": agree, "link_state_agreement": link_agree,
           "confusion": collections.Counter(f'{m["e2_tool"]}->{m["check"]}' for m in matched),
           "link_confusion": collections.Counter(f'{m["e2_link"]}->{m["check_link"]}' for m in matched
                                                 if m["e2_link"] != m["check_link"]),
           "median_seconds": sorted(secs)[len(secs) // 2]}
    json.dump(res, open(out_p, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
