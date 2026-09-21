"""The fine-tuned models: system prompts come from training/, endpoints come from environment variables."""

import json
import os
import re
import time
from pathlib import Path

from openai import OpenAI

REPO_DIR = Path(__file__).parent.parent
# name -> environment variable prefix and whether the model was trained to reason before answering
MODELS = {
    "triage": {"env": "TRIAGE", "thinking": False},
    "decider": {"env": "DECIDER", "thinking": True},
    "grounded": {"env": "GROUNDED", "thinking": True},
}


def system_prompt(name: str) -> str:
    """Return the prompt a model was trained with: the task description of its training job."""
    job = json.loads((REPO_DIR / "training" / name / "job_description.json").read_text())
    return job["task_description"]


def triage_labels() -> dict[str, str]:
    """Parse the triage label definitions out of the triage prompt."""
    return dict(re.findall(r"^- (\w+): (.+)$", system_prompt("triage"), flags=re.M))


def read_answer(content: str) -> dict:
    """Parse the JSON object in a model answer; return {} when there is none."""
    match = re.search(r"\{.*\}", content or "", flags=re.S)
    try:
        answer = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        answer = {}
    return answer if isinstance(answer, dict) else {}


class SlmClient:
    """One fine-tuned model behind an OpenAI-compatible endpoint (llama.cpp, vLLM, or a distil labs deployment)."""

    def __init__(self, name: str):
        prefix = MODELS[name]["env"]
        base_url = os.environ.get(f"{prefix}_BASE_URL")
        if not base_url:
            raise RuntimeError(f"Set {prefix}_BASE_URL (and {prefix}_API_KEY if the server needs one). See .env.example.")
        self.thinking = MODELS[name]["thinking"]
        self.model = os.environ.get(f"{prefix}_MODEL", "model")
        self.system = system_prompt(name)
        self.client = OpenAI(base_url=base_url.rstrip("/"), api_key=os.environ.get(f"{prefix}_API_KEY", "EMPTY"))

    def ask(self, text: str) -> dict:
        """Send one input with the training-time setup: trained system prompt, temperature 0, trained thinking mode."""
        start = time.time()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": self.system}, {"role": "user", "content": text}],
            temperature=0,
            extra_body={"chat_template_kwargs": {"enable_thinking": self.thinking}},
        )
        latency = time.time() - start
        message = response.choices[0].message
        reasoning = getattr(message, "reasoning_content", None) or ""
        content = message.content or ""
        if "</think>" in content:
            reasoning, content = content.rsplit("</think>", 1)
        return {"answer": read_answer(content), "raw": content.strip(), "reasoning": reasoning.strip(),
                "latency": latency, "output_tokens": response.usage.completion_tokens if response.usage else None}
