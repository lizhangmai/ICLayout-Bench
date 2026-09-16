"""Compatibility wrapper; prefer python -m layout_eval.preview."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from layout_eval.preview import main

if __name__ == "__main__":
    main()
