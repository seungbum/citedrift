#!/bin/sh
# Remaining held-out train steps after the first browser re-check (run from the repo root).
set -e
PY=".venv/bin/python -I"
while ! grep -q "^done" data/live_browser/run_train.log; do sleep 30; done
xvfb-run -a $PY src/recheck_browser.py data/live data/live_browser data/live_browser/extra_train.txt > data/live_browser/run_train_extra.log 2>&1
$PY src/url_features.py data/raw/liu2023 data/pairs_train.jsonl data/live data/live_browser results/train/url_features.jsonl
# pages whose text changed with the browser passes are scored now; the rest were scored earlier on final text
HF_HUB_OFFLINE=1 $PY src/e2_score_now.py data/pairs_train.jsonl results/train/url_features.jsonl results/train/e2_scores_now_part2.jsonl \
  --complete-only --lazy-dom --only-urls results/train/exclude_prescore.txt
cat results/train/e2_scores_now_part1.jsonl results/train/e2_scores_now_part2.jsonl > results/train/e2_scores_now.jsonl
$PY src/e2_drift.py data/pairs_train.jsonl results/train/url_features.jsonl results/train/e1_scores_combo.jsonl \
  results/train/e2_scores_now.jsonl results/judge_combo_params.json results/e1_eval_combo.json \
  results/train/e2_drift.jsonl results/train/e2_summary.json results/train/e1_scores_source_raw_text.jsonl data/raw/liu2023
echo TRAIN_TAIL_DONE
