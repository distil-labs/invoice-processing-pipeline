"""Step 2a: the pay-or-hold decision through Jev (three setups), hosted chat models, and the fine-tuned decision model."""

import argparse
import json
from pathlib import Path

from app.jev import call_jev
from app.models import SlmClient, system_prompt
from benchmarking import common

MAX_LINES = 6
DECISIONS = {
    "approve": "Every check passes.",
    "hold_no_po": "Check 1 fails: the PO number on the invoice is not exactly the number of the PO.",
    "hold_quantity": "Check 1 passes and check 2 fails: some invoice line bills more units than were received.",
    "hold_price": "Checks 1 and 2 pass and check 3 fails: some invoice line has a unit price more than 2% above the PO unit price.",
    "hold_total": "Checks 1 to 3 pass and check 4 fails: the stated total is not the sum of the line totals plus allowed freight.",
}
CHECKS = {
    "hold_no_po": "The PO number referenced on the invoice differs from the number of the purchase order.",
    "hold_quantity": "At least one invoice line bills a quantity greater than the quantity received for that item.",
    "hold_price": "At least one invoice line has a unit price more than 2% above the purchase order unit price for that item.",
    "hold_total": "The total stated on the invoice differs from the sum of the invoice line totals plus the freight charge, where freight counts only if the PO says it may be added.",
}
DEFAULT_BACKENDS = ["jev-single", "jev-checks", "jev-lines", "gemini-3.5-flash-lite", "gpt-5.6-luna", "gpt-5.6-luna-high", "glm-5.3-high"]
GROUPS = ["approve", "hold_no_po", "hold_quantity", "hold_price", "hold_total", "two_"]


def jev_single(case: dict) -> dict:
    """One choice question carrying the full task description."""
    result = call_jev(case["input"], {"decision": {"type": "choice", "instructions": system_prompt("decider"), "criteria": DECISIONS}})
    return {"prediction": result["answers"]["decision"]["choice"], **result}


def jev_checks(case: dict) -> dict:
    """One boolean per policy check, order applied in code."""
    result = call_jev(case["input"], {name: {"type": "boolean", "instructions": text} for name, text in CHECKS.items()})
    failed = [name for name in CHECKS if result["answers"][name]["probability"] >= 0.5]
    return {"prediction": failed[0] if failed else "approve", **result}


def jev_lines(case: dict) -> dict:
    """One boolean per invoice line for quantity and price, plus PO number and total, order applied in code."""
    questions = {"hold_no_po": {"type": "boolean", "instructions": CHECKS["hold_no_po"]}, "hold_total": {"type": "boolean", "instructions": CHECKS["hold_total"]}}
    for n in range(1, MAX_LINES + 1):
        questions[f"quantity_{n}"] = {"type": "boolean", "instructions": f"Invoice line {n} exists and bills a quantity greater than the quantity received for that item."}
        questions[f"price_{n}"] = {"type": "boolean", "instructions": f"Invoice line {n} exists and its unit price is more than 2% above the purchase order unit price for that item."}
    result = call_jev(case["input"], questions)
    fired = {name for name, answer in result["answers"].items() if answer["probability"] >= 0.5}
    if "hold_no_po" in fired:
        prediction = "hold_no_po"
    elif any(name.startswith("quantity_") for name in fired):
        prediction = "hold_quantity"
    elif any(name.startswith("price_") for name in fired):
        prediction = "hold_price"
    else:
        prediction = "hold_total" if "hold_total" in fired else "approve"
    return {"prediction": prediction, **result}


def run_backend(backend: str, cases: list[dict], out_dir: Path) -> dict:
    """Run one backend over all cases, save raw rows, return a summary."""
    if backend == "slm":
        client = SlmClient("decider")
        fn = lambda case: {**(r := common.call_slm(client, case["input"])), "prediction": r["answer"].get("decision")}
    elif backend in ("jev-single", "jev-checks", "jev-lines"):
        fn = {"jev-single": jev_single, "jev-checks": jev_checks, "jev-lines": jev_lines}[backend]
    else:
        system = system_prompt("decider")
        fn = lambda case: {**(r := common.call_hosted(backend, system, case["input"])), "prediction": r["answer"].get("decision")}
    outputs = common.run_parallel(fn, cases)
    rows = [{"id": c["id"], "kind": c["kind"], "gold": c["decision"], "correct": o["prediction"] == c["decision"], **o} for c, o in zip(cases, outputs)]
    (out_dir / f"decider__{backend}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    summary = {"backend": backend, "correct": f"{sum(r['correct'] for r in rows)}/{len(rows)}"}
    for group in GROUPS:
        hits = [r["correct"] for r in rows if r["kind"].startswith(group)]
        summary[group.rstrip("_")] = f"{sum(hits)}/{len(hits)}"
    summary.update(common.cost_and_latency(rows))
    return summary


def main(backends: list[str], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = common.load_jsonl(common.REPO_DIR / "data" / "invoice_cases.jsonl")
    summaries = []
    for backend in backends:
        summaries.append(run_backend(backend, cases, out_dir))
        print("done:", summaries[-1], flush=True)
    common.print_table(summaries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backends", default=",".join(DEFAULT_BACKENDS), help="comma-separated; add 'slm' for the fine-tuned model behind DECIDER_BASE_URL")
    parser.add_argument("--out-dir", type=Path, default=common.RESULTS_DIR / "decider")
    args = parser.parse_args()
    main(backends=args.backends.split(","), out_dir=args.out_dir)
