"""Inspect inference configuration or recover committed workspace submissions."""
import argparse
import json
import os
from pathlib import Path

from benchmarking.evidence.journal import recover_submissions
from benchmarking.execution.inference import (
    load_inference_config,
    validate_harness_wire,
)
from benchmarking.execution.workspace.config import load_run_config


def _inference_preflight(profile, config, credential_present):
    """Describe a model profile without making a provider request."""
    return {
        "status": "ready" if credential_present else "missing_credential",
        "model_call": False,
        "endpoint": profile.base_url,
        "model": profile.model,
        "wire_api": profile.wire_api,
        "credential_env": profile.api_key_env,
        "credential_present": credential_present,
        "harness": config.harness.identity() if config else None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    recover = commands.add_parser("recover", help="Read committed submissions without resuming a solve")
    recover.add_argument("directory")
    inference = commands.add_parser("inference-check", help="Validate a profile without making a model call")
    inference.add_argument("profile", type=Path)
    inference.add_argument("--agent", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "recover":
            print(json.dumps(recover_submissions(args.directory), indent=2, allow_nan=False))
            return
        profile = load_inference_config(args.profile)
        config = load_run_config(args.agent) if args.agent else None
        if config:
            validate_harness_wire(config.harness.wire_api, profile.wire_api)
        result = _inference_preflight(profile, config, bool(os.environ.get(profile.api_key_env)))
        print(json.dumps(result, indent=2, allow_nan=False))
        if not result["credential_present"]:
            parser.exit(1)
    except (TypeError, ValueError, OSError) as error:
        parser.exit(2, f"ICLayout-Bench command failed: {error}\n")

if __name__ == "__main__":
    main()
