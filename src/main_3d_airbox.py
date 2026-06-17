from __future__ import annotations

import sys
from pathlib import Path


# PyCharm direct-run entry for stage-1 3D Maxwell air-box verification.
#
# Keep src/main.py for the existing 2D grating workflow.  Run this file when
# learning or debugging the new 3D path.

USE_PYCHARM_SETTINGS_WHEN_NO_ARGS = True

AIRBOX3D_CASE = "both"  # "normal", "oblique", or "both"
NEDELEC_DEGREE = 2
VISUALIZATION_DEGREE = 2
MESH_TARGET_SIZE = 0.14
LAMBDA0 = None
UNIQUE_OUTPUT = True


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_package_importable() -> None:
    root = str(_workspace_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _add_value(args: list[str], flag: str, value: object | None) -> None:
    if value is not None:
        args.extend([flag, str(value)])


def _add_bool(args: list[str], positive_flag: str, value: bool | None) -> None:
    if value is None:
        return
    args.append(positive_flag if value else "--no-" + positive_flag.removeprefix("--"))


def _pycharm_args() -> list[str]:
    args = ["--case", AIRBOX3D_CASE]
    _add_value(args, "--nedelec-degree", NEDELEC_DEGREE)
    _add_value(args, "--visualization-degree", VISUALIZATION_DEGREE)
    _add_value(args, "--mesh-target-size", MESH_TARGET_SIZE)
    _add_value(args, "--lambda0", LAMBDA0)
    _add_bool(args, "--unique-output", UNIQUE_OUTPUT)
    return args


def main() -> None:
    _ensure_package_importable()
    from fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox import (
        main as run_3d_airbox_main,
    )

    if USE_PYCHARM_SETTINGS_WHEN_NO_ARGS and len(sys.argv) == 1:
        run_3d_airbox_main(_pycharm_args())
    else:
        run_3d_airbox_main()


if __name__ == "__main__":
    main()
