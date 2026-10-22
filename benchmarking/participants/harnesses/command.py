"""Launch an explicitly declared participant command."""

from benchmarking.participants.harnesses.contracts import (
    HarnessMetadata,
    LaunchContext,
    ParticipantSelection,
)
from benchmarking.participants.harnesses.records import records
from benchmarking.results.usage import UsageEvidence, request_record

METADATA = HarnessMetadata(None, 'CLAUDE_CONFIG_DIR', '.claude', None)

CAPABILITIES = {"resume_session": False, "capacity_resumes": False}


def usage(agent, native):
    evidence = UsageEvidence()
    for index, event in enumerate(records(agent)):
        if event.get("type") != "model.usage":
            continue
        value = event.get("usage") or {}
        evidence.requests.append(request_record(event.get("request_id", f"stdout:{index}"), event.get("model"),
            input_tokens=value.get("input_tokens"), uncached=value.get("uncached_input_tokens"),
            cached=value.get("cached_input_tokens"), written=value.get("cache_write_input_tokens"),
            output=value.get("output_tokens"), reasoning=value.get("reasoning_output_tokens"),
            seconds=event.get("elapsed_seconds"), started_at=event.get("started_at"), cost=value.get("cost"),
            currency=event.get("currency", "USD"), source="agent.jsonl"))
    return evidence


def resolve(model, effort, env):
    return ParticipantSelection({
        "harness": "command",
        "model": model,
        "effort_requested": effort,
        "effort_resolved": effort,
    }, env, {})


def prepare(context: LaunchContext) -> list[str]:
    settings = context.selection.settings
    return settings["launch"]["command"]
