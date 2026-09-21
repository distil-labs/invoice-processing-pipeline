"""Stand-in for the ERP: the purchase order and goods receipt that belong to an invoice."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_ERP_FILE = Path(__file__).parent.parent / "data" / "erp.json"
INVOICE_NUMBER = re.compile(r"\b[A-Z]{2}-\d{5}\b")


@dataclass(frozen=True)
class Erp:
    """Purchase order and goods receipt texts, keyed by invoice number."""

    documents_by_invoice_number: Mapping[str, str]

    @classmethod
    def from_file(cls, path: Path = DEFAULT_ERP_FILE) -> "Erp":
        return cls(documents_by_invoice_number=json.loads(path.read_text()))

    def find_documents(self, invoice_message: str) -> str | None:
        """Return the purchase order and goods receipt for the first known invoice number in the message."""
        for invoice_number in INVOICE_NUMBER.findall(invoice_message):
            if invoice_number in self.documents_by_invoice_number:
                return self.documents_by_invoice_number[invoice_number]
        return None
