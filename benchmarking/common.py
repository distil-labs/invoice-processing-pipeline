"""Shared benchmark helpers: hosted chat models through OpenRouter, the fine-tuned models, exact scoring."""

import json
import os
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.jev import post_with_retry
from app.models import SlmClient

REPO_DIR = Path(__file__).parent.parent
RESULTS_DIR = Path(__file__).parent / "results"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
WORKERS = 8
# Reasoning models run at effort high and without JSON mode: forcing JSON mode lowered their accuracy in our pilots.
HOSTED = {
    "gemini-3.5-flash-lite": {"model": "google/gemini-3.5-flash-lite"},
    "gpt-5.6-luna": {"model": "openai/gpt-5.6-luna", "reasoning": {"effort": "none"}},
    "gpt-5.6-luna-high": {"model": "openai/gpt-5.6-luna", "reasoning": {"effort": "high"}, "json_mode": False},
    "glm-5.3-high": {"model": "z-ai/glm-5.3", "reasoning": {"effort": "high"}, "json_mode": False},
}
GROUNDED_FIELDS = ["decision", "invoice_number", "po_number", "item", "invoiced", "expected"]


def load_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list of dicts."""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def call_hosted(backend: str, system: str, user: str) -> dict:
    """Send one chat request through OpenRouter and return the parsed JSON answer with latency, cost and token counts."""
    config = HOSTED[backend]
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
    match = re.search(r"\{.*\}", text, flags=re.S)
    try:
        answer = json.loads(match.group(0) if match else text)
    except json.JSONDecodeError:
        answer = {}
    usage = body.get("usage", {})
    return {
        "answer": answer if isinstance(answer, dict) else {},
        "latency": latency,
        "cost": float(usage.get("cost") or 0),
        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0,
        "provider": body.get("provider"),
    }


def call_slm(client: SlmClient, user: str) -> dict:
    """Send one input to a fine-tuned model in the same result shape as call_hosted."""
    result = client.ask(user)
    return {"answer": result["answer"], "latency": result["latency"], "cost": 0.0, "reasoning_tokens": len(result["reasoning"]) // 3, "provider": "own endpoint"}


def run_parallel(fn, rows: list[dict]) -> list[dict]:
    """Apply fn to every row with a small thread pool, keeping order."""
    with ThreadPoolExecutor(WORKERS) as pool:
        return list(pool.map(fn, rows))


def cost_and_latency(rows: list[dict]) -> dict:
    """Median latency, median reasoning tokens and cost per 1,000 requests."""
    return {
        "reasoning_tok": int(statistics.median(r.get("reasoning_tokens", 0) for r in rows)),
        "latency_s": round(statistics.median(r["latency"] for r in rows), 2),
        "usd_per_1000": round(1000 * sum(r["cost"] for r in rows) / len(rows), 3),
    }


def print_table(summaries: list[dict]):
    """Print summaries as a pipe-separated table."""
    print(" | ".join(summaries[0]))
    for summary in summaries:
        print(" | ".join(str(v) for v in summary.values()))


def grounded_answer(case: dict) -> dict:
    """The expected step 2b answer of one invoice case: decision, identifiers, and the item and value pair that disagree."""
    grounding = case["grounding"] or {}
    return {
        "decision": case["decision"],
        "invoice_number": case["invoice"]["invoice_number"],
        "po_number": case["invoice"]["po_number"],
        "item": grounding.get("item"),
        "invoiced": grounding.get("invoice_value"),
        "expected": grounding.get("reference_value"),
    }


def same_value(predicted, gold) -> bool:
    """Compare two field values: numbers numerically, strings ignoring case and outer whitespace, null only with null."""
    if gold is None or predicted is None:
        return gold is None and predicted is None
    if isinstance(gold, (int, float)) and not isinstance(gold, bool):
        try:
            return abs(float(str(predicted).replace(",", "")) - gold) < 0.005
        except ValueError:
            return False
    return str(predicted).strip().casefold() == str(gold).strip().casefold()


def score_answer(predicted: dict, gold: dict, fields: list[str]) -> dict:
    """Return per-field matches plus 'all'."""
    checks = {field: same_value(predicted.get(field), gold.get(field)) for field in fields}
    checks["all"] = all(checks.values())
    return checks
