import sys
from pathlib import Path

# experiments/scripts/ is a directory of runnable scripts, not an installed package (they are
# invoked as `python3 experiments/scripts/<name>.py` via the Makefile), so the import path is set
# here rather than by a pyproject entry.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
