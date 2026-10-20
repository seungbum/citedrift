# CiteDrift: reproduce every number, the explorer data and the paper PDF.
#   make fetch      re-fetch cited pages + one-time browser re-check (network; slow; not needed to reproduce numbers)
#   make baselines  urlhealth run + Wayback re-query (network)
#   make e1         judge scores on the 2023 text, string-match baseline, combined judge, Qwen, evaluation (GPU)
#   make e2         current-page features, link states, judge scores now, drift classes (GPU)
#   make e3         end-to-end latency on 20 answers (network + GPU)
#   make tables     calibration, baseline comparison, numbers.tex for the paper
#   make explorer   app/static/explorer.json
#   make site       copy the static explorer to docs/ (GitHub Pages)
#   make pdf        paper/main.pdf
# Behind a TLS-intercepting proxy set REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt.

PY   := .venv/bin/python -I
LIU  := data/raw/liu2023
PAIRS:= data/pairs_devtest.jsonl
R    := results
export HF_HUB_OFFLINE ?= 1

.PHONY: fetch baselines e1 e2 e3 e4 tables explorer pdf check all site
all: e1 e2 tables explorer pdf check

$(PAIRS):
	$(PY) src/build_pairs.py $(LIU) $(PAIRS)

fetch: $(PAIRS)
	python3 -I src/fetch_live.py $(LIU)/verifiability_judgments data/live
	xvfb-run -a $(PY) src/recheck_browser.py data/live data/live_browser
	xvfb-run -a $(PY) src/recheck_browser.py data/live data/live_browser data/live_browser/extra_short_text.txt
	xvfb-run -a $(PY) src/recheck_browser.py data/live data/live_browser data/live_browser/extra_botwall.txt

baselines: $(PAIRS)
	$(PY) src/baseline_urlhealth.py data/live $(PAIRS) $(R)/baseline_urlhealth.jsonl
	$(PY) src/check_wayback_gaps.py $(R)/baseline_urlhealth.jsonl $(R)/wayback_gaps.jsonl

e1: $(PAIRS)
	$(PY) src/e1_score_2023.py $(LIU) $(PAIRS) $(R)/e1_scores_source_text.jsonl source_text
	$(PY) src/e1_score_2023.py $(LIU) $(PAIRS) $(R)/e1_scores_source_raw_text.jsonl source_raw_text
	$(PY) src/e1_eval.py $(PAIRS) $(R)/e1_scores_source_text.jsonl $(R)/e1_eval_source_text.json
	$(PY) src/e1_eval.py $(PAIRS) $(R)/e1_scores_source_raw_text.jsonl $(R)/e1_eval_source_raw_text.json
	$(PY) src/baseline_ngram.py $(LIU) $(PAIRS) $(R)/e1_scores_ngram.jsonl
	$(PY) src/e1_eval.py $(PAIRS) $(R)/e1_scores_ngram.jsonl $(R)/e1_eval_ngram.json
	$(PY) src/e1_combo.py $(PAIRS) $(R)/e1_scores_source_raw_text.jsonl $(R)/e1_scores_ngram.jsonl $(R)/e1_scores_combo.jsonl $(R)/judge_combo_params.json
	$(PY) src/e1_eval.py $(PAIRS) $(R)/e1_scores_combo.jsonl $(R)/e1_eval_combo.json
	$(PY) src/e1_subset.py $(PAIRS) $(R)/e1_scores_source_raw_text.jsonl $(R)/e1_scores_ngram.jsonl $(R)/e1_scores_combo.jsonl $(R)/e1_subset.json
	$(PY) src/e1_qwen.py $(LIU) $(PAIRS) $(R)/e1_scores_source_raw_text.jsonl $(R)/e1_qwen_raw_top3.jsonl
	$(PY) src/e1_qwen_eval.py $(PAIRS) $(R)/e1_qwen_raw_top3.jsonl $(R)/e1_scores_combo.jsonl $(R)/e1_eval_combo.json $(R)/e1_eval_qwen.json

e2: $(PAIRS)
	$(PY) src/url_features.py $(LIU) $(PAIRS) data/live data/live_browser $(R)/url_features.jsonl
	$(PY) src/e2_score_now.py $(PAIRS) $(R)/url_features.jsonl $(R)/e2_scores_now.jsonl
	$(PY) src/e2_drift.py $(PAIRS) $(R)/url_features.jsonl $(R)/e1_scores_combo.jsonl $(R)/e2_scores_now.jsonl \
	  $(R)/judge_combo_params.json $(R)/e1_eval_combo.json $(R)/e2_drift.jsonl $(R)/e2_summary.json \
	  $(R)/e1_scores_source_raw_text.jsonl $(LIU)

e4:
	$(PY) src/e4_checkmode.py $(LIU) $(PAIRS) $(R)/e2_drift.jsonl $(R)/e4_checkmode.json 60

e3:
	$(PY) src/e3_latency.py $(LIU) $(PAIRS) $(R)/e3_latency.json 20
	$(PY) src/e3_latency.py $(LIU) $(PAIRS) $(R)/e3_latency_explain.json 5 --explain

tables:
	$(PY) src/calibration_summary.py $(R)/drift_devtest.jsonl $(R)/url_features.jsonl data/live_browser/browser_log.jsonl $(R)/wayback_gaps.jsonl $(R)/calibration.json
	$(PY) src/baseline_compare.py $(R)/e2_drift.jsonl $(R)/baseline_urlhealth.jsonl $(R)/e1_eval_ngram.json $(PAIRS) $(R)/url_features.jsonl $(R)/baseline_compare.json
	$(PY) src/inspection_eval.py data/inspection/key.csv data/inspection/labels.csv $(R)/inspection_summary.json
	$(PY) src/inspection_eval.py data/inspection2/key.csv data/inspection2/labels.csv $(R)/inspection2_summary.json $(R)/e2_drift.jsonl
	$(PY) src/inspection_estimate.py $(R)/e2_drift.jsonl $(R)/e2_drift_rule1.jsonl data/inspection2/key.csv data/inspection2/labels.csv $(R)/inspection2_estimate.json
	$(PY) src/inspection_control_estimate.py data/inspection2/key.csv data/inspection2/labels.csv data/inspection2_control/key.csv data/inspection2_control/labels.csv $(R)/e2_drift.jsonl $(R)/e2_drift_rule1.jsonl $(R)/inspection_control_estimate.json
	$(PY) src/baseline_on_spotcheck.py data/inspection2/key.csv data/inspection2/labels.csv $(R)/e2_drift.jsonl $(R)/baseline_urlhealth.jsonl $(R)/e1_eval_ngram.json $(PAIRS) $(R)/url_features.jsonl $(R)/baseline_spotcheck.json $(R)/e2_drift_rule1.jsonl
	$(PY) src/threshold_provenance.py $(R)/url_features.jsonl $(R)/threshold_provenance.json
	test ! -f data/inspection2/author_check.csv || $(PY) src/author_check_eval.py data/inspection2/author_check.csv $(R)/author_check.json
	$(PY) src/make_numbers.py $(R) paper/numbers.tex

explorer:
	$(PY) src/export_explorer.py $(PAIRS) $(R)/e2_drift.jsonl $(R)/e2_summary.json $(R)/url_features.jsonl $(LIU) app/static/explorer.json \
	  $(R)/baseline_urlhealth.jsonl

pdf:
	cd paper && ../../.bin/tectonic -X compile main.tex > build.log 2>&1 || (cat build.log; exit 1)

check:
	$(PY) src/check_paper.py paper

site:  # static explorer for GitHub Pages (docs/, no check mode); docs/citedrift_demo.mp4 comes from src/make_video.py + src/add_narration.py
	cp app/static/index.html app/static/app.js app/static/style.css app/static/explorer.json docs/ && touch docs/.nojekyll

# Held-out validation on the Liu et al. TRAIN split (no design choice used it; see results/KPI_preregistration.md).
# Network steps (fetch, browser) are listed for the record; scoring steps reproduce from the cached pages.
TR := results/train
train-fetch:
	$(PY) src/build_pairs.py $(LIU) data/pairs_train.jsonl train
	python3 -I src/fetch_live.py $(LIU)/verifiability_judgments data/live train
	xvfb-run -a $(PY) src/recheck_browser.py data/live data/live_browser
	$(PY) src/browser_allowlist.py data/pairs_train.jsonl data/live data/live_browser/train_allow.txt
	xvfb-run -a $(PY) src/recheck_browser.py data/live data/live_browser data/live_browser/train_allow.txt  # dev/test rule only
train:
	$(PY) src/e1_score_2023.py $(LIU) data/pairs_train.jsonl $(TR)/e1_scores_source_raw_text.jsonl source_raw_text
	$(PY) src/baseline_ngram.py $(LIU) data/pairs_train.jsonl $(TR)/e1_scores_ngram.jsonl
	$(PY) src/apply_combo.py $(TR)/e1_scores_source_raw_text.jsonl $(TR)/e1_scores_ngram.jsonl $(R)/judge_combo_params.json $(TR)/e1_scores_combo.jsonl
	$(PY) src/e1_heldout.py data/pairs_train.jsonl $(TR)/e1_scores_combo.jsonl $(R)/e1_eval_combo.json $(TR)/e1_eval.json
	$(PY) src/browser_allowlist.py data/pairs_train.jsonl data/live $(TR)/browser_allow.txt
	$(PY) src/url_features.py $(LIU) data/pairs_train.jsonl data/live data/live_browser $(TR)/url_features.jsonl --browser-allow $(TR)/browser_allow.txt
	$(PY) src/e2_score_now.py data/pairs_train.jsonl $(TR)/url_features.jsonl $(TR)/e2_scores_now.jsonl --complete-only --lazy-dom
	$(PY) src/e2_drift.py data/pairs_train.jsonl $(TR)/url_features.jsonl $(TR)/e1_scores_combo.jsonl $(TR)/e2_scores_now.jsonl \
	  $(R)/judge_combo_params.json $(R)/e1_eval_combo.json $(TR)/e2_drift.jsonl $(TR)/e2_summary.json \
	  $(TR)/e1_scores_source_raw_text.jsonl $(LIU) --human-only
	$(PY) src/inspection_eval.py data/inspection_train/key.csv data/inspection_train/labels.csv $(R)/inspection_train_summary.json $(TR)/e2_drift.jsonl
