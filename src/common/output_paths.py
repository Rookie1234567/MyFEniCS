from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast


def unique_run_dir(results_root: Path, base_name: str, enabled: bool = True) -> Path:
    if not enabled:
        return results_root

    results_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    index = 1
    while True:
        suffix = "" if index == 1 else f"_{index:02d}"
        candidate = results_root / f"{base_name}_{stamp}{suffix}"
        try:
            candidate.mkdir(exist_ok=False)
        except FileExistsError:
            index += 1
            continue
        return candidate


def shared_unique_run_dir(
    comm: Any,
    results_root: Path,
    base_name: str,
    enabled: bool = True,
) -> Path:
    """Atomically claim one rank-0 directory or broadcast the same failure."""

    payload: tuple[str | None, str | None, str | None] | None = None
    if comm.rank == 0:
        try:
            chosen = unique_run_dir(results_root, base_name, enabled=enabled)
        except Exception as error:
            payload = (None, type(error).__name__, str(error))
        else:
            payload = (str(chosen), None, None)
    chosen_text, error_type, error_message = comm.bcast(payload, root=0)
    if error_type is not None:
        raise RuntimeError(
            "rank 0 failed to claim shared run directory: "
            f"{error_type}: {error_message}"
        )
    return Path(cast(str, chosen_text))
