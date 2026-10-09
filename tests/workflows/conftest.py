import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = REPO_ROOT / "workflows" / "examples" / "code_understanding"

sys.path.insert(0, str(WORKFLOW_ROOT))


@pytest.fixture(autouse=True)
def disable_telemetry(monkeypatch):
    telemetry_module = ModuleType("telemetry.default_custom_telemetry")

    class NoopTelemetry:
        def track(self):
            return None

    telemetry_module.DefaultCustomTelemetry = NoopTelemetry
    monkeypatch.setitem(
        sys.modules,
        "telemetry.default_custom_telemetry",
        telemetry_module,
    )
