"""Generate three-way-match pilot cases with labels computed in code."""

import argparse
import json
import random
from pathlib import Path

ITEMS = [
    ("Nitrile gloves, box of 100", 12.50), ("Safety glasses, clear lens", 8.40), ("Pallet wrap, 18 in roll", 23.75),
    ("Hydraulic oil ISO 46, 5 gal", 86.00), ("Cutting disc 125 mm, pack of 25", 31.20), ("Hex bolt M10 x 40, box of 200", 44.90),
    ("Shipping label roll 4x6", 17.60), ("Corrugated box 600x400x400", 3.85), ("LED high bay light 150 W", 129.00),
    ("Conveyor belt cleaner", 64.30), ("Forklift propane cylinder refill", 27.00), ("Thermal transfer ribbon", 9.95),
    ("Packing tape 48 mm, case of 36", 58.00), ("Steel strapping coil 16 mm", 142.50), ("Absorbent pads, bale", 71.25),
]
VENDORS = ["Kessler Industrial Supply", "Marlow Packaging", "Trident Fasteners", "Bexley Safety Co.", "Orrin Lubricants"]
SCENARIOS = {"approve_clean": 8, "approve_near": 12, "hold_no_po": 8, "hold_quantity": 10, "hold_price": 10, "hold_total": 8, "precedence": 4}
OK_PCTS = [1.0, 1.5, 1.8]
BAD_PCTS = [2.5, 3.0, 4.0, 6.0]


def money(value: float) -> str:
    """Format a number as USD with thousands separators."""
    return f"USD {value:,.2f}"


def bump_price(price: float, pct: float) -> float:
    """Raise a price by pct percent, rounded to cents."""
    return round(price * (1 + pct / 100), 2)


def build_case(rng: random.Random, scenario: str, index: int) -> dict:
    """Build one case for a scenario and compute its label from the numbers."""
    vendor = rng.choice(VENDORS)
    po_number = f"PO-{rng.randint(40000, 69999)}"
    lines = []
    for name, price in rng.sample(ITEMS, rng.randint(3, 5)):
        ordered = rng.choice([5, 10, 12, 20, 24, 40, 50])
        received = ordered if rng.random() < 0.6 else ordered - rng.choice([1, 2, 5])
        lines.append({"name": name, "po_price": price, "ordered": ordered, "received": max(received, 1)})
    for line in lines:
        line["inv_qty"] = line["received"]
        line["inv_price"] = line["po_price"]
    invoice_po = po_number
    target = rng.randrange(len(lines))

    if scenario in ("approve_near", "precedence"):
        near = rng.choice([i for i in range(len(lines)) if i != target] or [target])
        lines[near]["inv_price"] = bump_price(lines[near]["po_price"], rng.choice(OK_PCTS))
        other = rng.randrange(len(lines))
        if other != near:
            lines[other]["inv_price"] = round(lines[other]["po_price"] * 0.97, 2)
    if scenario == "hold_no_po":
        digits = list(po_number[3:])
        digits[-1], digits[-2] = digits[-2], digits[-1]
        swapped = "PO-" + "".join(digits)
        invoice_po = swapped if swapped != po_number else f"PO-{int(po_number[3:]) + 10}"
    if scenario in ("hold_quantity", "precedence"):
        lines[target]["received"] = max(lines[target]["ordered"] - rng.choice([2, 3, 5]), 1)
        lines[target]["inv_qty"] = lines[target]["ordered"]
    if scenario == "hold_price" or scenario == "precedence":
        price_line = target if scenario == "hold_price" else (target + 1) % len(lines)
        lines[price_line]["inv_price"] = bump_price(lines[price_line]["po_price"], rng.choice(BAD_PCTS))

    line_sum = round(sum(l["inv_qty"] * l["inv_price"] for l in lines), 2)
    stated_total = line_sum
    if scenario == "hold_total":
        stated_total = round(line_sum + rng.choice([-90.0, -18.0, 10.0, 27.0, 100.0]), 2)

    decision, bad_line = "approve", None
    if invoice_po != po_number:
        decision = "hold_no_po"
    else:
        for check, test in (("hold_quantity", lambda l: l["inv_qty"] > l["received"]), ("hold_price", lambda l: l["inv_price"] > l["po_price"] * 1.02)):
            failing = [i + 1 for i, l in enumerate(lines) if test(l)]
            if failing:
                decision, bad_line = check, failing[0]
                break
        else:
            if stated_total != line_sum:
                decision = "hold_total"

    text = [f"PURCHASE ORDER {po_number} (open). Vendor: {vendor}"]
    text += [f"{i}. {l['name']} | qty {l['ordered']} | unit {money(l['po_price'])}" for i, l in enumerate(lines, 1)]
    text += ["", f"GOODS RECEIPT for {po_number}"]
    text += [f"{i}. {l['name']} | received {l['received']}" for i, l in enumerate(lines, 1)]
    text += ["", f"INVOICE {vendor.split()[0][:2].upper()}-{rng.randint(10000, 99999)} from {vendor}. References {invoice_po}"]
    text += [f"{i}. {l['name']} | qty {l['inv_qty']} | unit {money(l['inv_price'])} | line total {money(l['inv_qty'] * l['inv_price'])}" for i, l in enumerate(lines, 1)]
    text += [f"Invoice total: {money(stated_total)}"]
    return {"id": f"T{index:02d}", "input": "\n".join(text), "decision": decision, "line": bad_line, "kind": scenario}


def main(out_path: Path, seed: int):
    rng = random.Random(seed)
    cases, index = [], 1
    for scenario, count in SCENARIOS.items():
        for _ in range(count):
            cases.append(build_case(rng, scenario, index))
            index += 1
    out_path.write_text("\n".join(json.dumps(c) for c in cases) + "\n")
    print(len(cases), "cases ->", out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "matching.jsonl")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    main(out_path=args.out, seed=args.seed)
