"""V29/V30 H6 diagonal, fixed-window apply, and original power10 checks."""
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
from src.solvers.fullspace_lor_native_hx_fixture import (
    build_frozen_fullspace_primal_source,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
    _build_same_mesh_levels,
)
from src.solvers.physical_light_setup import build_light_h6_setup


ROOT = Path(__file__).resolve().parents[2]
V30_INPUT = ROOT / "input/task39extra/v30_workstation_guided_original_h7p5.dat"


def _destroy_setup(setup):
    if setup is None:
        return
    smoother = setup.pop("h6", None)
    shell = setup.pop("p6_shell", None)
    if smoother is not None:
        smoother.destroy()
    if shell is not None:
        shell.destroy()
    setup.clear()


def _apply_copy(smoother, rhs):
    result = smoother.apply(rhs)
    try:
        return result.array.copy()
    finally:
        result.destroy()


def _relative_error(actual, expected):
    return float(
        np.linalg.norm(actual - expected)
        / max(np.linalg.norm(expected), np.finfo(float).tiny)
    )


def test_v29_v30_h6_fixed_diagonal_window_and_power10():
    if MPI.COMM_WORLD.size != 1:
        raise AssertionError("the frozen H6 component requires MPI1")
    specification = load_and_resolve(V30_INPUT)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_WORLD, (6,), include_positive_coefficients=True
    )
    space, floquet = levels["spaces"][6], levels["floquets"][6]
    cells = int(space.mesh.topology.index_map(space.mesh.topology.dim).size_local)
    assert cells == 990
    seed, _ = build_frozen_fullspace_primal_source(
        space, floquet, cfg, "random"
    )
    seed_sha256 = hashlib.sha256(seed.array.tobytes()).hexdigest()
    zero = seed.duplicate()
    zero.set(0.0)
    setup_options = dict(
        packed_power10=True,
        packed_apply=True,
        sum_factorized_work=True,
        sum_factorized_power10=True,
        direct_selected_backend=True,
        batched_target_grouping=True,
    )
    v29_setup = None
    v30_setup = None
    try:
        start = perf_counter()
        v29_setup = build_light_h6_setup(
            levels, cfg, lambda *_args, **_kwargs: None,
            reference_metric_diagonal=False,
            **setup_options,
        )
        v29_setup_seconds = perf_counter() - start
        assert v29_setup["light_facts"]["diagonal_builder"] == (
            "quadrature_batched_local_type_reuse_v1"
        )
        assert v29_setup["light_facts"]["seed_sha256"] == seed_sha256
        v29_diagonal = v29_setup["p6_shell"].diagonal.array.copy()
        v29_inverse_sqrt = v29_setup["h6"]._inv_sqrt.array.copy()
        v29_lambda_lo = float(v29_setup["h6"].lambda_lo)
        v29_lambda_hi = float(v29_setup["h6"].lambda_hi)
        v29_history = np.asarray(v29_setup["h6"].power_history, dtype=float)
        v29_power10_output = _apply_copy(v29_setup["h6"], seed)
        v29_facts = dict(v29_setup["light_facts"])
        print("L2 H6 V29 power10 complete", flush=True)
        _destroy_setup(v29_setup)
        v29_setup = None

        start = perf_counter()
        v30_setup = build_light_h6_setup(
            levels, cfg, lambda *_args, **_kwargs: None,
            reference_metric_diagonal=True,
            **setup_options,
        )
        v30_setup_seconds = perf_counter() - start
        assert v30_setup["light_facts"]["diagonal_builder"] == (
            "reference_energy_actual_affine_metric_v1"
        )
        assert v30_setup["light_facts"]["seed_sha256"] == seed_sha256
        v30_diagonal = v30_setup["p6_shell"].diagonal.array.copy()
        v30_inverse_sqrt = v30_setup["h6"]._inv_sqrt.array.copy()
        v30_lambda_lo = float(v30_setup["h6"].lambda_lo)
        v30_lambda_hi = float(v30_setup["h6"].lambda_hi)
        v30_history = np.asarray(v30_setup["h6"].power_history, dtype=float)
        v30_power10_output = _apply_copy(v30_setup["h6"], seed)
        print("L2 H6 V30 power10 complete", flush=True)

        # Hold both D and the spectral window at their V29 values to isolate
        # the H6 action path used by the candidate setup.
        v30_setup["p6_shell"].diagonal.array[:] = v29_diagonal
        v30_setup["h6"]._inv_sqrt.array[:] = v29_inverse_sqrt
        v30_setup["h6"].lambda_lo = v29_lambda_lo
        v30_setup["h6"].lambda_hi = v29_lambda_hi
        v30_fixed_d_window_output = _apply_copy(v30_setup["h6"], seed)

        # Restore the candidate D while retaining the exact V29 spectral
        # window, then measure how the diagonal substitution affects H6 apply.
        v30_setup["p6_shell"].diagonal.array[:] = v30_diagonal
        v30_setup["h6"]._inv_sqrt.array[:] = v30_inverse_sqrt
        v30_setup["h6"].lambda_lo = v29_lambda_lo
        v30_setup["h6"].lambda_hi = v29_lambda_hi
        v30_candidate_d_fixed_window_output = _apply_copy(v30_setup["h6"], seed)
        zero_output = _apply_copy(v30_setup["h6"], zero)

        max_abs_diagonal = float(np.max(np.abs(v30_diagonal - v29_diagonal)))
        relative_diagonal = _relative_error(v30_diagonal, v29_diagonal)
        history_scale = max(float(np.max(np.abs(v29_history))), 1.0)
        max_relative_history_difference = float(
            np.max(np.abs(v30_history - v29_history)) / history_scale
        )
        fixed_d_window_apply_relative = _relative_error(
            v30_fixed_d_window_output, v29_power10_output
        )
        candidate_d_fixed_window_apply_relative = _relative_error(
            v30_candidate_d_fixed_window_output, v29_power10_output
        )
        candidate_native_window_apply_relative = _relative_error(
            v30_power10_output, v29_power10_output
        )
        zero_output_max_abs = float(np.max(np.abs(zero_output)))
        input_sha256 = hashlib.sha256(V30_INPUT.read_bytes()).hexdigest()
        source_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        tracked_diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD"], cwd=ROOT, check=True,
            capture_output=True,
        ).stdout
        record = {
            "schema": "task39extra.v30.l2.h6-fixed-window-power10.v1",
            "status": "MEASURED_BEFORE_ASSERTIONS",
            "source_head": source_head,
            "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
            "h6_test_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "candidate_source_sha256": hashlib.sha256(
                (ROOT / "src/solvers/fullspace_metric_positive_diagonal.py").read_bytes()
            ).hexdigest(),
            "v30_input": V30_INPUT.relative_to(ROOT).as_posix(),
            "input_sha256": input_sha256,
            "run_id": specification.identity["run_id"],
            "degree": 6,
            "mesh_cells": cells,
            "mpi_size": MPI.COMM_WORLD.size,
            "seed_sha256": seed_sha256,
            "setup_seconds": {
                "v29": v29_setup_seconds,
                "v30_reference_metric": v30_setup_seconds,
            },
            "diagonal": {
                "v29_sha256": hashlib.sha256(v29_diagonal.tobytes()).hexdigest(),
                "v30_sha256": hashlib.sha256(v30_diagonal.tobytes()).hexdigest(),
                "max_abs_difference": max_abs_diagonal,
                "relative_l2_difference": relative_diagonal,
            },
            "power10": {
                "v29_history": v29_history.tolist(),
                "v30_history": v30_history.tolist(),
                "max_relative_history_difference": max_relative_history_difference,
                "v29_lambda_lo": v29_lambda_lo,
                "v29_lambda_hi": v29_lambda_hi,
                "v30_lambda_lo": v30_lambda_lo,
                "v30_lambda_hi": v30_lambda_hi,
                "v29_matrix_mult_count": int(v29_facts["power_matrix_mult_count"]),
                "v30_matrix_mult_count": int(
                    v30_setup["h6"].power_matrix_mult_count
                ),
            },
            "h6_apply": {
                "same_v29_D_and_window_relative_difference": fixed_d_window_apply_relative,
                "candidate_D_with_v29_window_relative_difference": candidate_d_fixed_window_apply_relative,
                "candidate_native_power10_window_relative_difference": candidate_native_window_apply_relative,
                "zero_rhs_max_abs": zero_output_max_abs,
            },
            "v29_setup_facts": v29_facts,
            "v30_setup_facts": dict(v30_setup["light_facts"]),
        }
        record_path = ROOT / (
            "docs/task039_extra_physical_multilevel/outcomes/records/"
            "workstation_guided_local_v30_l2_h6_power10.json"
        )
        if os.environ.get("TASK39EXTRA_V30_SAVE_H6_RECORD") == "1":
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_path.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print("L2_H6_RECORD " + json.dumps(record, sort_keys=True), flush=True)

        assert max_abs_diagonal <= 1e-10
        assert relative_diagonal <= 1e-10
        assert len(v29_history) == len(v30_history) == 10
        assert max_relative_history_difference <= 1e-10
        assert abs(v29_lambda_lo - v30_lambda_lo) / max(abs(v29_lambda_lo), 1.0) <= 1e-10
        assert abs(v29_lambda_hi - v30_lambda_hi) / max(abs(v29_lambda_hi), 1.0) <= 1e-10
        assert fixed_d_window_apply_relative <= 1e-10
        assert candidate_d_fixed_window_apply_relative <= 1e-10
        assert candidate_native_window_apply_relative <= 1e-10
        assert zero_output_max_abs == 0.0
        assert int(v29_facts["power_matrix_mult_count"]) == 20
        assert int(v30_setup["h6"].power_matrix_mult_count) == 20
        record["status"] = "PASS"
        if os.environ.get("TASK39EXTRA_V30_SAVE_H6_RECORD") == "1":
            record_path.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    finally:
        _destroy_setup(v29_setup)
        _destroy_setup(v30_setup)
        seed.destroy()
        zero.destroy()
