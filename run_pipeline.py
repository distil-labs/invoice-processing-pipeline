"""Run the accounts payable pipeline over an inbox file and, when the file carries labels, score it end to end."""

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.pipeline import Pipeline
from benchmarking.common import GROUNDED_FIELDS, grounded_answer, load_jsonl, score_answer

REPO_DIR = Path(__file__).parent


def main(triage_backend: str, inbox_path: Path, out_path: Path, limit: int, workers: int, show: int):
    inbox = load_jsonl(inbox_path)[: limit or None]
    cases = {c["id"]: c for c in load_jsonl(REPO_DIR / "data" / "invoice_cases.jsonl")}
    pipeline = Pipeline(triage_backend)

    start = time.time()
    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(lambda m: pipeline.process(m["input"]), inbox))
    wall = time.time() - start

    rows = []
    for message, result in zip(inbox, results):
        row = {"id": message["id"], "gold_label": message.get("label"), **result}
        if message.get("label") == "invoice":
            checks = score_answer(result["decision"] or {}, grounded_answer(cases[message["matching_id"]]), GROUNDED_FIELDS)
            row["correct"] = result["label"] == "invoice" and checks["all"]
            row["decision_correct"] = result["label"] == "invoice" and checks["decision"]
        elif message.get("label"):
            row["correct"] = row["decision_correct"] = result["label"] != "invoice"
        rows.append(row)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    for row in rows[:show]:
        decision = json.dumps(row["decision"]) if row["decision"] else "-"
        print(f"{row['id']}  {row['label']:17s} {decision}")
    n = len(rows)
    invoices = [r for r in rows if r["gold_label"] == "invoice"]
    decided = [r for r in rows if r["decision"] is not None]
    print(f"\nstep 1: {triage_backend} | messages: {n} | sent to step 2: {len(decided)} | {wall:.0f} s with {workers} in flight")
    if all("correct" in r for r in rows):
        print(f"step 1 labels correct: {sum(r['label'] == r['gold_label'] for r in rows)}/{n} | invoices missed: {sum(r['label'] != 'invoice' for r in invoices)} | non-invoices sent to step 2: {sum(r['gold_label'] != 'invoice' for r in decided)}")
        print(f"handled correctly end to end: {sum(r['correct'] for r in rows)}/{n}")
        if invoices:
            print(f"invoices: right decision {sum(r['decision_correct'] for r in invoices)}/{len(invoices)} | all six fields right {sum(r['correct'] for r in invoices)}/{len(invoices)}")
    if decided:
        print(f"median latency: step 1 {statistics.median(r['triage_latency'] for r in rows):.2f} s | step 2 {statistics.median(r['decision_latency'] for r in decided):.2f} s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--triage", default="jev", choices=["jev", "slm"], help="step 1 backend: Jev, or the fine-tuned triage model")
    parser.add_argument("--inbox", type=Path, default=REPO_DIR / "data" / "inbox.jsonl")
    parser.add_argument("--out", type=Path, default=REPO_DIR / "output" / "pipeline.jsonl")
    parser.add_argument("--limit", type=int, default=0, help="only the first N messages")
    parser.add_argument("--workers", type=int, default=8, help="messages in flight")
    parser.add_argument("--show", type=int, default=10, help="print the first N results")
    args = parser.parse_args()
    main(triage_backend=args.triage, inbox_path=args.inbox, out_path=args.out, limit=args.limit, workers=args.workers, show=args.show)
