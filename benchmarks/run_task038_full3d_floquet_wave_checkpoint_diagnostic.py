"""Run the bounded V15 checkpoint residual and rank-32 wave diagnostic.

The heavy imports are deliberately inside ``run_worker``.  This child only
orchestrates the already qualified p6 bundle, one checkpoint restore, one
residual action, and the fixed 32-column diagnostic; it never creates a KSP.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from benchmarks.task038_full3d_jit_staging import (
    F2_MARKER_ORDER,
    F2_MARKER_SCHEMA,
    _install_ffcx_observer,
    _restore_ffcx_observer,
    sha256_file,
    write_marker,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_floquet_wave_checkpoint_diagnostic"
SCHEMA = "task038.v15.f2-f3.floquet-wave.worker-record.v1"
STAGE = "f2-f3-floquet-wave-diagnostic"
PROFILE = "p6/h10/13.5nm/s/grazing1/phi0"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
SELECTOR_SCHEMA = "task038.v15.floquet-selection.v1"
SELECTOR_PAYLOAD_SHA256 = "7a6dea2534b200c6572b0200acd77087c71ccb0e52a0d1a16dae75e108cee2c3"
SELECTED_MODE_INDICES = (
    38,
    39,
    72,
    73,
    76,
    77,
    32,
    33,
    36,
    37,
    40,
    41,
    0,
    1,
    42,
    43,
    46,
    47,
    2,
    3,
    6,
    7,
    74,
    75,
    34,
    35,
    66,
    67,
    70,
    71,
    26,
    27,
)
CHECKPOINT_SOURCE_SHA = "ee5920b9fa977a39fea7bc09cfbe155303acdb2d"
CHECKPOINT_INPUT_IDENTITY_SHA256 = "754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f"
CHECKPOINT_OPERATOR_IDENTITY_SHA256 = "bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3"
CHECKPOINT_MANIFEST_SHA256 = "7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139"
CHECKPOINT_SHARD_SHA256 = "00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b"
CHECKPOINT_ITERATION = 1000
CHECKPOINT_RESIDUAL = 0.4837947981092168
RANK = 32
PREDICTED_CENTRAL_RSS = 1_555_934_144
Q32_BYTES = 88_986_624
SIX_VECTOR_BYTES = 16_684_992
VECTOR_BYTES = 2_780_832
RSS_WATCHDOG = 1_950_000_000
RSS_HARD_LIMIT = 2_000_000_000
F2_RESIDUAL_LIMIT = 1.0e-11
F3_ORTHOGONALITY_LIMIT = 1.0e-10
F3_REPEAT_LIMIT = 1.0e-12
F3_CAPTURED_LIMIT = 0.90
F3_RHO_LIMIT = 0.31622776601683794
F3_IDEAL_LIMIT = 0.153


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (
        json.dumps(
            _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _array_sha(values: Any) -> str:
    import numpy as np

    array = np.asarray(values, dtype=np.complex128)
    if not array.flags.c_contiguous:
        raise ValueError("vector facts require a contiguous array view")
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _stable_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _vector_values(vector: Any) -> Any:
    import numpy as np

    return np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()


def _vector_view(vector: Any) -> Any:
    import numpy as np

    return np.asarray(vector.getArray(readonly=True), dtype=np.complex128)


def _marker(
    marker_dir: Path,
    root: Path,
    cache_dir: Path,
    source_sha: str,
    name: str,
    **facts: Any,
) -> Path:
    common = {
        "stage": STAGE,
        "artifact_root": str(root),
        "cache_dir": str(cache_dir),
        "source_sha": source_sha,
        "worker_pid": os.getpid(),
        "mpi_size": 1,
        "watchdog_stop_bytes": RSS_WATCHDOG,
    }
    common.update(facts)
    return write_marker(
        marker_dir,
        name,
        common,
        order=F2_MARKER_ORDER,
        schema=F2_MARKER_SCHEMA,
    )


def _save_vectors(path: Path, arrays: Mapping[str, Any]) -> dict[str, Any]:
    import numpy as np

    if path.exists():
        raise FileExistsError(f"diagnostic vector artifact already exists: {path}")
    np.savez(
        path,
        **{name: np.asarray(values, dtype=np.complex128) for name, values in arrays.items()},
    )
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": int(path.stat().st_size),
        "roles": list(arrays),
    }


def _owned_slaves(setup: Mapping[str, Any]) -> Any:
    import numpy as np

    mpc = setup["floquets"][6].mpc
    index_map = mpc.function_space.dofmap.index_map
    block_size = int(mpc.function_space.dofmap.index_map_bs)
    owned = int(index_map.size_local) * block_size
    values = np.asarray(mpc.slaves, dtype=np.int64)
    return np.asarray(values[(values >= 0) & (values < owned)], dtype=np.int32)


def _basis_facts(values: Any, slave_indices: Any) -> dict[str, Any]:
    import numpy as np

    values = np.asarray(values, dtype=np.complex128)
    slaves = np.asarray(slave_indices, dtype=np.int64)
    finite = bool(np.all(np.isfinite(values)))
    norm_value = float(np.linalg.norm(values)) if finite else None
    finite = bool(finite and norm_value is not None and np.isfinite(norm_value))
    return {
        "array_sha256": _array_sha(values),
        "finite": finite,
        "norm": norm_value if finite else None,
        "owned_slave_max": (
            float(np.max(np.abs(values[slaves])))
            if finite and slaves.size
            else 0.0 if finite else None
        ),
    }


def _unobserved_facts() -> dict[str, Any]:
    return {
        "observed": False,
        "array_sha256": None,
        "finite": None,
        "norm": None,
        "owned_slave_max": None,
    }


def _build_identity(
    specification: Any,
    payload: Mapping[str, Any],
    cfg: Any,
    bundle: Mapping[str, Any],
    rhs_generation: Mapping[str, Any],
    rhs_before: Any,
    setup_audit: Mapping[str, Any],
    physical_audit: Mapping[str, Any],
    input_path: Path,
) -> dict[str, Any]:
    from benchmarks.run_task038_full3d_same_mesh_hcurl_pmg_p0_physical import (
        _frozen_input_identity,
    )

    frozen = _frozen_input_identity(
        specification, payload, cfg, str(bundle["mode_sha256"])
    )
    operator_authority = {
        "profile": PROFILE,
        "levels": [6, 3, 1],
        "pairs": [[6, 3], [3, 1]],
        "setup_audit": _jsonable(setup_audit),
        "physical_action": _jsonable(physical_audit),
        "frozen_input": _jsonable(frozen),
        "mode_manifest_sha256": str(bundle["mode_sha256"]),
    }
    input_authority = {
        **_jsonable(frozen),
        "source_generation": _jsonable(rhs_generation),
        "rhs_array_sha256": _array_sha(rhs_before),
        "input_path": str(input_path),
    }
    return {
        "input_file_sha256": str(specification.input_sha256),
        "physical_model_sha256": str(specification.physical_model_sha256),
        "mode_manifest_sha256": str(bundle["mode_sha256"]),
        "profile": PROFILE,
        "input_identity_sha256": _stable_sha(input_authority),
        "operator_identity_sha256": _stable_sha(operator_authority),
        "checkpoint_input_identity_sha256": CHECKPOINT_INPUT_IDENTITY_SHA256,
        "checkpoint_operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY_SHA256,
        "frozen_input": frozen,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--marker-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--input", type=Path, required=True)
    return parser.parse_args(argv)


def run_worker(args: argparse.Namespace) -> None:
    root = Path(args.artifact_root).resolve()
    cache_dir = Path(args.cache_dir).resolve()
    marker_dir = Path(args.marker_dir).resolve()
    checkpoint_dir = Path(args.checkpoint_dir).resolve()
    record_path = Path(args.record).resolve()
    input_path = Path(args.input).resolve()
    if int(args.expected_mpi_size) != 1:
        raise ValueError("F2/F3 diagnostic is fixed to MPI1")
    if not root.is_dir() or cache_dir != root / "jit_cache" or not cache_dir.is_dir():
        raise FileNotFoundError("F2/F3 parent-owned root/cache is not prepared")
    if marker_dir != root / "markers" or not marker_dir.is_dir():
        raise FileNotFoundError("F2/F3 parent-owned marker directory is not prepared")
    if not checkpoint_dir.is_dir() or record_path.exists() or not record_path.parent.is_dir():
        raise FileExistsError("F2/F3 checkpoint or record path is not usable")
    raw_dir = root / "diagnostic_raw"
    raw_dir.mkdir(exist_ok=False)
    vector_path = raw_dir / "diagnostic_vectors.npz"
    if not input_path.is_file() or sha256_file(input_path) != INPUT_SHA256:
        raise ValueError("F2/F3 input is not the frozen Task038 profile")
    os.environ["XDG_CACHE_HOME"] = str(cache_dir)
    import numpy as np
    from mpi4py import MPI
    from petsc4py import PETSc

    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise ValueError("F2/F3 diagnostic is MPI1-only")

    from benchmarks.run_task038_full3d_same_mesh_hcurl_pmg_p6_positive import _source_facts
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_memory_first_krylov import read_solution_checkpoint
    from src.solvers.fullspace_physical_wave_diagnostic import (
        project_onto_q,
        select_v15_modes,
        two_pass_mgs_append,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        audit_p6_same_mesh_physical_bundle,
        build_p6_same_mesh_physical_bundle,
        build_physical_rhs,
        destroy_p6_same_mesh_physical_bundle,
    )

    repo = Path(__file__).resolve().parents[1]
    provenance = _source_facts(repo, args.expected_source_sha, comm, PETSc)
    specification = load_and_resolve(input_path)
    payload = specification.as_jsonable()
    cfg = simulation_config_3d_from_normalized(payload)
    calls: list[dict[str, Any]] = []
    jit_module: Any = None
    jit_original: Any = None
    bundle: dict[str, Any] = {}
    rhs: Any = None
    solution: Any = None
    residual_action: Any = None
    residual: Any = None
    rhs_before_view: Any = None
    solution_before_view: Any = None
    residual_action_view: Any = None
    rhs_after_view: Any = None
    solution_after_view: Any = None
    residual_values: Any = None
    source_facts: dict[str, Any] | None = None
    setup_audit: dict[str, Any] | None = None
    physical_audit: dict[str, Any] | None = None
    audit: dict[str, Any] | None = None
    identity: dict[str, Any] | None = None
    checkpoint_facts: dict[str, Any] | None = None
    f2_facts: dict[str, Any] | None = None
    f3_facts: dict[str, Any] | None = None
    q: Any = None
    r_factor: Any = None
    vector_facts: dict[str, Any] | None = None
    coefficients: Any = None
    projected: Any = None
    perpendicular: Any = None
    projection: Any = None
    repeat_perpendicular: Any = None
    repeat_workspace: Any = None
    column_facts: list[dict[str, Any]] = []
    failed_column: dict[str, Any] | None = None
    rhs_norm: float | None = None
    upper_cycle: Any = None
    dtn_action: Any = None
    checkpoint_restore_started = False
    lifecycle_marker_names = [
        "bundle_built",
        "source_built",
        "checkpoint_restore_started",
        "checkpoint_restore_complete",
        "residual_action_started",
        "residual_action_complete",
    ]
    try:
        from dolfinx import jit as jit_module

        calls, jit_original = _install_ffcx_observer(jit_module)

        def callback(name: str, facts: Mapping[str, Any]) -> None:
            if name == "bundle_built":
                _marker(marker_dir, root, cache_dir, args.expected_source_sha, name, **dict(facts))

        bundle = build_p6_same_mesh_physical_bundle(cfg, comm, stage_callback=callback)
        audit = audit_p6_same_mesh_physical_bundle(bundle)
        setup_audit = dict(audit["setup_audit"])
        physical_audit = dict(audit["physical_action"])
        rhs, rhs_generation = build_physical_rhs(bundle)
        if jit_module is not None:
            _restore_ffcx_observer(jit_module, jit_original)
            jit_module = None
            jit_original = None
        slaves = _owned_slaves(bundle["setup"])
        rhs_before_view = _vector_view(rhs)
        try:
            source_before = _basis_facts(rhs_before_view, slaves)
            source_facts = {"generation": rhs_generation, "before": source_before}
            rhs_norm_value = np.linalg.norm(rhs_before_view)
            rhs_norm = float(rhs_norm_value) if np.isfinite(rhs_norm_value) else None
            identity = _build_identity(
                specification,
                payload,
                cfg,
                bundle,
                rhs_generation,
                rhs_before_view,
                setup_audit,
                physical_audit,
                input_path,
            )
        finally:
            rhs_before_view = None
        identity_gate_failures = [
            f"{key} does not match checkpoint authority"
            for key, expected in (
                ("input_identity_sha256", CHECKPOINT_INPUT_IDENTITY_SHA256),
                ("operator_identity_sha256", CHECKPOINT_OPERATOR_IDENTITY_SHA256),
            )
            if identity[key] != expected
        ]
        _marker(
            marker_dir,
            root,
            cache_dir,
            args.expected_source_sha,
            "source_built",
            generation=rhs_generation["generation"],
            mode_manifest_sha256=bundle["mode_sha256"],
            identity_gate_failures=identity_gate_failures,
        )
        if identity_gate_failures:
            f2_facts = {
                "status": "identity_gate_failed",
                "identity_gate_passed": False,
                "identity_failures": identity_gate_failures,
                "checkpoint_solution_before": _unobserved_facts(),
                "checkpoint_solution_after": _unobserved_facts(),
                "rhs_before": source_before,
                "rhs_after": source_before,
                "exact_action_output": _unobserved_facts(),
                "residual": _unobserved_facts(),
                "stored_true_residual": CHECKPOINT_RESIDUAL,
                "recomputed_true_residual": None,
                "relative_difference": None,
                "finite": None,
                "rhs_input_unchanged": None,
                "solution_input_unchanged": None,
                "solution_finite": None,
                "residual_action_finite": None,
                "owned_slave_max": None,
                "residual_action_count": 0,
            }
            f3_facts = {"status": "not_run_by_f2_identity_gate"}
            lifecycle_marker_names = ["bundle_built", "source_built"]
        else:
            solution = rhs.duplicate()
            checkpoint_restore_started = True
            _marker(
                marker_dir,
                root,
                cache_dir,
                args.expected_source_sha,
                "checkpoint_restore_started",
                checkpoint_dir=str(checkpoint_dir),
                iteration=CHECKPOINT_ITERATION,
            )
            checkpoint_facts = read_solution_checkpoint(
                checkpoint_dir,
                solution,
                expected={
                    "iteration": CHECKPOINT_ITERATION,
                    "explicit_true_residual": CHECKPOINT_RESIDUAL,
                    "input_identity_sha256": CHECKPOINT_INPUT_IDENTITY_SHA256,
                    "operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY_SHA256,
                    "physical_model_sha256": PHYSICAL_MODEL_SHA256,
                    "source_sha": CHECKPOINT_SOURCE_SHA,
                    "mpi_size": 1,
                    "manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
                },
                ownership={
                    "rank": 0,
                    "ownership_range": list(map(int, solution.getOwnershipRange())),
                    "local_size": int(solution.getLocalSize()),
                    "global_size": int(solution.getSize()),
                },
                comm=comm,
            )
            _marker(
                marker_dir,
                root,
                cache_dir,
                args.expected_source_sha,
                "checkpoint_restore_complete",
                iteration=checkpoint_facts["iteration"],
                shard_sha256=checkpoint_facts["restored_shard_sha256"],
            )
            solution_before_view = _vector_view(solution)
            checkpoint_before = _basis_facts(solution_before_view, slaves)
            solution_before_view = None
            _marker(marker_dir, root, cache_dir, args.expected_source_sha, "residual_action_started")
            residual_action = rhs.duplicate()
            bundle["physical_action"].apply(solution, residual_action)
            residual_action_view = _vector_view(residual_action)
            action_facts = _basis_facts(residual_action_view, slaves)
            residual_action_view = None
            residual = rhs.copy()
            residual.axpy(PETSc.ScalarType(-1.0), residual_action)
            residual_values = _vector_values(residual)
            residual_norm_value = np.linalg.norm(residual_values)
            residual_finite = bool(np.isfinite(residual_norm_value) and np.all(np.isfinite(residual_values)))
            residual_relative = (
                float(residual_norm_value / rhs_norm)
                if residual_finite and rhs_norm is not None and rhs_norm > 0.0
                else None
            )
            stored_residual = float(CHECKPOINT_RESIDUAL)
            relative_difference = (
                abs(residual_relative - stored_residual)
                / max(abs(stored_residual), np.finfo(float).tiny)
                if residual_relative is not None
                else None
            )
            rhs_after_view = _vector_view(rhs)
            rhs_after_facts = _basis_facts(rhs_after_view, slaves)
            rhs_after_view = None
            solution_after_view = _vector_view(solution)
            checkpoint_after = _basis_facts(solution_after_view, slaves)
            solution_after_view = None
            source_facts["after"] = rhs_after_facts
            source_facts["input_unchanged"] = source_before["array_sha256"] == rhs_after_facts["array_sha256"]
            residual_facts = _basis_facts(residual_values, slaves)
            rhs_unchanged = source_before["array_sha256"] == rhs_after_facts["array_sha256"]
            solution_unchanged = checkpoint_before["array_sha256"] == checkpoint_after["array_sha256"]
            f2_failures: list[str] = []
            for label, facts in (
                ("source/RHS", source_before),
                ("RHS after", rhs_after_facts),
                ("checkpoint solution", checkpoint_before),
                ("checkpoint solution after", checkpoint_after),
                ("exact action output", action_facts),
                ("residual", residual_facts),
            ):
                if facts["finite"] is not True:
                    f2_failures.append(f"{label} is non-finite")
                if facts["owned_slave_max"] != 0.0:
                    f2_failures.append(f"{label} owned slave is nonzero")
            if residual_relative is None or relative_difference is None:
                f2_failures.append("residual relative value is unavailable")
            elif relative_difference > F2_RESIDUAL_LIMIT:
                f2_failures.append("relative residual difference exceeds gate")
            if not rhs_unchanged:
                f2_failures.append("RHS input changed")
            if not solution_unchanged:
                f2_failures.append("solution input changed")
            f2_facts = {
                "status": "observed",
                "identity_gate_passed": True,
                "identity_failures": [],
                "checkpoint": checkpoint_facts,
                "checkpoint_solution_before": checkpoint_before,
                "checkpoint_solution_after": checkpoint_after,
                "rhs_before": source_before,
                "rhs_after": rhs_after_facts,
                "exact_action_output": action_facts,
                "residual": residual_facts,
                "stored_true_residual": stored_residual,
                "recomputed_true_residual": residual_relative,
                "relative_difference": relative_difference,
                "finite": residual_facts["finite"],
                "rhs_input_unchanged": rhs_unchanged,
                "solution_input_unchanged": solution_unchanged,
                "solution_finite": checkpoint_after["finite"],
                "residual_action_finite": action_facts["finite"],
                "owned_slave_max": checkpoint_before["owned_slave_max"],
                "residual_action_count": 1,
            }
            _marker(
                marker_dir,
                root,
                cache_dir,
                args.expected_source_sha,
                "residual_action_complete",
                residual_relative=residual_relative,
                relative_difference=relative_difference,
                finite=f2_facts["finite"],
            )
            if f2_failures:
                f3_facts = {"status": "not_run_by_f2_residual_gate"}
                vector_facts = _save_vectors(vector_path, {"residual": residual_values})
            else:
                for vector_name in ("residual", "residual_action", "solution"):
                    vector = locals()[vector_name]
                    if vector is not None:
                        vector.destroy()
                        if vector_name == "residual":
                            residual = None
                        elif vector_name == "residual_action":
                            residual_action = None
                        else:
                            solution = None
                lifecycle_marker_names.append("basis_started")
                _marker(
                    marker_dir,
                    root,
                    cache_dir,
                    args.expected_source_sha,
                    "basis_started",
                    rank=RANK,
                    selected_mode_indices=list(SELECTED_MODE_INDICES),
                )
                mode_selection = select_v15_modes(
                    bundle["mode_rows"], mode_manifest_sha256=str(bundle["mode_sha256"])
                )
                if tuple(mode_selection["selected_mode_indices"]) != SELECTED_MODE_INDICES:
                    raise RuntimeError("dynamic V15 selector did not reproduce fixed indices")
                selector = {
                    "schema": SELECTOR_SCHEMA,
                    "mode_manifest_sha256": MODE_MANIFEST_SHA256,
                    "selected_mode_indices": list(SELECTED_MODE_INDICES),
                    "selected_rank": RANK,
                    "selector_payload_sha256": SELECTOR_PAYLOAD_SHA256,
                }
                upper_cycle = bundle["setup"]["upper_cycle"]
                dtn_action = bundle["dtn_action"]
                q = np.empty((rhs.getLocalSize(), RANK), dtype=np.complex128, order="F")
                r_factor = np.zeros((RANK, RANK), dtype=np.complex128)
                pc_apply_count = 0
                exact_action_count = 0
                modal_rhs_apply_count = 0
                for column_index, mode_index in enumerate(SELECTED_MODE_INDICES):
                    amplitudes = np.zeros(len(bundle["modes"]), dtype=np.complex128)
                    amplitudes[mode_index] = 1.0 + 0.0j
                    amplitudes_before = amplitudes.copy()
                    modal_rhs = rhs.duplicate()
                    z = None
                    y = None
                    q_column = None
                    modal_rhs_values = None
                    f_after_values = z_after_values = None
                    f_values = z_values = y_values = None
                    modal_rhs_facts: dict[str, Any] | None = None
                    failure: dict[str, Any] | None = None
                    try:
                        dtn_action.apply_modal_rhs(amplitudes, modal_rhs)
                        modal_rhs_apply_count += 1
                        f_values = _vector_view(modal_rhs)
                        f_facts = _basis_facts(f_values, slaves)
                        f_values = None
                        f_norm = f_facts["norm"]
                        if (
                            f_facts["finite"] is not True
                            or f_norm is None
                            or f_norm <= 0.0
                            or f_facts["owned_slave_max"] != 0.0
                        ):
                            failure = {"reason": "modal RHS is non-finite or zero", "modal_rhs": f_facts}
                        else:
                            modal_rhs.scale(1.0 / f_norm)
                            modal_rhs_values = _vector_view(modal_rhs)
                            modal_rhs_facts = _basis_facts(modal_rhs_values, slaves)
                            f_before_sha = modal_rhs_facts["array_sha256"]
                            modal_rhs_values = None
                            if (
                                modal_rhs_facts["finite"] is not True
                                or modal_rhs_facts["owned_slave_max"] != 0.0
                                or modal_rhs_facts["norm"] is None
                                or abs(float(modal_rhs_facts["norm"]) - 1.0) > F3_REPEAT_LIMIT
                            ):
                                failure = {
                                    "reason": "normalized modal RHS is non-finite, non-unit, or has nonzero slave",
                                    "modal_rhs": modal_rhs_facts,
                                }
                            else:
                                z = upper_cycle.apply(modal_rhs)
                                pc_apply_count += 1
                                f_after_values = _vector_view(modal_rhs)
                                f_after_sha = _array_sha(f_after_values)
                                f_after_values = None
                                modal_rhs.destroy()
                                modal_rhs = None
                                z_values = _vector_view(z)
                                z_facts = _basis_facts(z_values, slaves)
                                z_before_sha = z_facts["array_sha256"]
                                z_values = None
                                y = rhs.duplicate()
                                bundle["physical_action"].apply(z, y)
                                exact_action_count += 1
                                z_after_values = _vector_view(z)
                                z_after_sha = _array_sha(z_after_values)
                                z_after_values = None
                                z.destroy()
                                z = None
                                y_values = _vector_view(y)
                                y_facts = _basis_facts(y_values, slaves)
                                if z_facts["finite"] is not True or y_facts["finite"] is not True or y_facts["owned_slave_max"] != 0.0 or z_facts["owned_slave_max"] != 0.0:
                                    failure = {"reason": "basis PC/action output is non-finite or has nonzero slave", "pc_output": z_facts, "action_output": y_facts}
                                else:
                                    try:
                                        q_column, mgs_coefficients, norm = two_pass_mgs_append(q[:, :column_index], y_values, comm)
                                    except ValueError as error:
                                        failure = {"reason": str(error), "action_output": y_facts, "pc_output": z_facts}
                                    if failure is None:
                                        if column_index:
                                            r_factor[:column_index, column_index] = mgs_coefficients
                                        r_factor[column_index, column_index] = norm
                                        q[:, column_index] = q_column
                                        np.matmul(q[:, : column_index + 1], r_factor[: column_index + 1, column_index], out=q_column)
                                        q_column -= y_values
                                        reconstruction_denominator = y_facts["norm"]
                                        reconstruction_numerator = (
                                            float(np.linalg.norm(q_column))
                                            if np.all(np.isfinite(q_column))
                                            else None
                                        )
                                        if reconstruction_denominator is None or reconstruction_denominator <= 0.0:
                                            failure = {"reason": "basis action norm is zero or unavailable", "action_output": y_facts, "pc_output": z_facts}
                                        elif reconstruction_numerator is None:
                                            failure = {"reason": "basis QR reconstruction is non-finite", "action_output": y_facts, "pc_output": z_facts}
                                        else:
                                            reconstruction_relative = reconstruction_numerator / reconstruction_denominator
                                            column_facts.append(
                                                {
                                                    "mode_index": int(mode_index),
                                                    "modal_rhs_norm": float(f_norm),
                                                    "modal_rhs": modal_rhs_facts,
                                                    "pc_output": z_facts,
                                                    "action_output": y_facts,
                                                    "modal_input_unchanged": bool(np.array_equal(amplitudes, amplitudes_before)),
                                                    "pc_input_unchanged": f_before_sha == f_after_sha,
                                                    "action_input_unchanged": z_before_sha == z_after_sha,
                                                    "r_diagonal_abs": float(norm),
                                                    "qr_reconstruction_numerator": reconstruction_numerator,
                                                    "qr_reconstruction_denominator": float(reconstruction_denominator),
                                                    "qr_reconstruction_relative": float(reconstruction_relative),
                                                }
                                            )
                                y_values = None
                                if y is not None:
                                    y.destroy()
                                    y = None
                                q_column = None
                    finally:
                        f_values = f_after_values = modal_rhs_values = None
                        z_values = z_after_values = y_values = q_column = None
                        if y is not None:
                            y.destroy()
                        if z is not None:
                            z.destroy()
                        if modal_rhs is not None:
                            modal_rhs.destroy()
                        amplitudes = amplitudes_before = None
                        modal_rhs = z = y = None
                    if failure is not None:
                        failed_column = {
                            "column_index": int(column_index),
                            "mode_index": int(mode_index),
                            **failure,
                            "pc_apply_count": pc_apply_count,
                            "exact_action_count": exact_action_count,
                            "modal_rhs_apply_count": modal_rhs_apply_count,
                        }
                        break
                accepted_rank = len(column_facts)
                if failed_column is not None:
                    lifecycle_marker_names.append("basis_complete")
                    _marker(
                        marker_dir,
                        root,
                        cache_dir,
                        args.expected_source_sha,
                        "basis_complete",
                        status="span_gate_failed",
                        rank=accepted_rank,
                        failed_column=failed_column,
                        pc_apply_count=pc_apply_count,
                        exact_action_count=exact_action_count,
                        modal_rhs_apply_count=modal_rhs_apply_count,
                    )
                    vector_facts = _save_vectors(
                        vector_path,
                        {
                            "q": q[:, :accepted_rank],
                            "r_factor": r_factor[:accepted_rank, :accepted_rank],
                            "residual": residual_values,
                        },
                    )
                    f3_facts = {
                        "status": "span_gate_failed",
                        "selector": selector,
                        "rank": accepted_rank,
                        "accepted_rank": accepted_rank,
                        "condition_ratio": None,
                        "condition_finite": None,
                        "orthogonality": None,
                        "qr_reconstruction_relative": max((item["qr_reconstruction_relative"] for item in column_facts), default=None),
                        "projection_repeat_relative": None,
                        "captured_energy": None,
                        "rho": None,
                        "ideal_projected_true_residual_relative": None,
                        "pc_apply_count": pc_apply_count,
                        "exact_action_count": exact_action_count,
                        "modal_rhs_apply_count": modal_rhs_apply_count,
                        "column_facts": column_facts,
                        "failed_column": failed_column,
                        "vectors": vector_facts,
                    }
                else:
                    gram = np.empty((RANK, RANK), dtype=np.complex128)
                    for row_index in range(RANK):
                        for column_index in range(RANK):
                            gram[row_index, column_index] = np.vdot(q[:, row_index], q[:, column_index])
                    orthogonality = float(np.linalg.norm(gram - np.eye(RANK), ord=2))
                    singular = np.linalg.svd(r_factor, compute_uv=False)
                    singular_finite = bool(np.all(np.isfinite(singular)))
                    sigma_max = float(singular[0]) if singular.size and singular_finite else 0.0
                    sigma_min = float(singular[-1]) if singular.size and singular_finite else 0.0
                    condition = float(sigma_min / sigma_max) if sigma_max > 0.0 else 0.0
                    condition_finite = bool(singular_finite and np.isfinite(condition))
                    lifecycle_marker_names.append("basis_complete")
                    _marker(
                        marker_dir,
                        root,
                        cache_dir,
                        args.expected_source_sha,
                        "basis_complete",
                        rank=RANK,
                        pc_apply_count=pc_apply_count,
                        exact_action_count=exact_action_count,
                        modal_rhs_apply_count=modal_rhs_apply_count,
                        orthogonality=orthogonality,
                        condition=condition,
                        condition_finite=condition_finite,
                    )
                    lifecycle_marker_names.append("projection_started")
                    _marker(marker_dir, root, cache_dir, args.expected_source_sha, "projection_started")
                    projection = project_onto_q(q, residual_values, comm)
                    coefficients = np.asarray(projection["coefficients"], dtype=np.complex128)
                    projected = np.asarray(projection["projected"], dtype=np.complex128)
                    perpendicular = np.asarray(projection["perpendicular"], dtype=np.complex128)
                    vector_facts = _save_vectors(
                        vector_path,
                        {
                            "q": q,
                            "r_factor": r_factor,
                            "residual": residual_values,
                            "coefficients": coefficients,
                            "projected": projected,
                            "perpendicular": perpendicular,
                        },
                    )
                    captured = float(projection["captured_energy"])
                    rho = float(projection["rho"])
                    perpendicular_norm = float(np.linalg.norm(perpendicular))
                    ideal = float(perpendicular_norm / max(rhs_norm or np.finfo(float).tiny, np.finfo(float).tiny))
                    del projected, coefficients, projection
                    projected = coefficients = projection = None
                    repeat_perpendicular = residual_values.copy()
                    repeat_workspace = np.empty_like(repeat_perpendicular)
                    for column_index in range(RANK):
                        repeat_coefficient = np.vdot(q[:, column_index], residual_values)
                        np.multiply(q[:, column_index], repeat_coefficient, out=repeat_workspace)
                        repeat_perpendicular -= repeat_workspace
                    repeat_perpendicular -= perpendicular
                    projection_repeat = float(np.linalg.norm(repeat_perpendicular) / max(perpendicular_norm, np.finfo(float).tiny))
                    lifecycle_marker_names.append("projection_complete")
                    f3_facts = {
                        "status": "observed",
                        "selector": selector,
                        "rank": RANK,
                        "condition_ratio": condition,
                        "condition_finite": condition_finite,
                        "orthogonality": orthogonality,
                        "qr_reconstruction_relative": float(max(item["qr_reconstruction_relative"] for item in column_facts)),
                        "projection_repeat_relative": projection_repeat,
                        "captured_energy": captured,
                        "rho": rho,
                        "ideal_projected_true_residual_relative": ideal,
                        "pc_apply_count": pc_apply_count,
                        "exact_action_count": exact_action_count,
                        "modal_rhs_apply_count": modal_rhs_apply_count,
                        "column_facts": column_facts,
                        "vectors": vector_facts,
                    }
                    _marker(
                        marker_dir,
                        root,
                        cache_dir,
                        args.expected_source_sha,
                        "projection_complete",
                        rank=RANK,
                        captured_energy=captured,
                        rho=rho,
                        ideal_projected_true_residual_relative=ideal,
                    )
                    del repeat_coefficient, repeat_workspace, repeat_perpendicular, perpendicular, singular, gram
                    repeat_workspace = repeat_perpendicular = perpendicular = None
        _marker(marker_dir, root, cache_dir, args.expected_source_sha, "release_started")
        lifecycle_marker_names += ["release_started", "release_complete"]
        upper_cycle = dtn_action = None
        q = r_factor = coefficients = projected = perpendicular = projection = None
        repeat_workspace = repeat_perpendicular = None
        rhs_before_view = None
        solution_before_view = residual_action_view = None
        rhs_after_view = solution_after_view = None
        residual_values = None
    except ValueError as error:
        if not checkpoint_restore_started or checkpoint_facts is not None:
            raise
        failure = f"checkpoint restore failed: {error}"
        f2_facts = {
            "status": "checkpoint_restore_failed",
            "identity_gate_passed": True,
            "identity_failures": [],
            "checkpoint_solution_before": _unobserved_facts(),
            "checkpoint_solution_after": _unobserved_facts(),
            "rhs_before": source_before,
            "rhs_after": source_before,
            "exact_action_output": _unobserved_facts(),
            "residual": _unobserved_facts(),
            "stored_true_residual": CHECKPOINT_RESIDUAL,
            "recomputed_true_residual": None,
            "relative_difference": None,
            "finite": None,
            "rhs_input_unchanged": True,
            "solution_input_unchanged": None,
            "solution_finite": None,
            "residual_action_finite": None,
            "owned_slave_max": source_before["owned_slave_max"],
            "residual_action_count": 0,
        }
        f3_facts = {"status": "not_run_by_f2_checkpoint_gate"}
        lifecycle_marker_names = [
            "bundle_built",
            "source_built",
            "checkpoint_restore_started",
        ]
        _marker(
            marker_dir,
            root,
            cache_dir,
            args.expected_source_sha,
            "release_started",
            checkpoint_gate_failure=failure,
        )
        lifecycle_marker_names.append("release_started")
        lifecycle_marker_names.append("release_complete")
    finally:
        if jit_module is not None and jit_original is not None:
            _restore_ffcx_observer(jit_module, jit_original)
        rhs_before_view = None
        solution_before_view = residual_action_view = None
        rhs_after_view = solution_after_view = None
        for vector_name in ("residual", "residual_action", "solution", "rhs"):
            vector = locals()[vector_name]
            if vector is not None:
                vector.destroy()
                if vector_name == "residual":
                    residual = None
                elif vector_name == "residual_action":
                    residual_action = None
                elif vector_name == "solution":
                    solution = None
                else:
                    rhs = None
        if bundle:
            destroy_p6_same_mesh_physical_bundle(bundle)
            bundle = {}
        audit = setup_audit = physical_audit = None
        gc.collect()
        PETSc.garbage_cleanup(comm)
        gc.collect()
    _marker(marker_dir, root, cache_dir, args.expected_source_sha, "release_complete")
    if f2_facts is None or f3_facts is None or identity is None or source_facts is None:
        raise RuntimeError("F2/F3 diagnostic did not produce the required raw facts")
    record = {
        "schema": SCHEMA,
        "stage": STAGE,
        "workflow": "f2-f3-floquet-wave",
        "source_sha": args.expected_source_sha,
        "branch": BRANCH,
        "command": [str(Path(sys.executable)), "-m", MODULE, *sys.argv[1:]],
        "provenance": provenance,
        "identity": identity,
        "checkpoint": {
            "source_sha": CHECKPOINT_SOURCE_SHA,
            "input_identity_sha256": CHECKPOINT_INPUT_IDENTITY_SHA256,
            "operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY_SHA256,
            "manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
            "shard_sha256": CHECKPOINT_SHARD_SHA256,
            "iteration": CHECKPOINT_ITERATION,
            "stored_explicit_true_residual": CHECKPOINT_RESIDUAL,
            "solution_only": True,
        },
        "paths": {
            "artifact_root": str(root),
            "cache_dir": str(cache_dir),
            "marker_dir": str(marker_dir),
            "raw_dir": str(raw_dir),
            "record": str(record_path),
            "vectors": None if vector_facts is None else vector_facts,
            "checkpoint_dir": str(checkpoint_dir),
        },
        "mode": {
            "count": 80,
            "manifest_sha256": MODE_MANIFEST_SHA256,
            "selector_schema": SELECTOR_SCHEMA,
            "selector_payload_sha256": SELECTOR_PAYLOAD_SHA256,
            "selected_mode_indices": list(SELECTED_MODE_INDICES),
        },
        "ffcx_calls": calls,
        "expected_ffcx_call_count": 11,
        "source": source_facts,
        "f2": f2_facts,
        "f3": f3_facts,
        "architecture": {
            "checkpoint_read": checkpoint_facts is not None,
            "residual_action_count": int(f2_facts.get("residual_action_count", 0)),
            "basis_pc_count": int(f3_facts.get("pc_apply_count", 0)),
            "basis_action_count": int(f3_facts.get("exact_action_count", 0)),
            "retains_q": f3_facts.get("status") in {"observed", "span_gate_failed"},
            "retains_r": f3_facts.get("status") in {"observed", "span_gate_failed"},
            "retains_z": False,
            "retains_az": False,
            "ksp": False,
            "recovery": False,
            "global_aij": False,
            "numeric_allgather": False,
            "predicted_central_rss": PREDICTED_CENTRAL_RSS,
            "q32_bytes": Q32_BYTES,
            "six_vector_bytes": SIX_VECTOR_BYTES,
            "max_simultaneous_high_vector_count": 6,
            "watchdog_stop_bytes": RSS_WATCHDOG,
            "hard_gate_bytes": RSS_HARD_LIMIT,
        },
        "lifecycle": {
            "marker_schema": F2_MARKER_SCHEMA,
            "marker_names": lifecycle_marker_names,
        },
        "raw_facts_only": True,
    }
    _write_json(record_path, record)


def main(argv: list[str] | None = None) -> int:
    run_worker(_parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "BRANCH",
    "F2_MARKER_ORDER",
    "F2_MARKER_SCHEMA",
    "MODULE",
    "RANK",
    "SCHEMA",
    "main",
    "run_worker",
)
