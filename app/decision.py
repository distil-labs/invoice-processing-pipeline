"""Step 2: pay the invoice or hold it, and if hold, what is wrong and where."""

from dataclasses import dataclass
from typing import Any, Mapping

from app.erp import Erp
from app.models import GROUNDED, FineTunedModel

NO_PURCHASE_ORDER_FOUND = "no purchase order found for this invoice"


@dataclass(frozen=True)
class Decision:
    """The six-field answer of the grounded decision model."""

    decision: str | None
    invoice_number: str | None
    po_number: str | None
    item: str | None
    invoiced: str | float | None
    expected: str | float | None

    @classmethod
    def from_fields(cls, fields: Mapping[str, Any]) -> "Decision":
        return cls(**{name: fields.get(name) for name in cls.__dataclass_fields__})

    @property
    def is_approved(self) -> bool:
        return self.decision == "approve"


@dataclass(frozen=True)
class DecisionResult:
    """A decision with the reasoning behind it, or the reason there is none."""

    decision: Decision | None
    reasoning: str = ""
    latency_seconds: float = 0.0
    error: str | None = None


@dataclass(frozen=True)
class InvoiceDecider:
    """Checks an invoice against its purchase order and goods receipt with the fine-tuned Qwen3.5-4B."""

    model: FineTunedModel
    erp: Erp

    @classmethod
    def from_env(cls, erp: Erp | None = None) -> "InvoiceDecider":
        return cls(model=FineTunedModel.from_env(GROUNDED), erp=erp or Erp.from_file())

    def decide(self, invoice_message: str) -> DecisionResult:
        documents = self.erp.find_documents(invoice_message)
        if documents is None:
            return DecisionResult(decision=None, error=NO_PURCHASE_ORDER_FOUND)
        answer = self.model.ask(self.compose_input(invoice_message, documents))
        return DecisionResult(decision=Decision.from_fields(answer.fields), reasoning=answer.reasoning, latency_seconds=answer.latency_seconds)

    @staticmethod
    def compose_input(invoice_message: str, erp_documents: str) -> str:
        """The three-document layout the model was trained on."""
        return f"INVOICE MESSAGE\n{invoice_message}\n\n{erp_documents}"
