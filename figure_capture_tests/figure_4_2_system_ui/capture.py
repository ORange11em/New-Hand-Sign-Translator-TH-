"""Capture the HandVox dashboard safely without opening the camera."""

from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUT = HERE / "output" / "figure_4_2_system_dashboard.png"
CAPTURE_TOOL = ROOT / "tools" / "capture_training_gui.py"


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(CAPTURE_TOOL), str(OUTPUT), "--page", "dashboard"]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        return completed.returncode
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

