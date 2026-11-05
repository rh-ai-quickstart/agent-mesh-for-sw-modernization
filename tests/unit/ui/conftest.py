from __future__ import annotations

import sys
from pathlib import Path

import pytest

UI_DIR = Path(__file__).resolve().parents[3] / "ui"
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))

CU_DIR = Path(__file__).resolve().parents[3] / "workflows" / "examples" / "code_understanding"
if str(CU_DIR) not in sys.path:
    sys.path.insert(0, str(CU_DIR))

pytest.importorskip("fastapi")
pytest.importorskip("kubernetes")
