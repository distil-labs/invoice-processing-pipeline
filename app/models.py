"""The fine-tuned models, served behind any OpenAI-compatible endpoint (llama.cpp, vLLM, a distil labs deployment)."""

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from openai import OpenAI

TRAINING_DIR = Path(__file__).parent.parent / "training"
END_OF_REASONING = "</think>"


@dataclass(frozen=True)
class ModelSpec:
    """What the pipeline knows about one fine-tuned model."""

    name: str
    env_prefix: str
    reasons_before_answering: bool

    @property
    def system_prompt(self) -> str:
        """The prompt the model was trained with: the task description of its training job."""
        job_description = json.loads((TRAINING_DIR / self.name / "job_description.json").read_text())
        return job_description["task_description"]


TRIAGE = ModelSpec(name="triage", env_prefix="TRIAGE", reasons_before_answering=False)
DECIDER = ModelSpec(name="decider", env_prefix="DECIDER", reasons_before_answering=True)
GROUNDED = ModelSpec(name="grounded", env_prefix="GROUNDED", reasons_before_answering=True)


@dataclass(frozen=True)
class Endpoint:
    """Where a model is served."""

    base_url: str
    api_key: str = "EMPTY"
    served_model_name: str = "model"

    @classmethod
    def from_env(cls, env_prefix: str) -> "Endpoint":
        """Read <PREFIX>_BASE_URL, <PREFIX>_API_KEY and <PREFIX>_MODEL."""
        base_url = os.environ.get(f"{env_prefix}_BASE_URL")
        if not base_url:
            raise RuntimeError(f"Set {env_prefix}_BASE_URL (and {env_prefix}_API_KEY if the server needs one). See .env.example.")
        return cls(
            base_url=base_url.rstrip("/"),
            api_key=os.environ.get(f"{env_prefix}_API_KEY", "EMPTY"),
            served_model_name=os.environ.get(f"{env_prefix}_MODEL", "model"),
        )


@dataclass(frozen=True)
class ModelAnswer:
    """One answer of a fine-tuned model, split into its reasoning and its JSON answer."""

    fields: Mapping[str, Any]
    text: str
    reasoning: str
    latency_seconds: float
    output_tokens: int | None

    @classmethod
    def from_completion(cls, content: str, separate_reasoning: str, latency_seconds: float, output_tokens: int | None) -> "ModelAnswer":
        """Build an answer from a chat completion, whether the server returns the reasoning inline or separately."""
        reasoning, text = separate_reasoning, content
        if END_OF_REASONING in content:
            reasoning, text = content.rsplit(END_OF_REASONING, 1)
        return cls(fields=parse_json_object(text), text=text.strip(), reasoning=reasoning.strip(),
                   latency_seconds=latency_seconds, output_tokens=output_tokens)


@dataclass(frozen=True)
class FineTunedModel:
    """A fine-tuned model that is asked exactly the way it was trained: same system prompt, temperature 0, same thinking mode."""

    spec: ModelSpec
    endpoint: Endpoint
    client: OpenAI = field(repr=False, compare=False)

    @classmethod
    def from_env(cls, spec: ModelSpec) -> "FineTunedModel":
        """Connect to the endpoint configured in the environment for this model."""
        endpoint = Endpoint.from_env(spec.env_prefix)
        return cls(spec=spec, endpoint=endpoint, client=OpenAI(base_url=endpoint.base_url, api_key=endpoint.api_key))

    def ask(self, text: str) -> ModelAnswer:
        """Send one input and return the model's answer."""
        started = time.time()
        completion = self.client.chat.completions.create(
            model=self.endpoint.served_model_name,
            messages=[{"role": "system", "content": self.spec.system_prompt}, {"role": "user", "content": text}],
            temperature=0,
            extra_body={"chat_template_kwargs": {"enable_thinking": self.spec.reasons_before_answering}},
        )
        message = completion.choices[0].message
        return ModelAnswer.from_completion(
            content=message.content or "",
            separate_reasoning=getattr(message, "reasoning_content", None) or "",
            latency_seconds=time.time() - started,
            output_tokens=completion.usage.completion_tokens if completion.usage else None,
        )


def parse_json_object(text: str) -> dict:
    """Return the JSON object inside a text, or an empty dict when there is none."""
    match = re.search(r"\{.*\}", text or "", flags=re.S)
    try:
        parsed = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}
