"""Launch an explicitly declared participant command."""

from .contracts import HarnessMetadata, LaunchContext, ParticipantSelection

METADATA = HarnessMetadata(None, 'CLAUDE_CONFIG_DIR', '.claude', None)

CAPABILITIES = {"resume_session": False, "capacity_resumes": False}


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
