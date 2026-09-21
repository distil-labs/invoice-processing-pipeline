"""The two steps: triage a message, then decide an invoice against its purchase order and goods receipt."""

import json
import re
from pathlib import Path

from app.jev import triage_with_jev
from app.models import SlmClient

REPO_DIR = Path(__file__).parent.parent
INVOICE_NUMBER = re.compile(r"\b[A-Z]{2}-\d{5}\b")


class Pipeline:
    """Step 1 with Jev or the fine-tuned triage model, step 2 with the fine-tuned grounded decision model."""

    def __init__(self, triage_backend: str = "jev", erp_path: Path = REPO_DIR / "data" / "erp.json"):
        self.triage_backend = triage_backend
        self.triage_model = SlmClient("triage") if triage_backend == "slm" else None
        self.decision_model = SlmClient("grounded")
        self.erp = json.loads(erp_path.read_text())

    def triage(self, message: str) -> dict:
        """Step 1: label one message."""
        if self.triage_backend == "jev":
            return triage_with_jev(message)
        result = self.triage_model.ask(message)
        return {"label": result["answer"].get("label"), "confidence": None, "latency": result["latency"], "cost": 0.0}

    def lookup_erp(self, message: str) -> str | None:
        """Find the purchase order and goods receipt for the invoice number in the message. Stands in for an ERP query."""
        for number in INVOICE_NUMBER.findall(message):
            if number in self.erp:
                return self.erp[number]
        return None

    def decide(self, message: str) -> dict:
        """Step 2: pay or hold one invoice, with the item and values behind a hold."""
        documents = self.lookup_erp(message)
        if documents is None:
            return {"answer": {}, "reasoning": "", "latency": 0.0, "error": "no purchase order found for this invoice"}
        return self.decision_model.ask(f"INVOICE MESSAGE\n{message}\n\n{documents}")

    def process(self, message: str) -> dict:
        """Run one message through both steps."""
        first = self.triage(message)
        result = {"label": first["label"], "triage_latency": first["latency"], "triage_cost": first["cost"], "decision": None}
        if first["label"] == "invoice":
            second = self.decide(message)
            result.update(decision=second["answer"], reasoning=second["reasoning"], decision_latency=second["latency"], error=second.get("error"))
        return result
