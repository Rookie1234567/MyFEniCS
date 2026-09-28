"""Frozen V29 p6/990-cell three-way H6 diagonal component qualification."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from time import perf_counter

import numpy as np
from mpi4py import MPI

from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.solvers.fullspace_metric_positive_diagonal import (
    build_reference_metric_positive_diagonal,
)
from src.solvers.fullspace_quadrature_diagonal import (
    build_quadrature_positive_diagonal,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
    _build_same_mesh_levels,
)


ROOT = Path(__file__).resolve().parents[2]
V29_INPUT = ROOT / "input/task39extra/v29_a4_tensor_h6_original_h7p5.dat"


def test_v29_original_p6_990_cell_diagonal_three_way():
    if MPI.COMM_WORLD.size != 1:
        raise AssertionError("this fixed p6 component qualification requires MPI1")
    input_sha256 = hashlib.sha256(V29_INPUT.read_bytes()).hexdigest()
    specification = load_and_resolve(V29_INPUT)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    assert specification.identity["run_id"] == (
        "task39extra_v29_a4_tensor_h6_original_h7p5_v1"
    )
    assert cfg.nedelec_degree == 6 and cfg.mesh_target_size == 7.5
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_WORLD, (6,), include_positive_coefficients=True
    )
    space = levels["spaces"][6]
    mpc = levels["floquets"][6].mpc
    mu, mass = levels["mu"], levels["mass"]
    cells = int(space.mesh.topology.index_map(space.mesh.topology.dim).size_local)
    assert cells == 990

    timing = {}
    vectors = []
    try:
        started = perf_counter()
        old = build_quadrature_positive_diagonal(space, mu, mass, mpc)
        timing["workstation_definition_reference_seconds"] = perf_counter() - started
        vectors.append(old)
        old_values = old.array.copy()
        print("L2 p6 old reference complete", timing, flush=True)

        started = perf_counter()
        v29_audit = {}
        v29 = build_quadrature_positive_diagonal(
            space,
            mu,
            mass,
            mpc,
            batched_target_grouping=True,
            reuse_local_types=True,
            audit=v29_audit,
        )
        timing["v29_optimized_diagonal_seconds"] = perf_counter() - started
        vectors.append(v29)
        v29_values = v29.array.copy()
        print("L2 p6 V29 diagonal complete", timing, flush=True)

        started = perf_counter()
        candidate_audit = {}
        candidate = build_reference_metric_positive_diagonal(
            space, mu, mass, mpc, audit=candidate_audit
        )
        timing["reference_metric_diagonal_seconds"] = perf_counter() - started
        vectors.append(candidate)
        candidate_values = candidate.array.copy()
        print("L2 p6 reference metric complete", timing, flush=True)

        difference_old = candidate_values - old_values
        difference_v29 = candidate_values - v29_values
        max_abs_old = float(np.max(np.abs(difference_old)))
        max_abs_v29 = float(np.max(np.abs(difference_v29)))
        rel_old = float(
            np.linalg.norm(difference_old)
            / max(np.linalg.norm(old_values), np.finfo(float).tiny)
        )
        rel_v29 = float(
            np.linalg.norm(difference_v29)
            / max(np.linalg.norm(v29_values), np.finfo(float).tiny)
        )
        source_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        tracked_diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD"], cwd=ROOT, check=True,
            capture_output=True,
        ).stdout
        record = {
            "schema": "task39extra.v30.l2.p6-diagonal-comparison.v1",
            "status": "MEASURED_BEFORE_ASSERTIONS",
            "source_head": source_head,
            "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
            "candidate_source_sha256": hashlib.sha256(
                (ROOT / "src/solvers/fullspace_metric_positive_diagonal.py").read_bytes()
            ).hexdigest(),
            "p6_test_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "run_id": specification.identity["run_id"],
            "input_path": V29_INPUT.relative_to(ROOT).as_posix(),
            "input_sha256": input_sha256,
            "mesh_cells": cells,
            "degree": 6,
            "mpi_size": MPI.COMM_WORLD.size,
            "timing_seconds": timing,
            "max_abs_candidate_vs_reference": max_abs_old,
            "max_abs_candidate_vs_v29": max_abs_v29,
            "relative_candidate_vs_reference": rel_old,
            "relative_candidate_vs_v29": rel_v29,
            "old_diagonal_sha256": hashlib.sha256(old_values.tobytes()).hexdigest(),
            "v29_diagonal_sha256": hashlib.sha256(v29_values.tobytes()).hexdigest(),
            "candidate_diagonal_sha256": hashlib.sha256(
                candidate_values.tobytes()
            ).hexdigest(),
            "v29_audit": v29_audit,
            "candidate_audit": candidate_audit,
        }
        record_path = ROOT / (
            "docs/task039_extra_physical_multilevel/outcomes/records/"
            "workstation_guided_local_v30_l2_p6_diagonal.json"
        )
        if os.environ.get("TASK39EXTRA_V30_SAVE_P6_RECORD") == "1":
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_path.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print("L2_P6_RECORD " + json.dumps(record, sort_keys=True), flush=True)

        assert max_abs_old <= 1e-10
        assert max_abs_v29 <= 1e-10
        assert rel_old <= 1e-10 and rel_v29 <= 1e-10
        assert candidate_audit["identity"] == (
            "reference_energy_actual_affine_metric_v1"
        )
        assert candidate_audit["actual_cell_T_apply_before_reference_integration"]
        assert candidate_audit["cells_using_reference_metric"] > 0
        assert candidate_audit["metric_cache_misses"] > 1
        assert candidate_audit["orientation_tensor_cache_entries"] > 0
        assert candidate_audit["orientation_tensor_cache_entries"] <= 64
        assert candidate_audit["orientation_tabulation_retained_after_tensor_build"] is False
        assert candidate_audit["geometry_rounding_or_approximation"] is False
        assert candidate_audit["target_cross_terms_preserved_by_fallback"] is True
        for vector in (old, v29, candidate):
            assert np.all(np.isfinite(vector.array))
            assert np.all(vector.array.real > 0)
        slaves = np.asarray(mpc.slaves)
        np.testing.assert_array_equal(
            candidate.array[slaves[slaves < candidate.getLocalSize()]], 1
        )
        record["status"] = "PASS"
        if os.environ.get("TASK39EXTRA_V30_SAVE_P6_RECORD") == "1":
            record_path.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    finally:
        for vector in vectors:
            vector.destroy()
