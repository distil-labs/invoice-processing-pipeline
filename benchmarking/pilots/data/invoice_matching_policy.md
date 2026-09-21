# Northwind invoice matching policy

Each case has a purchase order (PO), a goods receipt, and a vendor invoice. Run the checks in this order and stop at the first one that fails.

| Order | Check | Decision if it fails |
|---|---|---|
| 1 | The PO number referenced on the invoice is exactly the number of the PO. | `hold_no_po` |
| 2 | On every invoice line, the invoiced quantity is not more than the received quantity for that item. | `hold_quantity` |
| 3 | On every invoice line, the invoiced unit price is not more than 2% above the PO unit price. A lower price is fine. | `hold_price` |
| 4 | The invoice total stated on the invoice equals the sum of its line totals. | `hold_total` |

If every check passes, the decision is `approve`.

Also report the invoice line number that caused the hold. For `hold_no_po`, `hold_total` and `approve` the line is `null`.
