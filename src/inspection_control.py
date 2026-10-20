"""Control for the spot check: the same pairs, but with the 2023 page text instead of today's page.

For every distinct pair of the validation sample, writes a packet in the same format
as inspection_sample.py, with the page text released with the Liu et al. data (2023)
in place of the current page (and no 'URL reached now'). The share of these pairs that
the agent labels not fully supported measures agent-vs-annotator disagreement without
any drift; drift estimates are reported as the excess over it. Order is reshuffled (seed 2).

Usage: .venv/bin/python -I src/inspection_control.py <key2_csv> <pairs_jsonl> <liu_dir> <out_dir>
"""
import csv, gzip, json, os, random, sys

MAX_CHARS = 12000


def main():
    key_p, pairs_p, liu, out = sys.argv[1:5]
    os.makedirs(os.path.join(out, "items"), exist_ok=True)
    P = {(r["split"], r["idx"]): r for r in map(json.loads, open(pairs_p))}
    J = {}
    for sp in ("dev", "test"):
        with gzip.open(os.path.join(liu, "verifiability_judgments", f"verifiability_judgments_{sp}.jsonl.gz"), "rt") as f:
            for i, line in enumerate(f):
                J[(sp, i)] = json.loads(line)
    seen, pick = set(), []
    for r in csv.DictReader(open(key_p)):
        k = (r["split"], int(r["idx"]))
        if k not in seen:
            seen.add(k)
            pick.append((k, r["stratum"]))
    random.Random(2).shuffle(pick)
    with open(os.path.join(out, "key.csv"), "w", newline="") as kf:
        kw = csv.writer(kf)
        kw.writerow(["item", "split", "idx", "stratum"])
        for i, (k, stratum) in enumerate(pick, 1):
            p, j = P[k], J[k]
            txt = [f"ITEM {i}", "", "STATEMENT (from an AI search answer, 2023):", p["statement"], "",
                   "CITED URL (2023): " + p["url"], "",
                   "EVIDENCE an annotator copied from the cited page in 2023:", p.get("evidence_2023") or "(none)", "",
                   "PAGE TITLE: " + (j.get("source_title") or ""), "",
                   "PAGE TEXT (extracted, may be truncated):", (j["source_raw_text"] or "")[:MAX_CHARS]]
            with open(os.path.join(out, "items", f"{i:03d}.txt"), "w") as fo:
                fo.write("\n".join(txt) + "\n")
            kw.writerow([i, k[0], k[1], stratum])
    print(len(pick))


if __name__ == "__main__":
    main()
