"""Run the accounts payable pipeline over an inbox file and, when the file carries labels, grade it end to end."""

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from app.pipeline import TRIAGE_BACKENDS, Pipeline, PipelineResult
from app.triage import INVOICE
from benchmarking.common import GROUNDED_FIELDS, grounded_answer, load_jsonl, score_answer

REPO_DIR = Path(__file__).parent
DEFAULT_INBOX = REPO_DIR / "data" / "inbox.jsonl"
INVOICE_CASES = REPO_DIR / "data" / "invoice_cases.jsonl"
DEFAULT_OUTPUT = REPO_DIR / "output" / "pipeline.jsonl"


@dataclass(frozen=True)
class InboxMessage:
    """One line of an inbox file; the expected label and invoice case are present only in labelled files."""

    id: str
    text: str
    expected_label: str | None = None
    invoice_case_id: str | None = None

    @classmethod
    def from_row(cls, row: Mapping, position: int) -> "InboxMessage":
        return cls(id=row.get("id", f"M{position:03d}"), text=row["input"], expected_label=row.get("label"), invoice_case_id=row.get("matching_id"))

    @property
    def is_labelled(self) -> bool:
        return self.expected_label is not None

    @property
    def is_invoice(self) -> bool:
        return self.expected_label == INVOICE


@dataclass(frozen=True)
class Outcome:
    """The pipeline's result for one message and, for labelled messages, whether it was right."""

    message: InboxMessage
    result: PipelineResult
    decision_correct: bool | None = None
    handled_correctly: bool | None = None

    @property
    def label_correct(self) -> bool:
        return self.result.triage.label == self.message.expected_label

    def to_row(self) -> dict:
        return {"id": self.message.id, "expected_label": self.message.expected_label, **asdict(self.result),
                "decision_correct": self.decision_correct, "handled_correctly": self.handled_correctly}

    def summary_line(self) -> str:
        decision = self.result.decision.decision if self.result.decision else None
        return f"{self.message.id}  {self.result.triage.label or '?':17s} {json.dumps(asdict(decision)) if decision else '-'}"


@dataclass(frozen=True)
class Report:
    """All outcomes of one run."""

    outcomes: tuple[Outcome, ...]
    triage_backend: str
    wall_seconds: float
    workers: int

    @property
    def invoices(self) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if o.message.is_invoice)

    @property
    def sent_to_step_two(self) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if o.result.reached_step_two)

    @property
    def is_graded(self) -> bool:
        return all(o.message.is_labelled for o in self.outcomes)

    def lines(self) -> list[str]:
        total = len(self.outcomes)
        lines = [f"step 1: {self.triage_backend} | messages: {total} | sent to step 2: {len(self.sent_to_step_two)} | {self.wall_seconds:.0f} s with {self.workers} in flight"]
        if self.is_graded:
            lines += self.grading_lines()
        if self.sent_to_step_two:
            lines.append(f"median latency: step 1 {statistics.median(o.result.triage.latency_seconds for o in self.outcomes):.2f} s"
                         f" | step 2 {statistics.median(o.result.decision.latency_seconds for o in self.sent_to_step_two):.2f} s")
        return lines

    def grading_lines(self) -> list[str]:
        total, invoices = len(self.outcomes), self.invoices
        missed = sum(not o.result.triage.is_invoice for o in invoices)
        misrouted = sum(not o.message.is_invoice for o in self.sent_to_step_two)
        lines = [f"step 1 labels correct: {sum(o.label_correct for o in self.outcomes)}/{total} | invoices missed: {missed} | non-invoices sent to step 2: {misrouted}",
                 f"handled correctly end to end: {sum(o.handled_correctly for o in self.outcomes)}/{total}"]
        if invoices:
            lines.append(f"invoices: right decision {sum(o.decision_correct for o in invoices)}/{len(invoices)} | all six fields right {sum(o.handled_correctly for o in invoices)}/{len(invoices)}")
        return lines


def load_inbox(path: Path, limit: int) -> list[InboxMessage]:
    """Read an inbox file; every line needs an 'input' field."""
    rows = load_jsonl(path)[: limit or None]
    return [InboxMessage.from_row(row, position) for position, row in enumerate(rows, 1)]


def load_expected_answers() -> dict[str, dict]:
    """Expected step 2 answers of the example invoices, by case id."""
    return {case["id"]: grounded_answer(case) for case in load_jsonl(INVOICE_CASES)}


def grade(message: InboxMessage, result: PipelineResult, expected_answers: Mapping[str, dict]) -> Outcome:
    """Compare one result with what was expected; unlabelled messages stay ungraded."""
    if not message.is_labelled:
        return Outcome(message=message, result=result)
    if not message.is_invoice:
        kept_out_of_step_two = not result.reached_step_two
        return Outcome(message=message, result=result, decision_correct=kept_out_of_step_two, handled_correctly=kept_out_of_step_two)
    given = asdict(result.decision.decision) if result.reached_step_two and result.decision.decision else {}
    checks = score_answer(given, expected_answers[message.invoice_case_id], GROUNDED_FIELDS)
    return Outcome(message=message, result=result, decision_correct=checks["decision"], handled_correctly=checks["all"])


def run(pipeline: Pipeline, inbox: list[InboxMessage], workers: int) -> tuple[list[PipelineResult], float]:
    """Process all messages with a few in flight; return the results and the wall-clock seconds."""
    started = time.time()
    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(lambda message: pipeline.process(message.text), inbox))
    return results, time.time() - started


def save(outcomes: tuple[Outcome, ...], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(outcome.to_row()) for outcome in outcomes) + "\n")


def main(triage_backend: str, inbox_path: Path, out_path: Path, limit: int, workers: int, show: int):
    inbox = load_inbox(inbox_path, limit)
    expected_answers = load_expected_answers()
    pipeline = Pipeline.from_env(triage_backend)

    results, wall_seconds = run(pipeline, inbox, workers)
    outcomes = tuple(grade(message, result, expected_answers) for message, result in zip(inbox, results))
    report = Report(outcomes=outcomes, triage_backend=triage_backend, wall_seconds=wall_seconds, workers=workers)

    save(outcomes, out_path)
    for outcome in outcomes[:show]:
        print(outcome.summary_line())
    print()
    for line in report.lines():
        print(line)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--triage", default="jev", choices=TRIAGE_BACKENDS, help="step 1 backend: Jev, or the fine-tuned triage model")
    parser.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=0, help="only the first N messages")
    parser.add_argument("--workers", type=int, default=8, help="messages in flight")
    parser.add_argument("--show", type=int, default=10, help="print the first N results")
    args = parser.parse_args()
    main(triage_backend=args.triage, inbox_path=args.inbox, out_path=args.out, limit=args.limit, workers=args.workers, show=args.show)
