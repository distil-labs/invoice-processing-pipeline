"""Pilot benchmark (frozen): the exploratory tasks run before the demo tasks were fixed. See pilots/README.md."""

import argparse
import json
import os
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

REPO_DIR = Path(__file__).parent
POLICY_PATH = REPO_DIR / "data" / "expense_policy.md"
JEV_URL = "https://ai-gateway.vercel.sh/v1/evaluate"
JEV_MODEL = "typesafe-ai/jev"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GUIDE_PATH = REPO_DIR / "data" / "gl_coding_guide.md"
MATCHING_PATH = REPO_DIR / "data" / "invoice_matching_policy.md"
LLM_BACKENDS = {
    "gemini-3.5-flash-lite": {"model": "google/gemini-3.5-flash-lite"},
    "gpt-5.6-luna": {"model": "openai/gpt-5.6-luna", "reasoning": {"effort": "none"}},
    "gpt-5.6-luna-reasoning": {"model": "openai/gpt-5.6-luna"},
}
EXTRA_BACKENDS = {
    "qwen3.5-9b-base": {"model": "qwen/qwen3.5-9b", "reasoning": {"enabled": False}},
    "glm-5.3-thinking": {"model": "z-ai/glm-5.3"},
    "kimi-k3-thinking": {"model": "moonshotai/kimi-k3"},
    "qwen3.8-2.4t-thinking": {"model": "qwen/qwen3.8-2.4t-a95b"},
    "glm-5.3-reasoning-high": {"model": "z-ai/glm-5.3", "reasoning": {"effort": "high"}},
    "qwen3.8-2.4t-reasoning-high": {"model": "qwen/qwen3.8-2.4t-a95b", "reasoning": {"effort": "high"}},
    "kimi-k3-reasoning-high": {"model": "moonshotai/kimi-k3", "reasoning": {"effort": "high"}},
    "qwen3.8-2.4t-reasoning-high-nojsonmode": {"model": "qwen/qwen3.8-2.4t-a95b", "reasoning": {"effort": "high"}, "json_mode": False},
    "glm-5.3-reasoning-high-nojsonmode": {"model": "z-ai/glm-5.3", "reasoning": {"effort": "high"}, "json_mode": False},
    "kimi-k3-reasoning-high-nojsonmode": {"model": "moonshotai/kimi-k3", "reasoning": {"effort": "high"}, "json_mode": False},
    "gpt-5.6-luna-reasoning-high": {"model": "openai/gpt-5.6-luna", "reasoning": {"effort": "high"}},
}
WORKERS = 8
RETRIES = 5

TRIAGE_LABELS = {
    "invoice": "A vendor asks us to pay an amount that is not yet due or not yet paid, and this message is the bill itself (including a forwarded bill).",
    "receipt": "Confirmation that a payment was already made or received. Nothing is owed.",
    "payment_reminder": "A follow-up about a bill that was sent earlier: upcoming due date, overdue notice, or final notice.",
    "vendor_question": "A real vendor asks a question or makes a request that is not a bill, a receipt, or a reminder.",
    "spam": "Unsolicited marketing, scams, or phishing, including fake invoices from unknown senders with suspicious links.",
}
DECISIONS = {
    "approve": "No policy rule applies to this expense.",
    "needs_approval": "The expense breaks a rule whose decision is needs_approval, and no reject rule.",
    "reject": "The expense breaks at least one rule whose decision is reject.",
}
MATCHING_DECISIONS = {
    "approve": "Every check passes.",
    "hold_no_po": "The PO number referenced on the invoice is not exactly the number of the PO.",
    "hold_quantity": "The PO number matches, and some invoice line bills more units than were received.",
    "hold_price": "PO number and quantities pass, and some invoice line has a unit price more than 2% above the PO unit price.",
    "hold_total": "PO number, quantities and prices pass, and the stated invoice total is not the sum of the line totals.",
}
MATCHING_CHECKS = {
    "hold_no_po": "The PO number referenced on the invoice differs from the number of the purchase order.",
    "hold_quantity": "At least one invoice line bills a quantity greater than the quantity received for that item.",
    "hold_price": "At least one invoice line has a unit price more than 2% above the purchase order unit price for that item.",
    "hold_total": "The invoice total stated on the invoice is different from the sum of the invoice line totals.",
}
INVOICE_FIELDS = ["vendor", "invoice_number", "total", "currency", "due_date"]


def load_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list of dicts."""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_rules() -> dict[str, dict]:
    """Parse the policy table into {rule_id: {text, decision}}."""
    rules = {}
    for line in POLICY_PATH.read_text().splitlines():
        match = re.match(r"\| (R\d+) \| (.+) \| (\w+) \|", line)
        if match:
            rules[match.group(1)] = {"text": match.group(2), "decision": match.group(3)}
    return rules


def post_with_retry(url: str, headers: dict, payload: dict, timeout: int) -> tuple[requests.Response, float]:
    """POST and retry on rate limits and server errors; return the response and the latency of the successful attempt."""
    for attempt in range(RETRIES):
        start = time.time()
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        latency = time.time() - start
        if response.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(2 ** attempt)
    response.raise_for_status()
    return response, latency


def call_jev(state: str, questions: dict) -> dict:
    """Send one evaluate request to Jev and return answers, latency and cost."""
    response, latency = post_with_retry(
        JEV_URL,
        {"Authorization": f"Bearer {os.environ['VERCEL_API_KEY']}"},
        {"model": JEV_MODEL, "state": state, "questions": questions},
        60,
    )
    body = response.json()
    cost = float(body["providerMetadata"]["gateway"]["marketCost"])
    return {"answers": body["answers"], "latency": latency, "cost": cost}


def call_llm(backend: str, system: str, user: str) -> dict:
    """Send one chat request through OpenRouter and return the parsed JSON answer, latency and cost."""
    config = {**LLM_BACKENDS, **EXTRA_BACKENDS}[backend]
    payload = {
        "model": config["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "usage": {"include": True},
    }
    if config.get("json_mode", True):
        payload["response_format"] = {"type": "json_object"}
    if "reasoning" in config:
        payload["reasoning"] = config["reasoning"]
    response, latency = post_with_retry(OPENROUTER_URL, {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}, payload, 300)
    body = response.json()
    text = body["choices"][0]["message"]["content"] or ""
    try:
        match = re.search(r"\{.*\}", text, flags=re.S)
        answer = json.loads(match.group(0) if match else text)
    except json.JSONDecodeError:
        answer = {"parse_error": text}
    if isinstance(answer, list) and answer and isinstance(answer[0], dict):
        answer = answer[0]
    if not isinstance(answer, dict):
        answer = {"parse_error": text}
    usage = body.get("usage", {})
    return {
        "answer": answer,
        "latency": latency,
        "cost": float(usage.get("cost") or 0),
        "completion_tokens": usage.get("completion_tokens") or 0,
        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0,
        "provider": body.get("provider"),
    }


def triage_jev(example: dict) -> dict:
    """Classify one inbox message with a single Jev choice question."""
    questions = {"label": {"type": "choice", "instructions": "Classify this message sent to an accounts payable inbox.", "criteria": TRIAGE_LABELS}}
    result = call_jev(example["input"], questions)
    answer = result["answers"]["label"]
    return {"prediction": {"label": answer["choice"]}, "confidence": answer.get("confidence"), **result}


def triage_llm(example: dict, backend: str) -> dict:
    """Classify one inbox message with a chat model."""
    definitions = "\n".join(f"- {name}: {text}" for name, text in TRIAGE_LABELS.items())
    system = f'Classify this message sent to an accounts payable inbox.\nLabels:\n{definitions}\nAnswer with JSON: {{"label": "<one label>"}}'
    result = call_llm(backend, system, example["input"])
    return {"prediction": {"label": result["answer"].get("label")}, **result}


def policy_jev_single(example: dict) -> dict:
    """Decide one expense with a single Jev choice question that carries the whole policy."""
    instructions = "Decide this expense line under the policy below.\n\n" + POLICY_PATH.read_text()
    questions = {"decision": {"type": "choice", "instructions": instructions, "criteria": DECISIONS}}
    result = call_jev(example["input"], questions)
    answer = result["answers"]["decision"]
    return {"prediction": {"decision": answer["choice"], "rule": None}, "confidence": answer.get("confidence"), **result}


def policy_jev_rules(example: dict) -> dict:
    """Decide one expense with one Jev boolean question per rule, combined in code."""
    rules = load_rules()
    questions = {
        rule_id: {"type": "boolean", "instructions": f"This expense line breaks the following policy rule: {rule['text']}"}
        for rule_id, rule in rules.items()
    }
    result = call_jev(example["input"], questions)
    fired = {rule_id: answer["probability"] for rule_id, answer in result["answers"].items() if answer["probability"] >= 0.5}
    rejects = {r: p for r, p in fired.items() if rules[r]["decision"] == "reject"}
    chosen = rejects or fired
    if not chosen:
        prediction = {"decision": "approve", "rule": "none"}
    else:
        rule_id = max(chosen, key=chosen.get)
        prediction = {"decision": rules[rule_id]["decision"], "rule": rule_id}
    return {"prediction": prediction, **result}


def policy_llm(example: dict, backend: str) -> dict:
    """Decide one expense with a chat model, returning decision, rule and evidence."""
    system = (
        "Decide this expense line under the policy below.\n\n"
        + POLICY_PATH.read_text()
        + '\nAnswer with JSON: {"decision": "approve|needs_approval|reject", "rule": "<rule id or none>", '
        '"evidence": "<exact quote from the expense that triggered the rule, or empty>"}'
    )
    result = call_llm(backend, system, example["input"])
    return {"prediction": result["answer"], **result}


def extract_llm(example: dict, backend: str) -> dict:
    """Extract invoice fields from one message with a chat model."""
    system = (
        "Extract the invoice fields from this message. Answer with JSON: "
        '{"vendor": "<company name>", "invoice_number": "<as written, without #>", "total": <number, total amount due>, '
        '"currency": "<ISO 4217 code>", "due_date": "<YYYY-MM-DD, computed from the invoice date and terms if needed>"}'
    )
    result = call_llm(backend, system, example["input"])
    return {"prediction": result["answer"], **result}


def account_codes() -> dict[str, str]:
    """Parse the chart of accounts into {code: name}."""
    return dict(re.findall(r"\| (\d{4}) \| (.+?) \|", GUIDE_PATH.read_text()))


def coding_jev(example: dict) -> dict:
    """Assign a GL account with a single Jev choice question that carries the full guide."""
    instructions = "Assign this invoice or expense line to one account, following the coding guide below.\n\n" + GUIDE_PATH.read_text()
    questions = {"label": {"type": "choice", "instructions": instructions, "criteria": account_codes()}}
    result = call_jev(example["input"], questions)
    answer = result["answers"]["label"]
    return {"prediction": {"label": answer["choice"]}, "confidence": answer.get("confidence"), **result}


def coding_llm(example: dict, backend: str) -> dict:
    """Assign a GL account with a chat model that receives the full guide."""
    system = (
        "Assign this invoice or expense line to one account, following the coding guide below.\n\n"
        + GUIDE_PATH.read_text()
        + '\nAnswer with JSON: {"label": "<4-digit account code>"}'
    )
    result = call_llm(backend, system, example["input"])
    return {"prediction": {"label": str(result["answer"].get("label"))}, **result}


def matching_jev_single(example: dict) -> dict:
    """Decide one matching case with a single Jev choice question that carries the policy."""
    instructions = "Decide this invoice matching case under the policy below.\n\n" + MATCHING_PATH.read_text()
    questions = {"decision": {"type": "choice", "instructions": instructions, "criteria": MATCHING_DECISIONS}}
    result = call_jev(example["input"], questions)
    answer = result["answers"]["decision"]
    return {"prediction": {"decision": answer["choice"]}, "confidence": answer.get("confidence"), **result}


def matching_jev_checks(example: dict) -> dict:
    """Decide one matching case with one Jev boolean per check, applying the policy order in code."""
    questions = {name: {"type": "boolean", "instructions": text} for name, text in MATCHING_CHECKS.items()}
    result = call_jev(example["input"], questions)
    failed = [name for name in MATCHING_CHECKS if result["answers"][name]["probability"] >= 0.5]
    return {"prediction": {"decision": failed[0] if failed else "approve"}, **result}


WORKED_FORMAT = (
    '{"po_on_invoice": "<PO number on the invoice>", "po_number": "<number of the PO>", "po_ok": <bool>, '
    '"lines": [{"line": <n>, "received": <qty>, "invoiced": <qty>, "qty_ok": <bool>, "po_price": <number>, '
    '"max_price": <po_price * 1.02, 4 decimals>, "inv_price": <number>, "price_ok": <bool>, "line_total": <number>}], '
    '"running_sum": [<line 1 total>, <sum after line 2>, <sum after line 3>, ...], "stated_total": <number>, "total_ok": <bool>, '
    '"decision": "approve|hold_no_po|hold_quantity|hold_price|hold_total", "line": <invoice line number or null>}'
)


def matching_llm(example: dict, backend: str, worked: bool = False) -> dict:
    """Decide one matching case with a chat model, optionally writing out the checks before the decision."""
    answer_format = WORKED_FORMAT if worked else '{"decision": "approve|hold_no_po|hold_quantity|hold_price|hold_total", "line": <invoice line number or null>}'
    system = (
        "Decide this invoice matching case under the policy below.\n\n"
        + MATCHING_PATH.read_text()
        + "\nAnswer with JSON, fields in this order: " + answer_format
    )
    result = call_llm(backend, system, example["input"])
    return {"prediction": result["answer"], **result}


def normalize(field: str, value) -> str:
    """Normalize one invoice field for comparison."""
    if field == "total":
        try:
            return f"{float(str(value).replace(',', '')):.2f}"
        except ValueError:
            return str(value)
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def score(task: str, example: dict, prediction: dict) -> dict:
    """Return a dict of named boolean checks for one prediction."""
    if task in ("triage", "coding"):
        return {"label": prediction.get("label") == example["label"]}
    if task in ("matching", "matching-worked"):
        checks = {"decision": prediction.get("decision") == example["decision"]}
        if "line" in prediction:
            checks["line"] = checks["decision"] and prediction.get("line") == example["line"]
        return checks
    if task == "policy":
        checks = {"decision": prediction.get("decision") == example["decision"]}
        if prediction.get("rule") is not None:
            checks["rule"] = str(prediction.get("rule")).lower() == example["rule"].lower()
        return checks
    checks = {f: normalize(f, prediction.get(f)) == normalize(f, example["fields"][f]) for f in INVOICE_FIELDS}
    checks["all_fields"] = all(checks.values())
    return checks


def run_backend(task: str, backend: str, examples: list[dict], out_dir: Path, tag: str = "") -> dict:
    """Run one backend over all examples, save raw outputs, and return a summary row."""
    if task == "triage":
        fn = triage_jev if backend == "jev" else lambda e: triage_llm(e, backend)
    elif task == "policy":
        fn = {"jev-single": policy_jev_single, "jev-rules": policy_jev_rules}.get(backend, lambda e: policy_llm(e, backend))
    elif task == "matching-worked":
        fn = lambda e: matching_llm(e, backend, worked=True)
    elif task == "matching":
        fn = {"jev-single": matching_jev_single, "jev-checks": matching_jev_checks}.get(backend, lambda e: matching_llm(e, backend))
    elif task == "coding":
        fn = coding_jev if backend == "jev" else lambda e: coding_llm(e, backend)
    else:
        fn = lambda e: extract_llm(e, backend)
    with ThreadPoolExecutor(WORKERS) as pool:
        outputs = list(pool.map(fn, examples))
    rows = []
    for example, output in zip(examples, outputs):
        rows.append({"id": example["id"], "checks": score(task, example, output["prediction"]), **output})
    out_path = out_dir / f"{task}{tag}__{backend}.jsonl"
    out_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    summary = {"backend": backend, "n": len(rows)}
    for check in rows[0]["checks"]:
        hits = [r["checks"][check] for r in rows if check in r["checks"]]
        summary[check] = f"{sum(hits)}/{len(hits)}"
    if "kind" in examples[0]:
        check = "decision" if task in ("policy", "matching", "matching-worked") else "label"
        for kind in sorted({e["kind"] for e in examples}):
            hits = [r["checks"][check] for r, e in zip(rows, examples) if e["kind"] == kind]
            summary[f"{check}_{kind}"] = f"{sum(hits)}/{len(hits)}"
    if "reasoning_tokens" in rows[0]:
        summary["median_reasoning_tok"] = int(statistics.median(r["reasoning_tokens"] for r in rows))
        summary["median_completion_tok"] = int(statistics.median(r["completion_tokens"] for r in rows))
    summary["median_latency_s"] = round(statistics.median(r["latency"] for r in rows), 2)
    summary["usd_per_1000"] = round(1000 * sum(r["cost"] for r in rows) / len(rows), 4)
    return summary


def main(task: str, data_dir: Path, out_dir: Path, extra: bool, inbox_file: str, only: list[str]):
    out_dir.mkdir(parents=True, exist_ok=True)
    llm_backends = list(LLM_BACKENDS) + (list(EXTRA_BACKENDS) if extra else [])
    if task == "triage":
        examples = load_jsonl(data_dir / inbox_file)
        backends = ["jev"] + llm_backends
    elif task == "policy":
        examples = load_jsonl(data_dir / "expenses.jsonl")
        backends = ["jev-single", "jev-rules"] + llm_backends
    elif task == "matching-worked":
        examples = load_jsonl(data_dir / "matching.jsonl")
        backends = ["gemini-3.5-flash-lite", "gpt-5.6-luna"] + (["qwen3.5-9b-base"] if extra else [])
    elif task == "matching":
        examples = load_jsonl(data_dir / "matching.jsonl")
        backends = ["jev-single", "jev-checks"] + llm_backends
    elif task == "coding":
        examples = load_jsonl(data_dir / "gl_coding.jsonl")
        backends = ["jev"] + llm_backends
    else:
        examples = [e for e in load_jsonl(data_dir / "inbox.jsonl") if e["label"] == "invoice"]
        backends = llm_backends
    summaries = []
    for backend in only or backends:
        tag = "-injected" if task == "triage" and inbox_file != "inbox.jsonl" else ""
        summaries.append(run_backend(task, backend, examples, out_dir, tag))
        print("done:", summaries[-1], flush=True)
    columns = list(summaries[-1].keys())
    print(" | ".join(columns))
    for summary in summaries:
        print(" | ".join(str(summary.get(c, "-")) for c in columns))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, choices=["triage", "policy", "coding", "matching", "matching-worked", "extract"])
    parser.add_argument("--data-dir", type=Path, default=REPO_DIR / "data")
    parser.add_argument("--out-dir", type=Path, default=REPO_DIR / "results")
    parser.add_argument("--inbox-file", default="inbox.jsonl")
    parser.add_argument("--backends", default="", help="comma-separated backend names; overrides the default list")
    parser.add_argument("--extra", action="store_true", help="also run the base student proxy and the teacher candidates")
    args = parser.parse_args()
    main(task=args.task, data_dir=args.data_dir, out_dir=args.out_dir, extra=args.extra, inbox_file=args.inbox_file, only=[b for b in args.backends.split(",") if b])
