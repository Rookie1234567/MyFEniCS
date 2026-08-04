"""Launch the locked Task006 blind12 x three-angle campaign."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from surrogate.task006.blind_runner import run  # noqa: E402


def main() -> int:
    result = run()
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
