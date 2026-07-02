"""Validate CLI: python -m templates.declarative <file.json> (ADR-007)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUVAT_JSON = ROOT / "templates" / "data" / "suvat.json"
VPY = ROOT / ".venv" / "bin" / "python"


def _run(path):
    exe = str(VPY) if VPY.exists() else sys.executable
    return subprocess.run([exe, "-m", "templates.declarative", str(path)],
                          cwd=ROOT, capture_output=True, text=True)


def test_cli_validates_suvat_json():
    r = _run(SUVAT_JSON)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "stage 5" in r.stdout.lower()
    assert "pass" in r.stdout.lower()
