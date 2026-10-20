"""Agreement of the author's hand-check with the AI inspector's labels (data/inspection2/author_check.csv).

The CSV is exported from data/inspection2/author_check.html: one row per (item, question) with the author's
"agree"/"disagree" (and an optional comment). Reports items checked and agreement per question.

Usage: .venv/bin/python -I src/author_check_eval.py <author_check_csv> <out_json>
"""
import collections, csv, json, sys


def main():
    rows = list(csv.DictReader(open(sys.argv[1])))
    votes = [r for r in rows if r["question"] in ("current_support", "evidence_now", "same_document")
             and r["author"] in ("agree", "disagree")]
    items = {r["item"] for r in votes}
    per_q = collections.defaultdict(lambda: [0, 0])
    for r in votes:
        per_q[r["question"]][1] += 1
        per_q[r["question"]][0] += r["author"] == "agree"
    agree = sum(r["author"] == "agree" for r in votes)
    res = {"items_checked": len(items), "votes": len(votes), "agree": agree,
           "agree_rate": agree / len(votes) if votes else None, "per_question": dict(per_q),
           "comments": {r["item"]: r["author"] for r in rows if r["question"] == "comment" and r["author"].strip()}}
    json.dump(res, open(sys.argv[2], "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("items_checked", "votes", "agree", "agree_rate", "per_question")}))


if __name__ == "__main__":
    main()
