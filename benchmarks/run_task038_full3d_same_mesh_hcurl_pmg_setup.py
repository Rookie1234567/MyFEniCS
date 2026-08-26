"""Setup-only worker for the fixed p6/p3/p1 same-mesh candidate.

This worker deliberately stops at setup qualification.  It owns the fresh raw
directory and markers, calls the reusable setup bundle, retains the fixed
restart-20 reserve, and applies the upper cycle ten times.  It does not create
a source, outer KSP, checkpoint, physical action, or PDE result.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import numpy as np


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_same_mesh_hcurl_pmg_setup"
STAGE = "c1-p6-setup"
CASE = "p6-h10-mpi1"
RECORD_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.setup-record.v1"
MARKER_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.setup-marker.v1"
PROBE_SOURCE_SCHEMA = "task038.v13.c0.physical-canonical-source.v1"
PROBE_SOURCE_GENERATION = "physical_canonical_key_sha256_v1"
PROBE_SOURCE_ROLE = "full_fe_dual"
PROBE_SEEDS = (
    "task038.v13.c1.p6-setup-probe-x-v1",
    "task038.v13.c1.p6-setup-probe-y-v1",
)
APPLY_COUNT = 10
RESERVE_BASIS_COUNT = 21
RESERVE_AUXILIARY_COUNT = 4
RESERVE_VECTOR_COUNT = 25
ALPHA = 0.37 - 0.19j
BETA = -0.23 + 0.41j
PROBE_LABELS = ("x", "y", "combo", "alpha_x", "beta_y")
APPLY_LABELS = (
    "x",
    "y",
    "x_repeat",
    "combo",
    "alpha_x",
    "beta_y",
    "x_repeat_2",
    "y_repeat",
    "combo_repeat",
    "y_repeat_2",
)
APPLY_INPUT_INDICES = (0, 1, 0, 2, 3, 4, 0, 1, 2, 1)
MARKERS = (
    "paths_ready",
    "bundle_built",
    "audit_ready",
    "reserve_built",
    "pc_applies_complete",
    "retained_ready",
    "reserve_destroyed",
    "bundle_destroyed",
    "record_written",
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, Path):
        return str(value)
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(
        _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8") + b"\n"
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def validate_setup_profile(stage: str, case: str, mpi_size: int) -> None:
    if stage != STAGE or case != CASE or int(mpi_size) != 1:
        raise ValueError("setup worker is fixed to c1-p6-setup/p6-h10-mpi1/MPI1")


def validate_record_staging(raw_dir: Path, record_path: Path) -> None:
    raw_dir = Path(raw_dir).resolve()
    record_path = Path(record_path).resolve()
    if raw_dir == record_path:
        raise ValueError("worker record path must differ from raw_dir")
    marker_dir = raw_dir / "markers"
    if raw_dir.exists() or marker_dir.exists() or record_path.exists():
        raise FileExistsError("worker raw, marker, or record path already exists")
    if not record_path.parent.is_dir():
        raise FileNotFoundError("worker record parent must already exist")
    raw_dir.mkdir(parents=True, exist_ok=False)
    marker_dir.mkdir()


def _emit_marker(raw_dir: Path, name: str, source_sha: str, **facts: Any) -> None:
    if name not in MARKERS:
        raise ValueError(f"unknown setup marker {name}")
    wall_time_ns = time.time_ns()
    _write_json(
        raw_dir / "markers" / f"{name}.json",
        {
            "schema": MARKER_SCHEMA,
            "marker": name,
            "source_sha": source_sha,
            "wall_time_ns": wall_time_ns,
            "facts": facts,
        },
    )
    return None


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--git-dir=.git-codex", "--work-tree=.", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git identity probe failed")
    return result.stdout.strip()


def _source_facts(root: Path, expected_sha: str) -> dict[str, Any]:
    from petsc4py import PETSc
    from mpi4py import MPI

    if (
        type(expected_sha) is not str
        or len(expected_sha) != 40
        or any(char not in "0123456789abcdef" for char in expected_sha)
    ):
        raise ValueError("expected-source-sha must be lowercase full Git SHA")
    actual_sha = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    if actual_sha != expected_sha or branch != BRANCH or status:
        raise RuntimeError(
            f"source identity is not closed: sha={actual_sha}, branch={branch}, status={status!r}"
        )
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified activation is required")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("PETSc scalar type must be complex128")
    if np.dtype(PETSc.IntType) != np.dtype(np.int32):
        raise RuntimeError("PETSc integer type must be int32")
    thread_names = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    threads = {name: os.environ.get(name, "1") for name in thread_names}
    if any(value != "1" for value in threads.values()):
        raise RuntimeError("all recorded thread settings must be one")
    abi = {}
    for name in ("mpi4py", "petsc4py", "dolfinx", "basix"):
        module = importlib.import_module(name)
        abi[name] = str(Path(module.__file__).resolve())
    return {
        "source_sha": actual_sha,
        "branch": branch,
        "clean_source_tree": True,
        "qualified_activation": "1",
        "python_executable": str(Path(sys.executable).resolve()),
        "mpi_size": int(MPI.COMM_WORLD.size),
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": threads,
        "abi_modules": abi,
    }


def _owned_slave_indices(bundle: Mapping[str, Any]) -> np.ndarray:
    mpc = bundle["floquets"][6].mpc
    index_map = mpc.function_space.dofmap.index_map
    owned = int(index_map.size_local) * int(mpc.function_space.dofmap.index_map_bs)
    matrix = bundle["p6_shell"].matrix
    local_rows = int(matrix.getLocalSize()[1])
    slaves = np.asarray(mpc.slaves, dtype=np.int64)
    return np.asarray(slaves[(slaves >= 0) & (slaves < min(owned, local_rows))], dtype=np.int32)


def _probe_qualification(bundle: Mapping[str, Any]) -> dict[str, Any]:
    from petsc4py import PETSc
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        build_physical_canonical_dual_source,
    )

    matrix = bundle["p6_shell"].matrix
    upper = bundle["upper_cycle"]
    slaves = _owned_slave_indices(bundle)
    vectors = [matrix.createVecRight() for _ in PROBE_LABELS]
    target = matrix.createVecRight()
    try:
        source_facts = []
        for vector, fixed_seed in zip(vectors[:2], PROBE_SEEDS, strict=True):
            source, facts = build_physical_canonical_dual_source(
                bundle["spaces"][6],
                bundle["floquets"][6],
                fixed_seed=fixed_seed,
            )
            try:
                source.copy(vector)
            finally:
                source.destroy()
            expected_facts = {
                "schema": PROBE_SOURCE_SCHEMA,
                "source_generation": PROBE_SOURCE_GENERATION,
                "role": PROBE_SOURCE_ROLE,
                "fixed_seed": fixed_seed,
                "source_finite": True,
                "source_nonzero": True,
                "dependent_value_authority": "slave_zero_dual_storage",
                "phase_application": "dual_source_slave_zero_no_phase_reapplication",
            }
            if any(facts.get(key) != expected for key, expected in expected_facts.items()):
                raise RuntimeError("canonical dual probe source facts are not qualified")
            source_facts.append(facts)
        vectors[2].copy(vectors[0])
        vectors[2].scale(PETSc.ScalarType(ALPHA))
        vectors[2].axpy(PETSc.ScalarType(BETA), vectors[1])
        vectors[3].copy(vectors[0])
        vectors[3].scale(PETSc.ScalarType(ALPHA))
        vectors[4].copy(vectors[1])
        vectors[4].scale(PETSc.ScalarType(BETA))
        input_before = np.vstack(
            [np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy() for vector in vectors]
        )
        outputs = np.empty((APPLY_COUNT, input_before.shape[1]), dtype=np.complex128)
        rows: list[dict[str, Any]] = []
        for row_index, (label, input_index) in enumerate(zip(APPLY_LABELS, APPLY_INPUT_INDICES, strict=True)):
            facts = upper.apply_into(vectors[input_index], target)
            np.copyto(outputs[row_index], np.asarray(target.getArray(readonly=True), dtype=np.complex128))
            lower = facts["lower_cycle_facts"]
            rows.append(
                {
                    "label": label,
                    "input_label": PROBE_LABELS[input_index],
                    "p6_smoother_apply_count": int(facts["p6_smoother_apply_count"]),
                    "p63_adjoint_count": int(facts["p63_adjoint_count"]),
                    "p63_primal_count": int(facts["p63_primal_count"]),
                    "lower_cycle_count": int(facts["lower_cycle_count"]),
                    "p1_solve_count": int(facts["p1_solve_count"]),
                    "p1_relative_residual": float(lower["p1_relative_residual"]),
                }
            )
        input_after = np.vstack(
            [np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy() for vector in vectors]
        )
        return {
            "apply_count": APPLY_COUNT,
            "apply_labels": list(APPLY_LABELS),
            "apply_input_indices": list(APPLY_INPUT_INDICES),
            "input_labels": list(PROBE_LABELS),
            "alpha": {"real": ALPHA.real, "imag": ALPHA.imag},
            "beta": {"real": BETA.real, "imag": BETA.imag},
            "rows": rows,
            "owned_slave_indices": [int(value) for value in slaves],
            "input_before": input_before,
            "input_after": input_after,
            "outputs": outputs,
            "source_facts": source_facts,
        }
    finally:
        target.destroy()
        for vector in vectors:
            vector.destroy()


def _write_probe_npz(raw_dir: Path, probe: Mapping[str, Any]) -> dict[str, Any]:
    path = raw_dir / "setup_probes.npz"
    if path.exists():
        raise FileExistsError(f"probe artifact already exists: {path}")
    np.savez_compressed(
        path,
        input_before=np.asarray(probe["input_before"], dtype=np.complex128),
        input_after=np.asarray(probe["input_after"], dtype=np.complex128),
        outputs=np.asarray(probe["outputs"], dtype=np.complex128),
    )
    return {
        "relative_path": path.name,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256_file(path),
        "roles": ["input_before", "input_after", "outputs"],
    }


def _record(
    *,
    raw_dir: Path,
    record_path: Path,
    source: Mapping[str, Any],
    source_sha: str,
    input_path: Path,
    command: list[str],
    setup_audit: Mapping[str, Any],
    reserve: Mapping[str, Any],
    probe: Mapping[str, Any],
    npz: Mapping[str, Any],
) -> dict[str, Any]:
    input_sha = _sha256_file(input_path)
    provenance = {
        **dict(source),
        "source_sha": source_sha,
        "input_path": str(input_path.resolve()),
        "input_sha256": input_sha,
        "command": list(command),
    }
    probe_facts = dict(probe)
    probe_facts.update(
        {
            "probe_kind": "canonical_diagnostic_dual",
            "no_pde_rhs": True,
            "no_physical_solve": True,
            "no_outer_ksp": True,
        }
    )
    probe_facts["npz"] = dict(npz)
    return {
        "schema": RECORD_SCHEMA,
        "stage": STAGE,
        "case": CASE,
        "raw_dir": str(raw_dir.resolve()),
        "record_path": str(record_path.resolve()),
        "command": list(command),
        "provenance": _jsonable(provenance),
        "setup_audit": _jsonable(setup_audit),
        "reserve": _jsonable(dict(reserve)),
        "probes": _jsonable(probe_facts),
        "lifecycle": {
            "marker_relative_dir": "markers",
            "marker_names": list(MARKERS),
            "destroy_order": ["reserve", "bundle"],
            "record_written_after_destroy": True,
        },
    }


def run_worker(args: argparse.Namespace) -> None:
    from mpi4py import MPI
    from petsc4py import PETSc
    from src.common.config_3d import target_stage4_config
    from src.solvers.fullspace_lor_memory_first_foundation import (
        allocate_restart20_reserve,
        destroy_restart20_reserve,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import (
        audit_p6_same_mesh_setup,
        build_p6_same_mesh_setup,
        destroy_p6_same_mesh_setup_bundle,
    )

    comm = MPI.COMM_WORLD
    validate_setup_profile(args.stage, args.case, comm.size)
    if comm.size != 1:
        raise RuntimeError("setup worker is MPI1-only")
    root = Path(__file__).resolve().parents[1]
    raw_dir = Path(args.raw_dir).resolve()
    record_path = Path(args.record).resolve()
    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"input template does not exist: {input_path}")
    source = _source_facts(root, args.expected_source_sha)
    validate_record_staging(raw_dir, record_path)
    command = [
        str(Path(sys.executable).resolve()),
        "-m",
        MODULE,
        "--stage",
        args.stage,
        "--case",
        args.case,
        "--raw-dir",
        str(raw_dir),
        "--record",
        str(record_path),
        "--expected-source-sha",
        args.expected_source_sha,
        "--expected-mpi-size",
        "1",
        "--input",
        str(input_path),
    ]
    bundle: dict[str, Any] = {}
    reserve: dict[str, Any] | None = None
    template: PETSc.Vec | None = None
    setup_audit: dict[str, Any] | None = None
    probe: dict[str, Any] | None = None
    npz: dict[str, Any] | None = None
    try:
        _emit_marker(
            raw_dir, "paths_ready", args.expected_source_sha, raw_dir=str(raw_dir)
        )
        cfg = target_stage4_config(degree=6, h_nm=10.0)
        bundle = build_p6_same_mesh_setup(cfg, comm)
        _emit_marker(
            raw_dir, "bundle_built", args.expected_source_sha
        )
        audit_before_apply = audit_p6_same_mesh_setup(bundle)
        _emit_marker(
            raw_dir,
            "audit_ready",
            args.expected_source_sha,
            schema=audit_before_apply["schema"],
        )
        template = bundle["p6_shell"].matrix.createVecRight()
        reserve = allocate_restart20_reserve(template)
        reserve_facts = {key: value for key, value in reserve.items() if key != "vectors"}
        _emit_marker(
            raw_dir,
            "reserve_built",
            args.expected_source_sha,
            basis_count=reserve_facts["basis_count"],
            auxiliary_vector_count=reserve_facts["auxiliary_vector_count"],
            vector_count=reserve_facts["vector_count"],
        )
        probe = _probe_qualification(bundle)
        npz = _write_probe_npz(raw_dir, probe)
        probe = {
            key: value
            for key, value in probe.items()
            if key not in {"input_before", "input_after", "outputs"}
        }
        setup_audit = audit_p6_same_mesh_setup(bundle)
        _emit_marker(
            raw_dir,
            "pc_applies_complete",
            args.expected_source_sha,
            apply_count=APPLY_COUNT,
            p1_solve_count=setup_audit["p1_factor"]["solve_count"],
        )
        _emit_marker(
            raw_dir,
            "retained_ready",
            args.expected_source_sha,
            retained_dwell_seconds=2.0,
            resource_authority="external_foundation_watchdog_process_tree",
        )
        time.sleep(2.0)
        destroy_restart20_reserve(reserve)
        reserve = None
        _emit_marker(
            raw_dir, "reserve_destroyed", args.expected_source_sha
        )
        destroy_p6_same_mesh_setup_bundle(bundle)
        bundle = {}
        _emit_marker(
            raw_dir, "bundle_destroyed", args.expected_source_sha
        )
        if template is not None:
            template.destroy()
            template = None
        assert setup_audit is not None and probe is not None and npz is not None
        record = _record(
            raw_dir=raw_dir,
            record_path=record_path,
            source=source,
            source_sha=args.expected_source_sha,
            input_path=input_path,
            command=command,
            setup_audit=setup_audit,
            reserve=reserve_facts,
            probe=probe,
            npz=npz,
        )
        _write_json(record_path, record)
        _emit_marker(
            raw_dir, "record_written", args.expected_source_sha, record_path=str(record_path)
        )
    finally:
        if reserve is not None:
            destroy_restart20_reserve(reserve)
        if template is not None:
            template.destroy()
        if bundle:
            destroy_p6_same_mesh_setup_bundle(bundle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=(STAGE,), required=True)
    parser.add_argument("--case", choices=(CASE,), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.expected_mpi_size != 1:
        raise ValueError("setup worker expected MPI size is fixed to one")
    run_worker(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = (
    "APPLY_COUNT",
    "APPLY_LABELS",
    "BRANCH",
    "CASE",
    "MARKERS",
    "MARKER_SCHEMA",
    "MODULE",
    "PROBE_LABELS",
    "RECORD_SCHEMA",
    "STAGE",
    "validate_record_staging",
    "validate_setup_profile",
)
