from __future__ import annotations

import sys
from pathlib import Path

import pytest

UI_DIR = Path(__file__).resolve().parents[1]
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))

pytest.importorskip("fastapi")
pytest.importorskip("kubernetes")
