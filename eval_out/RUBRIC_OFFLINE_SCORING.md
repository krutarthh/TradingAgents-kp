# Offline analysis-framework rubric

Use this appendix when scoring traces or saved reports outside LangSmith.

Attach dataset metadata per row via `suggested_langsmith_dataset_metadata` from
`tradingagents.evaluation.langsmith_rubric`.

---

## Analysis framework rubric (trace → final outputs)

Score each dimension **0** (missing), **1** (partial), **2** (strong). Optionally add one-line evidence per item.

1. **Thesis clarity** — `integrated_thesis_report` has bull/base/bear one-liners and an assumption table tied to named sources/tools.
2. **Cross-report triangulation** — conflicts across market, fundamentals, forward, news, sentiment are named; integrator or debate resolves or flags them.
3. **Business & industry** — fundamentals (and forward peers where used) explain economics and competitive context with tool-cited evidence.
4. **Earnings quality** — fundamentals lane addresses cash vs accruals / recurring vs one-offs / red flags where data allows.
5. **Valuation triangulation** — at least two independent anchors (e.g. peer multiple band + forward/consensus sanity); no unsupported “cheap on P/E” alone.
6. **Risks & catalysts** — top risks and repricing catalysts explicit; linked to “what the market is missing” where applicable.
7. **Numeric discipline** — material math uses `evaluate_math_expression` or clearly cites tool numbers; no orphan figures.
8. **Verifier-lite** — `verification_notes` is OK or only minor structural warnings; scenario probabilities in forward lane roughly coherent.
9. **Tool provenance** — string tool outputs show `[tool=…] [vendor=…] [symbol=…] [as_of=…]` where applicable for triangulation.

**Regression focus:** re-run traces where items 7–9 fail; fix tool args, headers, or prompts rather than expanding prose.

---

## How to use with this eval batch

1. Open each run's `full_states_log_<trade_date>.json` under `results_dir` / ticker / TradingAgentsStrategy_logs.
2. Score dimensions 0–2 per `ANALYSIS_FRAMEWORK_RUBRIC_MD`.
3. Compare outcome columns in `eval_results.csv` only after process-quality review.

Outcome metrics (forward alpha) do not validate reasoning quality alone.
