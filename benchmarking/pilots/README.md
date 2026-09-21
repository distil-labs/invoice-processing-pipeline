# Pilots

Small exploratory runs from 2026-09-20, before the demo tasks were fixed. They are kept as they were run, because they show where Jev does well and how the step 2 task was found. Sample sizes are 20 to 60, so read them as direction only.

| Pilot | Data | What it showed |
|---|---|---|
| Inbox triage, 25 messages | `data/inbox.jsonl` | Jev, gemini-3.5-flash-lite and gpt-5.6-luna all 25 of 25; Jev cheapest and fastest |
| Expense policy decisions, 12 written rules, 20 lines | `data/expenses.jsonl`, `data/expense_policy.md` | Jev 18 of 20, level with the small hosted models; every error from every model was arithmetic close to a threshold |
| General ledger coding, 24 accounts and 12 conventions, 50 lines | `data/gl_coding.jsonl`, `data/gl_coding_guide.md` | Jev 50 of 50, including all 27 lines that need an exception or precedence rule |
| Triage with injected instructions, 25 messages | `data/inbox_injected.jsonl` | Jev 25 of 25; an untuned 9B open model 12 of 25 without an instruction to ignore injected text |
| Three-way invoice matching on clean tables, 60 cases | `data/matching.jsonl`, `data/invoice_matching_policy.md`, `make_matching_pilot.py` | The first task that separated the models: every one-pass model 37 to 45 of 60 (Jev 44), models that reason or write out their working 57 to 60 |
| Invoice field extraction, 10 messages | the invoices in `data/inbox.jsonl` | Both small hosted models 10 of 10; Jev cannot return text |

Two findings about the harness came out of the matching pilot and apply to the main benchmarks: forcing JSON mode on reasoning models lowered their accuracy (one model went from 60 of 60 to 47 to 50), and `gpt-5.6-luna` decides per request whether to reason unless the effort is set, so it is always reported with reasoning off and with effort high.

`benchmark.py` is the script these pilots were run with, frozen. It reads `data/` and writes to `results/` in this folder, and needs `VERCEL_API_KEY` and `OPENROUTER_API_KEY`. The raw responses of every run are in `results/`.
