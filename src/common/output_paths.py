from __future__ import annotations

from datetime import datetime
from pathlib import Path


def unique_run_dir(results_root: Path, base_name: str, enabled: bool = True) -> Path:
    if not enabled:
        return results_root

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = results_root / f"{base_name}_{stamp}"
    if not candidate.exists():
        return candidate

    index = 2
    while True:
        numbered = results_root / f"{base_name}_{stamp}_{index:02d}"
        if not numbered.exists():
            return numbered
        index += 1
