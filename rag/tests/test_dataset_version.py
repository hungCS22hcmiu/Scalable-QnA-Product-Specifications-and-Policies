"""DATASET_VERSION comes from the environment, and the default does not move (item 3.6).

Each case runs in its own interpreter: config reads the variable once, at import, and a reload in
this process would leak into every other test.
"""

import os
import subprocess
import sys


def _version(**env: str) -> str:
    base = {k: v for k, v in os.environ.items() if k != "DATASET_VERSION"}
    out = subprocess.run(
        [sys.executable, "-c", "from rag import config; print(config.DATASET_VERSION)"],
        env=base | env,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def test_unset_gives_dev_v0():
    assert _version() == "dev-v0"


def test_environment_gives_v1():
    assert _version(DATASET_VERSION="v1") == "v1"


def test_empty_counts_as_unset():
    # "" would make ingest read data/ itself, and every *.json under it.
    assert _version(DATASET_VERSION="") == "dev-v0"
