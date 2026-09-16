"""Participant and local evaluation entry point."""

import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] in {"client", "harness", "analyze"}:
        from benchmarking import analyze, client, official
        command = sys.argv.pop(1)
        return {"client": client.main, "harness": official.main, "analyze": analyze.main}[command]()
    from layout_eval.cli import main as evaluate
    return evaluate()


if __name__ == "__main__":
    raise SystemExit(main())
