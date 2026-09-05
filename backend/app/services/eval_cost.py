from __future__ import annotations

import threading

from app.db import db

# Fallback Gemini 2.5 Flash pricing (USD per 1K tokens) used if the cost
# lookup table is missing a row for a model.
_DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.0003, "output": 0.0025, "thinking": 0.0035},
    # USD per 1K tokens. 3.6 Flash: $1.50 / $7.50 per 1M; thinking billed as output.
    "gemini-3.6-flash": {"input": 0.0015, "output": 0.0075, "thinking": 0.0075},
}

_lock = threading.Lock()
_price_cache: dict[str, dict[str, float]] = {}


def _load_prices() -> dict[str, dict[str, float]]:
    prices: dict[str, dict[str, float]] = {}
    try:
        rows = (
            db()
            .table("pc_evaluation_cost_lookup")
            .select("model, input_price, output_price, thinking_price")
            .execute()
            .data
            or []
        )
    except Exception:  # noqa: BLE001
        rows = []
    for r in rows:
        model = r.get("model")
        if not model:
            continue
        prices[model] = {
            "input": float(r.get("input_price") or 0),
            "output": float(r.get("output_price") or 0),
            "thinking": float(r.get("thinking_price") or 0),
        }
    return prices


def _prices_for(model: str) -> dict[str, float]:
    with _lock:
        if not _price_cache:
            _price_cache.update(_load_prices())
        prices = _price_cache.get(model) or _DEFAULT_PRICES.get(model)
        if prices is None:
            # Unknown model has no lookup row — treat as $0 rather than fail the run.
            return {"input": 0.0, "output": 0.0, "thinking": 0.0}
        return prices


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int,
) -> float:
    """Compute the USD cost of one evaluation using lookup prices (per 1K tokens)."""
    in_tok = max(0, int(input_tokens or 0))
    out_tok = max(0, int(output_tokens or 0))
    think_tok = max(0, int(thinking_tokens or 0))
    prices = _prices_for(model)
    return (
        (in_tok / 1000.0) * prices["input"]
        + (out_tok / 1000.0) * prices["output"]
        + (think_tok / 1000.0) * prices["thinking"]
    )


def summarize_cost(eval_rows: list[dict]) -> dict[str, object]:
    """Aggregate token and USD cost totals from pc_evaluations rows.

    Uses the stored ``estimated_cost_usd`` when present, otherwise derives it
    from the model's lookup prices so old rows still produce accurate totals.
    """
    per: dict[str, dict[str, object]] = {}
    totals: dict[str, object] = {
        "total_evaluations": len(eval_rows),
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_thinking_tokens": 0,
        "estimated_cost_usd": 0.0,
        "per_model": per,
    }
    for e in eval_rows or []:
        model = e.get("model") or "unknown"
        m = per.setdefault(
            model,
            {
                "evaluations": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "thinking_tokens": 0,
                "cost_usd": 0.0,
            },
        )
        inp = e.get("input_tokens") or 0
        out = e.get("output_tokens") or 0
        think = e.get("thinking_tokens") or 0
        cost = float(e.get("estimated_cost_usd") or 0) or estimate_cost_usd(model, inp, out, think)
        m["evaluations"] = int(m["evaluations"]) + 1
        m["input_tokens"] = int(m["input_tokens"]) + inp
        m["output_tokens"] = int(m["output_tokens"]) + out
        m["thinking_tokens"] = int(m["thinking_tokens"]) + think
        m["cost_usd"] = float(m["cost_usd"]) + cost
        totals["total_input_tokens"] = int(totals["total_input_tokens"]) + inp
        totals["total_output_tokens"] = int(totals["total_output_tokens"]) + out
        totals["total_thinking_tokens"] = int(totals["total_thinking_tokens"]) + think
        totals["estimated_cost_usd"] = float(totals["estimated_cost_usd"]) + cost

    totals["estimated_cost_usd"] = round(float(totals["estimated_cost_usd"]), 6)
    for _, m_per in per.items():
        m_per["cost_usd"] = round(float(m_per["cost_usd"]), 6)
    return totals