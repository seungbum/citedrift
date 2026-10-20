"""Build the statement-citation pair index used by all experiments.

Joins each verifiability judgment (dev/test) to the engine that produced the
response, using human_evaluation_annotations.jsonl (citation markers are
stripped in the judgments file, so responses are compared after removing
"[n]" markers and whitespace). Page texts are not copied; experiments read
them from the original files by (split, idx).

Usage: .venv/bin/python -I src/build_pairs.py <liu_dir> <out_jsonl> [splits...]
"""
import collections, gzip, json, os, re, sys

MARK = re.compile(r"\[\d+\]")


def key(s):
    return re.sub(r"\W+", "", MARK.sub("", s or "")).lower()


def clean_statement(s):
    s = MARK.sub("", s or "").replace("**", "")
    return re.sub(r"\s+", " ", s).strip()


def main():
    liu, out_path = sys.argv[1], sys.argv[2]
    splits = sys.argv[3:] or ["dev", "test"]
    resp = collections.defaultdict(set)
    byq = collections.defaultdict(list)
    with open(os.path.join(liu, "human_evaluation_annotations.jsonl")) as f:
        for line in f:
            h = json.loads(line)
            resp[(key(h["query"]), key(h["response"]))].add(h["system_name"])
            byq[key(h["query"])].append(h)
    stats = collections.Counter()
    with open(out_path, "w") as out:
        for sp in splits:
            p = os.path.join(liu, "verifiability_judgments", f"verifiability_judgments_{sp}.jsonl.gz")
            with gzip.open(p, "rt") as f:
                for i, line in enumerate(f):
                    j = json.loads(line)
                    eng = resp.get((key(j["query"]), key(j["response"])), set())
                    if len(eng) != 1:  # fall back: same query, cites this URL, contains the statement
                        st = key(j["statement"])
                        eng = {h["system_name"] for h in byq[key(j["query"])]
                               if st in key(h["response"])
                               and any(c["link_target"] == j["source_url"] for c in h["citations"])}
                    engine = next(iter(eng)) if len(eng) == 1 else None
                    stats["matched" if engine else ("ambiguous" if eng else "unmatched")] += 1
                    out.write(json.dumps({
                        "split": sp, "idx": i, "engine": engine, "query": j["query"],
                        "statement": clean_statement(j["statement"]), "url": j["source_url"],
                        "label_2023": j["source_supports_statement"],
                        "evidence_2023": j.get("source_localized_evidence"),
                        "source_date": j.get("source_date"),
                    }) + "\n")
    print(dict(stats))


if __name__ == "__main__":
    main()
