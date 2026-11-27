"""Chat calls to an OpenAI-compatible provider (DeepSeek unless the settings say otherwise), with a price table, a cost
ledger and spending caps. The service reads its provider from the environment (`provider_from_env`)."""

import json
import math
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"  # decision of 0d: thinking off
DEFAULT_THINKING_OFF = {"thinking": {"type": "disabled"}}
LEDGER = Path("data/llm_ledger.jsonl")


@dataclass(frozen=True)
class Price:
    """Per 1M tokens as listed, in `currency`. `off_peak` is the share of the listed price paid outside the peak
    hours: DeepSeek direct lists the peak price and halves it off peak; a flat price has 1.0."""

    currency: str
    cached: float
    input: float
    output: float
    off_peak: float = 1.0


PRICES = {
    # Snapshot of https://api-docs.deepseek.com/quick_start/pricing, read 2026-10-27.
    "deepseek-flash": Price("USD", 0.006, 0.30, 1.20, off_peak=0.5),
    "deepseek-v4-pro": Price("USD", 0.044, 1.32, 3.96, off_peak=0.5),
    # Scaleway Generative APIs (Paris), pricing page as seen by the user on 2026-11-27.
    "deepseek-v4.1-flash-1017": Price("EUR", 0.12, 0.60, 1.80),
}
# Costs, traces and spending caps are all counted in USD. Snapshot, 2026-11-27: the ECB chart showed about 1.12 on
# 2026-11-26; rounded up so that the caps over-count a euro price rather than under-count it.
USD_PER = {"USD": 1.0, "EUR": 1.20}
PEAK_HOURS_UTC = (1, 2, 3, 6, 7, 8, 9)

# Upper bound for the pre-call estimate; the pilot compares it with the billed prompt_tokens.
TOKENS_PER_CHAR = 0.5


class BudgetExceeded(Exception):
    pass


@dataclass
class Budget:
    """reserved is the worst case of the calls in flight, so parallel calls cannot overshoot a cap."""

    run_cap: float
    total_cap: float
    spent: float = 0.0
    reserved: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


def is_peak(when: datetime) -> bool:
    # Chinese public holidays are off-peak too; not modelled, so the cost is over-estimated then.
    return when.astimezone(UTC).weekday() < 5 and when.astimezone(UTC).hour in PEAK_HOURS_UTC


def price_of(model: str) -> Price:
    """The caps count in these prices, so a model without a row is refused, not run at zero cost."""
    if model not in PRICES:
        raise ValueError(f"no price for model {model!r}: add a row to llm.PRICES")
    return PRICES[model]


def cost_usd(model: str, hit: int, miss: int, output: int, when: datetime) -> float:
    price = price_of(model)
    share = 1.0 if is_peak(when) else price.off_peak
    return USD_PER[price.currency] * share * (hit * price.cached + miss * price.input + output * price.output) / 1e6


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) * TOKENS_PER_CHAR)


def worst_case_cost(model: str, prompt_tokens: int, max_tokens: int) -> float:
    """Peak price, every input token a cache miss, the whole `max_tokens` generated."""
    price = price_of(model)
    return USD_PER[price.currency] * (prompt_tokens * price.input + max_tokens * price.output) / 1e6


def read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_ledger(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ledger_total(path: Path) -> float:
    return sum(e["cost_usd"] for e in read_ledger(path) if e["type"] == "call")


def ensure_within_budget(budget: Budget, ledger_spent: float, worst_case: float) -> None:
    in_flight = budget.reserved
    if budget.spent + in_flight + worst_case > budget.run_cap:
        raise BudgetExceeded(
            f"run cap {budget.run_cap}: spent {budget.spent:.4f} + in flight {in_flight:.4f}"
            f" + worst case {worst_case:.4f}"
        )
    if ledger_spent + in_flight + worst_case > budget.total_cap:
        raise BudgetExceeded(
            f"total cap {budget.total_cap}: spent {ledger_spent:.4f} + in flight {in_flight:.4f}"
            f" + worst case {worst_case:.4f}"
        )


@dataclass(frozen=True)
class Provider:
    base_url: str
    model: str
    api_key: str
    thinking_off: dict  # extra request fields that switch thinking off; the form differs by provider, {} when none

    @property
    def host(self) -> str:
        return urlparse(self.base_url).hostname or ""


def provider_from_env(environ) -> Provider:
    """The provider of the service. LLM_BASE_URL, LLM_MODEL, LLM_API_KEY (else DEEPSEEK_API_KEY) and LLM_THINKING_OFF (a
    JSON object, {} for none); an empty value means the default, which is DeepSeek as before. Fails at start, never
    on a request: no key, no price for the model, a base URL that is not https, a thinking field that is not an object."""
    api_key = environ.get("LLM_API_KEY") or environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY (or DEEPSEEK_API_KEY) is not set")
    model = environ.get("LLM_MODEL") or DEFAULT_MODEL
    price_of(model)
    base_url = (environ.get("LLM_BASE_URL") or BASE_URL).rstrip("/")
    if not base_url.startswith("https://"):
        raise ValueError(f"LLM_BASE_URL must start with https:// (the key travels in it): {base_url!r}")
    raw = environ.get("LLM_THINKING_OFF")
    thinking_off = json.loads(raw) if raw else DEFAULT_THINKING_OFF
    if not isinstance(thinking_off, dict):
        raise TypeError("LLM_THINKING_OFF must be a JSON object, for example {} for none")
    return Provider(base_url, model, api_key, thinking_off)


def make_http(api_key: str, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=300,  # a thinking call at effort low took up to a minute
        transport=transport,
    )


def chat(
    http: httpx.Client,
    ledger: Path,
    budget: Budget,
    label: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    thinking: bool = False,
    json_mode: bool = True,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
) -> str:
    """One call, never retried. Raises BudgetExceeded before sending if the worst case does not fit.
    Safe to call from several threads sharing one Budget."""
    prompt_tokens = estimate_tokens("".join(m["content"] for m in messages))
    worst = worst_case_cost(model, prompt_tokens, max_tokens)
    with budget.lock:
        ensure_within_budget(budget, ledger_total(ledger), worst)
        budget.reserved += worst
    try:
        data = _post(http, model, messages, max_tokens, thinking, json_mode, temperature, reasoning_effort)
    finally:
        with budget.lock:
            budget.reserved -= worst

    usage = data["usage"]
    now = datetime.now(UTC)
    cost = cost_usd(
        model,
        usage["prompt_cache_hit_tokens"],
        usage["prompt_cache_miss_tokens"],
        usage["completion_tokens"],
        now,
    )
    # Written before the content is checked: an empty answer is still billed.
    with budget.lock:
        budget.spent += cost
        append_ledger(
            ledger,
            {
                "type": "call",
                "time": now.isoformat(timespec="seconds"),
                "label": label,
                "model": model,
                "estimated_prompt_tokens": prompt_tokens,
                "prompt_tokens": usage["prompt_tokens"],
                "cache_hit_tokens": usage["prompt_cache_hit_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens"),
                "cost_usd": cost,
                "request_id": data.get("id"),
            },
        )
    content = data["choices"][0]["message"]["content"]
    if not content or not content.strip():
        raise ValueError(f"empty answer from {model} (billed {cost:.6f} USD)")
    return content


def _post(http, model, messages, max_tokens, thinking, json_mode, temperature, reasoning_effort) -> dict:
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "thinking": {"type": "enabled" if thinking else "disabled"},
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if temperature is not None:  # ignored by the API when thinking is on
        body["temperature"] = temperature
    if reasoning_effort is not None:  # low, high or max; the docs tie it to thinking mode
        body["reasoning_effort"] = reasoning_effort
    response = http.post("/chat/completions", json=body)
    response.raise_for_status()
    return response.json()


def balance(http: httpx.Client) -> dict[str, float]:
    response = http.get("/user/balance")
    response.raise_for_status()
    return {b["currency"]: float(b["total_balance"]) for b in response.json()["balance_infos"]}


def record_balance(ledger: Path, balances: dict[str, float], label: str) -> None:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    append_ledger(ledger, {"type": "balance", "time": now, "label": label, "balances": balances})


def reconcile(ledger: Path) -> dict | None:
    """Estimated cost of the calls between the last two balance snapshots, against the balance drop."""
    entries = read_ledger(ledger)
    snapshots = [i for i, e in enumerate(entries) if e["type"] == "balance"]
    if len(snapshots) < 2:
        return None
    first, last = snapshots[-2], snapshots[-1]
    calls = [e for e in entries[first:last] if e["type"] == "call"]
    estimated = sum(e["cost_usd"] for e in calls)
    before, after = entries[first]["balances"], entries[last]["balances"]
    drop = {c: before[c] - after[c] for c in before}
    return {"calls": len(calls), "estimated_usd": estimated, "balance_drop": drop}
