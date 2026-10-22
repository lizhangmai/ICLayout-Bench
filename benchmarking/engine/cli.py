"""Compatibility command routing to evaluation and execution diagnostics."""
import sys


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] in {"recover", "inference-check"}:
        from benchmarking.execution.cli import main as command
    else:
        from benchmarking.evaluation.cli import main as command
    return command(arguments)

if __name__ == "__main__":
    main()
