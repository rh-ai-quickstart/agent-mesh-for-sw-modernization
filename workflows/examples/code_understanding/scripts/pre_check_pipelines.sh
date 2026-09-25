#!/usr/bin/env bash
# Exits 0 (skip) if pipelines are already uploaded to KFP, 1 (proceed) otherwise.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODE_UNDERSTANDING_DIR="$(dirname "$SCRIPT_DIR")"

PYTHONPATH="$CODE_UNDERSTANDING_DIR:${PYTHONPATH:-}" python3 - <<'PYEOF'
import sys
from services.check_pipeline import is_pipeline_uploaded
if is_pipeline_uploaded("single_repo"):
    print("Pipelines already uploaded, skipping.")
    sys.exit(0)
sys.exit(1)
PYEOF
