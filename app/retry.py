"""HTTP POST that survives rate limits and transient server errors."""

import time

import requests

RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)
MAX_ATTEMPTS = 5


def post_with_retry(url: str, headers: dict, payload: dict, timeout_seconds: int) -> tuple[requests.Response, float]:
    """POST and retry with exponential backoff; return the response and the latency of the successful attempt."""
    for attempt in range(MAX_ATTEMPTS):
        started = time.time()
        response = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
        latency_seconds = time.time() - started
        if response.status_code not in RETRYABLE_STATUS_CODES:
            break
        time.sleep(2 ** attempt)
    response.raise_for_status()
    return response, latency_seconds
