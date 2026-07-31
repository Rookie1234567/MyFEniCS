from __future__ import annotations

import json

from mpi4py import MPI

from ..common.config import SimulationConfig, project_root
from ..common.output_paths import shared_unique_run_dir
from ..solvers.solve_vector_maxwell import _json_default, run_case


def main() -> None:
    root = project_root()
    cfg = SimulationConfig(case_name="air_substrate_grating_manual")
    out_dir = shared_unique_run_dir(
        MPI.COMM_WORLD,
        root / "results",
        cfg.case_name,
    )
    summary = run_case(
        cfg,
        out_dir,
        constraint_backend="manual",
    )
    if MPI.COMM_WORLD.rank == 0:
        (out_dir / "manual_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
