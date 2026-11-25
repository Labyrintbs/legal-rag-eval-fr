"""The call of a model judge that answers in json: format the prompt, make one call, parse the reply into a Pydantic shape."""

import httpx
from pydantic import BaseModel, ValidationError

from legalrag import llm


def lowercase(value):
    """For `field_validator("label", mode="before")` of a judge's verdict: the model may answer "Addresses"."""
    return value.strip().lower() if isinstance(value, str) else value


def chat_messages(prompt: dict, **fields: str) -> list[dict]:
    return [{"role": "system", "content": prompt["system"].strip()}, {"role": "user", "content": prompt["user"].format(**fields)}]


def ask(http: httpx.Client, budget: llm.Budget, label: str, model: str, messages: list[dict], max_tokens: int,
        shape: type[BaseModel]) -> dict:
    """One call, no retry: {"value": the parsed reply} or {"error": ...}. The call is in the ledger under `label`."""
    try:
        text = llm.chat(http, llm.LEDGER, budget, label, model, messages, max_tokens, json_mode=True, temperature=0)
        return {"value": shape.model_validate_json(text)}
    except (ValidationError, ValueError, KeyError, httpx.HTTPError, llm.BudgetExceeded) as error:
        return {"error": f"{type(error).__name__}: {error}"}
