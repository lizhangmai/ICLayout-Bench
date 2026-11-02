"""Native model usage, token-based API cost calculation and duration records.

These measurements never replace the independent evaluator's usage provenance.
Input totals include cache reads and writes; reasoning is a subset of output.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

TOKEN_FIELDS = ("input_tokens", "uncached_input_tokens", "cached_input_tokens",
                "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")
RATES = ("input_per_million", "cache_read_per_million", "cache_write_per_million", "output_per_million")
PRICE_METADATA = ("currency", "source", "as_of", "prefer_reported_cost")


@dataclass
class UsageEvidence:
    requests: list[dict] = field(default_factory=list)
    reported_cost: float | None = None
    currency: str = "USD"
    api_seconds: float | None = None
    totals: dict | None = None


def number(value, *, integer=False):
    if type(value) not in ({int} if integer else {int, float}):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def timestamp(value):
    if type(value) in {int, float}:
        return value / 1000 if value > 100_000_000_000 else value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.timestamp() if parsed.tzinfo else None
        except ValueError:
            pass
    return None


def duration(start, end):
    start, end = timestamp(start), timestamp(end)
    return end - start if start is not None and end is not None and end >= start else None


def request_record(identifier, model, *, input_tokens=None, uncached=None, cached=None,
                   written=None, output=None, reasoning=None, seconds=None, started_at=None,
                   cost=None, currency="USD", source=None, scope="request"):
    values = dict(zip(TOKEN_FIELDS, (input_tokens, uncached, cached, written, output, reasoning)))
    values = {key: number(value, integer=True) for key, value in values.items()}
    parts = [values[k] for k in ("uncached_input_tokens", "cached_input_tokens", "cache_write_input_tokens")]
    if values["input_tokens"] is None and all(v is not None for v in parts):
        values["input_tokens"] = sum(parts)
    if values["uncached_input_tokens"] is None and all(values[k] is not None for k in
            ("input_tokens", "cached_input_tokens", "cache_write_input_tokens")):
        values["uncached_input_tokens"] = number(values["input_tokens"] - values["cached_input_tokens"]
                                                 - values["cache_write_input_tokens"], integer=True)
    if (values["input_tokens"] is not None and all(v is not None for v in parts)
            and sum(parts) != values["input_tokens"]):
        values["uncached_input_tokens"] = None
    if (values["reasoning_output_tokens"] is not None and values["output_tokens"] is not None
            and values["reasoning_output_tokens"] > values["output_tokens"]):
        values["reasoning_output_tokens"] = None
    return {"id": str(identifier), "model": model, **values, "elapsed_seconds": number(seconds),
            "started_at": timestamp(started_at), "cost": number(cost), "currency": currency,
            "cost_source": "provider" if number(cost) is not None else None,
            "source": source, "scope": scope}


def validate_pricing(pricing):
    if not isinstance(pricing, dict) or not pricing:
        raise ValueError("pricing must be a nonempty table")
    allowed = {*RATES, "currency", "source", "as_of", "aliases", "prefer_reported_cost",
               "long_context_threshold", "long_context", "off_peak", "peak_utc_hours",
               "off_peak_dates", "models"}
    if set(pricing) - allowed:
        raise ValueError("Unknown pricing fields: " + ", ".join(sorted(set(pricing) - allowed)))
    if not re.fullmatch(r"[A-Z]{3}", pricing.get("currency", "")):
        raise ValueError("pricing.currency must be a three-letter currency code")
    if not isinstance(pricing.get("source"), str) or not pricing["source"].startswith("https://"):
        raise ValueError("pricing.source must be an official HTTPS price reference")
    try:
        date.fromisoformat(str(pricing.get("as_of", "")))
    except ValueError as exc:
        raise ValueError("pricing.as_of must be an ISO date") from exc
    for key in RATES:
        if number(pricing.get(key)) is None:
            raise ValueError("pricing." + key + " must be a nonnegative finite rate")
    aliases = pricing.get("aliases", [])
    if not isinstance(aliases, list) or any(not isinstance(v, str) or not v for v in aliases):
        raise ValueError("pricing.aliases must be a list of model identifiers")
    if type(pricing.get("prefer_reported_cost", True)) is not bool:
        raise ValueError("pricing.prefer_reported_cost must be a boolean")
    if "long_context" in pricing and number(pricing.get("long_context_threshold"), integer=True) in {None, 0}:
        raise ValueError("long-context pricing needs a positive token threshold")
    for key in ("long_context", "off_peak"):
        if key in pricing:
            rates = pricing[key]
            if (not isinstance(rates, dict) or set(rates) != set(RATES)
                    or any(number(v) is None for v in rates.values())):
                raise ValueError("pricing." + key + " needs all four nonnegative rates")
    if "off_peak" in pricing:
        windows = pricing.get("peak_utc_hours")
        if (not isinstance(windows, list) or not windows
                or any(not isinstance(w, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d", w)
                       or w[:5] >= w[6:] for w in windows)):
            raise ValueError("off-peak pricing needs peak_utc_hours in HH:MM-HH:MM format")
        holidays = pricing.get("off_peak_dates", [])
        if not isinstance(holidays, list):
            raise ValueError("pricing.off_peak_dates must be a list of ISO dates")
        for value in holidays:
            date.fromisoformat(str(value))
    models = pricing.get("models", {})
    if not isinstance(models, dict) or any(not isinstance(k, str) or not k for k in models):
        raise ValueError("pricing.models must be a table keyed by model ID")
    for model, override in models.items():
        if not model or not isinstance(override, dict):
            raise ValueError("pricing.models needs named model tables")
        validate_pricing({**{k: pricing[k] for k in PRICE_METADATA if k in pricing}, **override})
    return pricing


def _calculate_token_cost(request, pricing, configured_model):
    """Multiply native token counts by explicit API rates; missing inputs stay unknown."""
    if not pricing:
        return None
    model = request.get("model") or configured_model
    if model in pricing.get("models", {}):
        rates = {**{k: pricing[k] for k in PRICE_METADATA if k in pricing}, **pricing["models"][model]}
    elif model == configured_model or model in pricing.get("aliases", []):
        rates = pricing
    else:
        return None
    if "long_context" in rates:
        if request.get("scope") != "request" or request.get("input_tokens") is None:
            return None
        if request["input_tokens"] > rates["long_context_threshold"]:
            rates = {**rates, **rates["long_context"]}
    if "off_peak" in rates:
        started = request.get("started_at")
        if started is None or request.get("scope") != "request":
            return None
        moment = datetime.fromtimestamp(started, UTC)
        clock = moment.strftime("%H:%M")
        peak = (moment.weekday() < 5 and moment.date().isoformat() not in
                {str(d) for d in rates.get("off_peak_dates", [])}
                and any(w[:5] <= clock < w[6:] for w in rates["peak_utc_hours"]))
        if not peak:
            rates = {**rates, **rates["off_peak"]}
    fields = ("uncached_input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens")
    if any(request.get(key) is None for key in fields):
        return None
    return sum(request[key] * rates[rate] for key, rate in zip(fields, RATES)) / 1_000_000


def _total(records, field):
    values = [value for record in records if (value := number(record.get(field))) is not None]
    return sum(values) if values else None


def summarize_usage(evidence, *, model, pricing=None, wall_seconds=None):
    """Price each unique call once; never infer missing usage from elapsed time."""
    unique = {}
    for request in evidence.requests:
        key = request["id"]
        previous = unique.get(key, {})
        unique[key] = {**previous, **{k: v for k, v in request.items() if v is not None}}
    requests = list(unique.values())
    currency = (pricing or {}).get("currency", "USD")
    use_reported = (number(evidence.reported_cost) is not None
                    and (pricing or {}).get("prefer_reported_cost", True))
    for request in requests:
        if use_reported:
            continue
        reported = number(request.get("cost"))
        if reported is not None and (pricing or {}).get("prefer_reported_cost", True):
            continue
        request["cost"] = _calculate_token_cost(request, pricing, model)
        request["currency"] = currency
        request["cost_source"] = "api_token_pricing" if request["cost"] is not None else None
    tokens = {key: _total(requests, key) for key in TOKEN_FIELDS}
    if evidence.totals is not None:
        tokens.update({key: measured for key, value in evidence.totals.items()
                       if key in TOKEN_FIELDS and (measured := number(value, integer=True)) is not None})
    seconds = number(evidence.api_seconds)
    if seconds is None:
        seconds = _total(requests, "elapsed_seconds")
    currencies = {r.get("currency") for r in requests if r.get("cost") is not None}
    cost = _total(requests, "cost") if len(currencies) == 1 else None
    source = {r.get("cost_source") for r in requests if r.get("cost") is not None}
    cost_source = next(iter(source)) if len(source) == 1 else "mixed" if source else None
    if use_reported:
        cost, currency, cost_source = evidence.reported_cost, evidence.currency, "harness_reported"
    elif len(currencies) == 1:
        currency = next(iter(currencies))
    return {"provenance": "participant_reported", "aggregation": "sum_known", "model": model, "requests": requests,
            "request_count": len(requests) if requests and all(r.get("scope") == "request" for r in requests) else None,
            "record_count": len(requests), "tokens": tokens, "api_seconds": seconds, "wall_seconds": number(wall_seconds),
            "cost": cost, "currency": currency, "cost_source": cost_source, "pricing": pricing,
            "coverage": {key: {"known": sum(r.get(key) is not None for r in requests),
                               "missing": sum(r.get(key) is None for r in requests)}
                         for key in (*TOKEN_FIELDS, "elapsed_seconds", "cost")}}


def combine_usage(components):
    """Include replaced attempts, retaining each attempt's frozen price basis."""
    parts = [value or {} for value in components]
    tokens = {key: _total([part.get("tokens") or {} for part in parts], key) for key in TOKEN_FIELDS}
    currencies = {p.get("currency") for p in parts if p.get("cost") is not None}
    seconds, wall = _total(parts, "api_seconds"), _total(parts, "wall_seconds")
    cost = _total(parts, "cost") if len(currencies) == 1 else None
    sources = {p.get("cost_source") for p in parts if p.get("cost") is not None}
    requests = [{**request, "id": f"attempt-{index}:{request['id']}"}
                for index, part in enumerate(parts) for request in part.get("requests", [])]
    return {**parts[-1], "aggregation": "sum_known", "tokens": tokens, "requests": requests,
            "request_count": _total(parts, "request_count"), "record_count": len(requests),
            "api_seconds": seconds, "wall_seconds": wall,
            "cost": cost, "currency": next(iter(currencies)) if len(currencies) == 1 else None,
            "cost_source": next(iter(sources)) if len(sources) == 1 else "mixed" if sources else None,
            "components": [{k: v for k, v in part.items() if k not in {"requests", "components"}} for part in parts],
            "coverage": {key: {name: sum((p.get("coverage") or {}).get(key, {}).get(name, 0) for p in parts)
                               for name in ("known", "missing")}
                         for key in (*TOKEN_FIELDS, "elapsed_seconds", "cost")},
            "missing_attempts": sum(not p for p in parts)}
