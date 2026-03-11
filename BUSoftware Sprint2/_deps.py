import sys
from pathlib import Path

DEPS_DIR = Path(__file__).resolve().parent / ".deps"
if DEPS_DIR.exists():
    sys.path.insert(0, str(DEPS_DIR))
