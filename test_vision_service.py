"""
Robustness test for vision_service.diagnose().

Usage:
    python test_vision_service.py path/to/image.jpg
    python test_vision_service.py path/to/image.jpg "Species Name"
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# add backend/ to path so vision_service is importable
sys.path.insert(0, str(Path(__file__).parent / "backend"))
from vision_service import diagnose  # noqa: E402


def run_single(image_path: str, species: str | None) -> None:
    print(f"\n{'-'*60}")
    print(f"  Image   : {image_path}")
    print(f"  Species : {species or '(not provided)'}")
    result = diagnose(image_path, known_species=species)
    print(f"\n  Result:")
    print(json.dumps(result, indent=4))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_vision_service.py <path/to/image.jpg> [species]")
        sys.exit(1)

    img = sys.argv[1]
    if not Path(img).exists():
        print(f"ERROR: file not found: {img}")
        sys.exit(1)

    sp = sys.argv[2] if len(sys.argv) > 2 else None
    run_single(img, sp)
