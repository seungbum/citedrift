# KPI pre-registration (written 2026-10-16 08:33 KST, before any train-split result exists)

Restored original targets:
- S2: share of flagged content changes that a blind AI agent confirms as no longer fully supported >= 0.60.
  Measured on all *validation* labels, i.e. samples that played no part in choosing the outcome rule:
  data/inspection2 (pairs whose current outcome is content_changed) pooled with a new blind sample of
  content-change flags from the Liu et al. TRAIN split (data/inspection_train), which no design choice has
  touched (judge fitted on dev, rule chosen on data/inspection). Design-sample labels (data/inspection) are excluded.
- S9: CiteDrift F1 > F1 of every baseline (weighted over checkable pairs, results/baseline_spotcheck.json).

Train-split procedure (fixed now): same fetch policy and code as dev+test; browser re-check for refused pages;
outcome rule, judge, threshold and combination weights unchanged; sample up to 50 content-change flags,
30 still-supported, 20 away, 20 uncertain, seed 3, same packet format and agent instructions as data/inspection2.
