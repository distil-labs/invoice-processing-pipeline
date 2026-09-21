"""Jev, TypeSafe AI's System One model, through the Vercel AI Gateway."""

import os
from dataclasses import dataclass
from typing import Any, Mapping

from app.retry import post_with_retry

GATEWAY_URL = "https://ai-gateway.vercel.sh/v1/evaluate"
JEV_MODEL = "typesafe-ai/jev"
REQUEST_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class ChoiceQuestion:
    """Pick one option; criteria maps each option to its definition."""

    instructions: str
    criteria: Mapping[str, str]

    def to_payload(self) -> dict:
        return {"type": "choice", "instructions": self.instructions, "criteria": dict(self.criteria)}


@dataclass(frozen=True)
class BooleanQuestion:
    """A statement Jev answers with the probability that it is true."""

    instructions: str

    def to_payload(self) -> dict:
        return {"type": "boolean", "instructions": self.instructions}


@dataclass(frozen=True)
class JevResponse:
    """Jev's answers to the questions of one request."""

    answers: Mapping[str, Mapping[str, Any]]
    latency_seconds: float
    cost_usd: float

    def choice(self, question: str) -> str:
        return self.answers[question]["choice"]

    def confidence(self, question: str) -> float | None:
        return self.answers[question].get("confidence")

    def probability(self, question: str) -> float:
        return self.answers[question]["probability"]

    def is_true(self, question: str, threshold: float = 0.5) -> bool:
        return self.probability(question) >= threshold


@dataclass(frozen=True)
class JevClient:
    """Asks Jev typed questions about a piece of text."""

    api_key: str
    url: str = GATEWAY_URL
    model: str = JEV_MODEL

    @classmethod
    def from_env(cls) -> "JevClient":
        """Read the Vercel AI Gateway key from VERCEL_API_KEY."""
        api_key = os.environ.get("VERCEL_API_KEY")
        if not api_key:
            raise RuntimeError("Set VERCEL_API_KEY to a Vercel AI Gateway key to call Jev. See .env.example.")
        return cls(api_key=api_key)

    def evaluate(self, state: str, questions: Mapping[str, ChoiceQuestion | BooleanQuestion]) -> JevResponse:
        """Ask all questions about one state in a single request."""
        payload = {"model": self.model, "state": state, "questions": {name: question.to_payload() for name, question in questions.items()}}
        response, latency_seconds = post_with_retry(self.url, {"Authorization": f"Bearer {self.api_key}"}, payload, REQUEST_TIMEOUT_SECONDS)
        body = response.json()
        return JevResponse(answers=body["answers"], latency_seconds=latency_seconds,
                           cost_usd=float(body["providerMetadata"]["gateway"]["marketCost"]))
