"""The whole pipeline: triage every message, decide every invoice."""

from dataclasses import dataclass

from app.decision import DecisionResult, InvoiceDecider
from app.triage import FineTunedTriager, JevTriager, TriageResult, Triager

TRIAGE_BACKENDS = ("jev", "slm")


@dataclass(frozen=True)
class PipelineResult:
    """What happened to one message."""

    triage: TriageResult
    decision: DecisionResult | None

    @property
    def reached_step_two(self) -> bool:
        return self.decision is not None


@dataclass(frozen=True)
class Pipeline:
    """Step 1 labels the message; invoices go on to step 2."""

    triager: Triager
    decider: InvoiceDecider

    @classmethod
    def from_env(cls, triage_backend: str = "jev") -> "Pipeline":
        """Build the pipeline with Jev ('jev') or the fine-tuned triage model ('slm') at step 1."""
        triager = JevTriager.from_env() if triage_backend == "jev" else FineTunedTriager.from_env()
        return cls(triager=triager, decider=InvoiceDecider.from_env())

    def process(self, message: str) -> PipelineResult:
        triage = self.triager.triage(message)
        decision = self.decider.decide(message) if triage.is_invoice else None
        return PipelineResult(triage=triage, decision=decision)
