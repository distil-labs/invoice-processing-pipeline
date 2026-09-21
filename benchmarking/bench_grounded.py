"""Step 2b: the decision plus what is wrong and where, through hosted chat models and the fine-tuned model. Jev cannot produce this output."""

import argparse
import json
from pathlib import Path

from app.models import SlmClient, system_prompt
from benchmarking import common
from benchmarking.bench_decider import GROUPS

DEFAULT_BACKENDS = ["gemini-3.5-flash-lite", "gpt-5.6-luna", "gpt-5.6-luna-high", "glm-5.3-high"]


def run_backend(backend: str, cases: list[dict], out_dir: Path) -> dict:
    """Run one backend over all cases, save raw rows, return a summary."""
    if backend == "slm":
        client = SlmClient("grounded")
        fn = lambda case: common.call_slm(client, case["input"])
    else:
        system = system_prompt("grounded")
        fn = lambda case: common.call_hosted(backend, system, case["input"])
    outputs = common.run_parallel(fn, cases)
    rows = [{"id": c["id"], "kind": c["kind"], "checks": common.score_answer(o["answer"], common.grounded_answer(c), common.GROUNDED_FIELDS), **o} for c, o in zip(cases, outputs)]
    (out_dir / f"grounded__{backend}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    summary = {"backend": backend, "all_fields": f"{sum(r['checks']['all'] for r in rows)}/{len(rows)}"}
    for field in common.GROUNDED_FIELDS:
        summary[field] = sum(r["checks"][field] for r in rows)
    for group in GROUPS:
        hits = [r["checks"]["all"] for r in rows if r["kind"].startswith(group)]
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
    parser.add_argument("--backends", default=",".join(DEFAULT_BACKENDS), help="comma-separated; add 'slm' for the fine-tuned model behind GROUNDED_BASE_URL")
    parser.add_argument("--out-dir", type=Path, default=common.RESULTS_DIR / "grounded")
    args = parser.parse_args()
    main(backends=args.backends.split(","), out_dir=args.out_dir)
