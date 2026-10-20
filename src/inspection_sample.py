"""Step 1(c): blinded spot check of the drift outcomes.

Draws a stratified random sample (seed 0) of complete_support pairs on
reachable pages: up to N_CHANGED "content_changed" and N_STILL
"still_supported", plus N_AWAY pairs on URLs whose redirect was ruled "away".
Writes one packet per item (statement, the annotator's 2023 evidence, the
current main text and, if different, the DOM text) in shuffled order, without
the tool's outcome or scores. The key (item -> pair, outcome) is written
separately. Packets contain page text and stay local (data/, not published).

Usage: .venv/bin/python -I src/inspection_sample.py <drift_jsonl> <pairs_jsonl> <url_features_jsonl> <out_dir>
          [--seed N] [--exclude previous_key.csv] [--demoted previous_drift_jsonl]
  --exclude    skip pairs already in an earlier sample
  --demoted    add a stratum of N_DEMOTED pairs that were content_changed in the earlier drift file
               but are not content_changed now (checks the rule change)
"""
import csv, gzip, json, os, random, sys

N_CHANGED, N_STILL, N_AWAY, N_DEMOTED, N_UNCERTAIN = 50, 30, 20, 20, 20


def opt(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


MAX_CHARS = 12000


def main():
    drift_p, pairs_p, feat_p, out = sys.argv[1:5]
    os.makedirs(os.path.join(out, "items"), exist_ok=True)
    pairs = {(r["split"], r["idx"]): r for r in map(json.loads, open(pairs_p))}
    feats = {r["url"]: r for r in map(json.loads, open(feat_p))}
    excl = set()
    if opt("--exclude"):
        excl = {(r["split"], int(r["idx"])) for r in csv.DictReader(open(opt("--exclude")))}
    rows = [r for r in map(json.loads, open(drift_p))
            if r["label_2023"] == "complete_support" and (r["split"], r["idx"]) not in excl]
    rng = random.Random(int(opt("--seed", 0)))
    strata = [("content_changed", N_CHANGED, lambda r: r["class_human"] == "content_changed"),
              ("still_supported", N_STILL, lambda r: r["class_human"] == "still_supported"),
              ("away", N_AWAY, lambda r: r["link_state"] == "away"),
              ("uncertain", N_UNCERTAIN, lambda r: r["class_human"] == "uncertain")]
    if opt("--demoted"):
        old = {(r["split"], r["idx"]) for r in map(json.loads, open(opt("--demoted")))
               if r["class_human"] == "content_changed"}
        strata[1] = ("still_supported", N_STILL, lambda r: r["class_human"] == "still_supported"
                     and (r["split"], r["idx"]) not in old)
        strata.append(("demoted", N_DEMOTED, lambda r: (r["split"], r["idx"]) in old
                       and r["class_human"] != "content_changed"))
    pick = []
    for cls, n, cond in strata:
        pool = [r for r in rows if cond(r)]
        pick += [(cls, r) for r in rng.sample(pool, min(n, len(pool)))]
    rng.shuffle(pick)
    with open(os.path.join(out, "key.csv"), "w", newline="") as kf:
        kw = csv.writer(kf)
        kw.writerow(["item", "split", "idx", "stratum", "class_human", "link_state", "url"])
        for i, (stratum, r) in enumerate(pick, 1):
            p = pairs[(r["split"], r["idx"])]
            f = feats[r["url"]]
            with gzip.open(os.path.join("data/cache/now_text", f["key"] + ".json.gz"), "rt") as h:
                d = json.load(h)
            final = f["browser_final_url"] or f["http_final_url"] or r["url"]
            txt = [f"ITEM {i}", "", "STATEMENT (from an AI search answer, 2023):", p["statement"], "",
                   "CITED URL (2023): " + r["url"], "URL REACHED NOW (2026): " + final, "",
                   "EVIDENCE an annotator copied from the cited page in 2023:", p.get("evidence_2023") or "(none)", "",
                   "CURRENT PAGE TITLE: " + (d.get("title") or ""), "",
                   "CURRENT PAGE, MAIN TEXT (extracted, may be truncated):", (d.get("main_text") or "")[:MAX_CHARS]]
            dom = d.get("dom_text") or ""
            if len(dom) > len(d.get("main_text") or "") + 500:
                txt += ["", "CURRENT PAGE, ALL VISIBLE TEXT (may be truncated):", dom[:MAX_CHARS]]
            with open(os.path.join(out, "items", f"{i:03d}.txt"), "w") as fo:
                fo.write("\n".join(txt) + "\n")
            kw.writerow([i, r["split"], r["idx"], stratum, r["class_human"], r["link_state"], r["url"]])
    print(len(pick))


if __name__ == "__main__":
    main()
