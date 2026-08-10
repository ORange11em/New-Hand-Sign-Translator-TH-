"""Export the verified HandVox architecture image into this test's output."""

from pathlib import Path
import shutil


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "qa" / "assets" / "handvox_architecture.png"
OUTPUT = HERE / "output" / "figure_3_1_handvox_architecture.png"


def main() -> int:
    if not SOURCE.exists():
        raise FileNotFoundError(f"ไม่พบภาพต้นฉบับ: {SOURCE}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, OUTPUT)
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

