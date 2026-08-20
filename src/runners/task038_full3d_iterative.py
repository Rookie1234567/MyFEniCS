"""T1 identity stub for the not-yet-connected Full3D iterative adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def run_full3d_iterative(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Expose the reviewed adapter identity without launching numerical code."""

    method = resolved_payload.get("method", {})
    if not isinstance(method, Mapping) or method.get("kind") != "full3d_iterative":
        raise ValueError("full3d_iterative adapter received a mismatched method")
    return {
        "passed": False,
        "errors": [
            "full3d_iterative numerical adapter is not connected in T1; "
            "T2-T5 qualification is required"
        ],
        "summary": None,
        "numerical_output_directory": str(Path(run_directory).resolve() / "numerical_output"),
    }


__all__ = ["run_full3d_iterative"]
