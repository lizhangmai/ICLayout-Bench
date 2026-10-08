"""Run a single participant condition or a TOML experiment matrix."""


def main(argv=None):
    from benchmarking.participants.cli import main as run

    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
