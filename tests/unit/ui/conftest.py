from __future__ import annotations

import sys
from pathlib import Path

UI_DIR = Path(__file__).resolve().parents[3] / "ui"
if str(UI_DIR) not in sys.path:
    sys.path.insert(0, str(UI_DIR))
