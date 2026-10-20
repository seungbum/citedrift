# Held-out train split outputs

- Human-mode outcomes (`class_human`, the `human` block of `e2_summary.json`) are valid: every complete_support pair
  on a reachable page was scored (`e2_scores_now.jsonl`, `--complete-only --lazy-dom`).
- Tool-mode outcomes are NOT computed for this split (`e2_drift.py --human-only` drops them): pairs whose 2023 label was not
  complete_support were not scored on today's page, so tool mode lacks their current scores. They are not reported.
- Browser records are used only for URLs that the dev/test re-check rule would have opened (`browser_allow.txt`,
  `src/browser_allowlist.py`); 118 extra visits to dead pages made under a broader rule are ignored.
