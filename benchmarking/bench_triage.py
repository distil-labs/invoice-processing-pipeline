"""Step 1: inbox triage through Jev, hosted chat models, and the fine-tuned triage model."""

import argparse
import json
from pathlib import Path

from app.jev import triage_with_jev
from app.models import SlmClient, system_prompt, triage_labels
from benchmarking import common

DEFAULT_BACKENDS = ["jev", "gemini-3.5-flash-lite", "gpt-5.6-luna", "gpt-5.6-luna-high", "glm-5.3-high"]


def run_backend(backend: str, rows: list[dict], out_dir: Path) -> dict:
    """Run one backend over the inbox, save raw rows, return a summary."""
    if backend == "jev":
        fn = lambda row: {**(r := triage_with_jev(row["input"])), "prediction": r["label"]}
    elif backend == "slm":
        client = SlmClient("triage")
        fn = lambda row: {**(r := common.call_slm(client, row["input"])), "prediction": r["answer"].get("label")}
    else:
        system = system_prompt("triage")
        fn = lambda row: {**(r := common.call_hosted(backend, system, row["input"])), "prediction": r["answer"].get("label")}
    outputs = common.run_parallel(fn, rows)
    scored = [{"id": r["id"], "gold": r["label"], "hard": r["hard"], "correct": o["prediction"] == r["label"], **o} for r, o in zip(rows, outputs)]
    (out_dir / f"triage__{backend}.jsonl").write_text("\n".join(json.dumps(s) for s in scored) + "\n")
    summary = {"backend": backend, "correct": f"{sum(s['correct'] for s in scored)}/{len(scored)}"}
    for label in triage_labels():
        hits = [s["correct"] for s in scored if s["gold"] == label]
        summary[label] = f"{sum(hits)}/{len(hits)}"
    hard = [s["correct"] for s in scored if s["hard"]]
    summary["hard"] = f"{sum(hard)}/{len(hard)}"
    missed = sum(s["gold"] == "invoice" and not s["correct"] for s in scored)
    false_invoice = sum(s["gold"] != "invoice" and s["prediction"] == "invoice" for s in scored)
    summary["invoices_missed / non-invoices_sent_to_step_2"] = f"{missed} / {false_invoice}"
    summary.update(common.cost_and_latency(scored))
    return summary


def main(backends: list[str], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = common.load_jsonl(common.REPO_DIR / "data" / "inbox.jsonl")
    summaries = []
    for backend in backends:
        summaries.append(run_backend(backend, rows, out_dir))
        print("done:", summaries[-1], flush=True)
    common.print_table(summaries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backends", default=",".join(DEFAULT_BACKENDS), help="comma-separated; add 'slm' for the fine-tuned model behind TRIAGE_BASE_URL")
    parser.add_argument("--out-dir", type=Path, default=common.RESULTS_DIR / "triage")
    args = parser.parse_args()
    main(backends=args.backends.split(","), out_dir=args.out_dir)
