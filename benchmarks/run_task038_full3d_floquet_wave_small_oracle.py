"""F1 selector and small p3/h50 oracle entry points.

The default selector mode is pure and synthetic.  The explicit real mode is
the only mode that builds the existing p3/h50 same-mesh case; it never builds
p6, a checkpoint, a KSP, or a physical recovery.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


SELECTOR_RECORD_SCHEMA = "task038.v15.floquet-f1-selector.record.v1"
REAL_RECORD_SCHEMA = "task038.v15.floquet-f1-real-small.record.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
SELECTOR_SCHEMA = "task038.v15.floquet-selection.v1"
SELECTOR_POLICY = "eligible_class_filter__normalized_abs_beta_ascending__mode_index_tiebreak"
SELECTOR_PAYLOAD_SHA256 = "7a6dea2534b200c6572b0200acd77087c71ccb0e52a0d1a16dae75e108cee2c3"
PROFILE = "p6/h10/13.5nm/s/grazing1/phi0"
REAL_PROFILE = "p3/h50/13.5nm/s/grazing1/phi0/small-oracle"
REPO_ROOT = Path(__file__).resolve().parents[1]
GIT_DIR = REPO_ROOT / ".git-codex"


def _write_exclusive(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_source(source_sha: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise SystemExit("--source-sha must be a complete lowercase 40-hex SHA")


def _git_value(*arguments: str) -> str:
    completed = subprocess.run(
        [
            "git",
            "--git-dir",
            str(GIT_DIR),
            "--work-tree",
            str(REPO_ROOT),
            *arguments,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git command failed")
    return completed.stdout.strip()


def _source_provenance(source_sha: str) -> dict[str, object]:
    branch = _git_value("symbolic-ref", "--quiet", "--short", "HEAD")
    head = _git_value("rev-parse", "HEAD")
    upstream = _git_value(
        "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
    )
    upstream_sha = _git_value("rev-parse", "--verify", "@{upstream}")
    ahead, behind = _git_value(
        "rev-list", "--left-right", "--count", "HEAD...@{upstream}"
    ).split()
    status = _git_value("status", "--porcelain=v1", "--untracked-files=all")
    if (
        branch != BRANCH
        or upstream != f"origin/{BRANCH}"
        or head != source_sha
        or upstream_sha != source_sha
        or (ahead, behind) != ("0", "0")
        or status
    ):
        raise RuntimeError("source checkout is not the clean current upstream")
    return {
        "branch": branch,
        "head_sha": head,
        "upstream": upstream,
        "upstream_sha": upstream_sha,
        "ahead": 0,
        "behind": 0,
        "status_porcelain": "",
    }


def _runtime_provenance(PETSc, comm) -> dict[str, object]:
    import numpy as np

    expected_python = str(REPO_ROOT / ".venv/bin/python")
    expected_prefix = str(REPO_ROOT / ".venv")
    threads = {
        name: os.environ.get(name)
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    }
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("qualified activation is not enabled")
    if sys.executable != expected_python or sys.prefix != expected_prefix:
        raise RuntimeError("real oracle requires the lexical checkout interpreter")
    if threads != {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}:
        raise RuntimeError("real oracle requires one thread per library")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("real oracle requires PETSc complex128")
    if np.dtype(PETSc.IntType) != np.dtype(np.int32):
        raise RuntimeError("real oracle requires PETSc int32")
    return {
        "qualified_activation": "1",
        "python_executable": sys.executable,
        "python_prefix": sys.prefix,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "mpi_size": int(comm.size),
        "threads": threads,
    }


def _run_selector(args: argparse.Namespace) -> int:
    manifest_path = args.manifest.absolute()
    record_path = args.record.absolute()
    if not manifest_path.is_file() or record_path.exists() or not record_path.parent.is_dir():
        raise SystemExit("manifest/record path is not a fresh readable layout")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"mode_manifest_sha256", "wavelength_nm", "modes"}
    if set(manifest) != required or manifest["mode_manifest_sha256"] != MODE_MANIFEST_SHA256:
        raise SystemExit("manifest identity is not the frozen V15 identity")
    if manifest["wavelength_nm"] != 13.5:
        raise SystemExit("wavelength is not the frozen V15 physical configuration")
    from src.solvers.fullspace_physical_wave_diagnostic import select_v15_modes

    selection = select_v15_modes(
        manifest["modes"],
        wavelength_nm=manifest["wavelength_nm"],
        mode_manifest_sha256=manifest["mode_manifest_sha256"],
    )
    selector = {key: value for key, value in selection.items() if key != "mode_facts"}
    if selector["selector_payload_sha256"] != SELECTOR_PAYLOAD_SHA256:
        raise SystemExit("selector authority payload SHA is not frozen")
    record = {
        "schema": SELECTOR_RECORD_SCHEMA,
        "oracle_kind": "synthetic_algebra",
        "stage": "f1-selector-only",
        "branch": BRANCH,
        "source_sha": args.source_sha,
        "profile": PROFILE,
        "identity": {
            "input_sha256": INPUT_SHA256,
            "physical_model_sha256": PHYSICAL_MODEL_SHA256,
            "mode_manifest_sha256": MODE_MANIFEST_SHA256,
        },
        "manifest": {
            "path": str(manifest_path),
            "mode_manifest_sha256": MODE_MANIFEST_SHA256,
            "mode_count": len(manifest["modes"]),
            "wavelength_nm": manifest["wavelength_nm"],
            "k0_nm_inv": selection["k0_nm_inv"],
        },
        "selector": selector,
        "mode_facts": selection["mode_facts"],
        "execution": {
            "checkpoint": False,
            "compile": False,
            "jit": False,
            "ksp": False,
            "mesh": False,
            "pde": False,
            "physical_recovery": False,
        },
        "scope": (
            "F1 synthetic selector algebra only; no p6 checkpoint rebuild "
            "or formal diagnostic"
        ),
    }
    _write_exclusive(record_path, record)
    return 0


def _partitioned_global_vector(vector, comm):
    import numpy as np

    start, stop = map(int, vector.getOwnershipRange())
    local = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
    parts = comm.gather((start, stop, local), root=0)
    if comm.rank == 0:
        ordered = sorted(parts, key=lambda item: item[0])
        if not ordered or ordered[0][0] != 0:
            raise RuntimeError("small oracle vector ownership has a gap")
        values = []
        cursor = 0
        for part_start, part_stop, part_values in ordered:
            if part_start != cursor or part_values.size != part_stop - part_start:
                raise RuntimeError("small oracle vector ownership is not contiguous")
            values.append(part_values)
            cursor = part_stop
        global_values = np.concatenate(values)
        digest = hashlib.sha256(global_values.tobytes(order="C")).hexdigest()
    else:
        global_values = None
        digest = None
    digest = comm.bcast(digest, root=0)
    return digest, global_values


def _vector_finite_and_slave_max(vector, slave_rows, comm):
    import numpy as np
    from mpi4py import MPI

    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    finite = bool(comm.allreduce(int(np.all(np.isfinite(values))), op=MPI.MIN))
    start, stop = map(int, vector.getOwnershipRange())
    slaves = np.asarray(slave_rows, dtype=np.int64)
    owned = slaves[(slaves >= start) & (slaves < stop)] - start
    local_max = float(np.max(np.abs(values[owned]), initial=0.0))
    return finite, float(comm.allreduce(local_max, op=MPI.MAX))


def _vector_relative(left, right, comm):
    from src.solvers.fullspace_physical_wave_diagnostic import relative_error

    return float(relative_error(left, right, comm))


def _small_config(input_path):
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized

    specification = load_and_resolve(input_path)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    cfg.nedelec_degree = 3
    cfg.visualization_degree = 3
    cfg.mesh_target_size = 50.0
    cfg.mesh_cell_type = "hexahedron"
    cfg.mesh_spacing_mode = "boundary_fitted"
    cfg.mesh_axis_cell_counts = (4, 4, 3)
    cfg.use_pml = False
    cfg.pml_top_thickness = 0.0
    cfg.pml_bottom_thickness = 0.0
    cfg.divergence_penalty = 0.0
    cfg.stage4_dtn_order_policy = "auto_propagating"
    cfg.diffraction_zero_order_only = False
    return cfg


def _run_real_small(args: argparse.Namespace) -> int:
    import numpy as np

    input_path = args.input.absolute()
    record_path = args.record.absolute()
    cache_dir = args.cache_dir.absolute()
    vector_path = record_path.with_name(record_path.stem + "_vectors.npz")
    if not input_path.is_file() or record_path.exists() or vector_path.exists():
        raise SystemExit("real small oracle input or output is not fresh")
    if _sha256_file(input_path) != INPUT_SHA256:
        raise SystemExit("real small oracle input SHA does not match V15")
    os.environ["XDG_CACHE_HOME"] = str(cache_dir)
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    if comm.size != args.expected_mpi_size:
        raise SystemExit("MPI size does not match --expected-mpi-size")
    cache_error = None
    if comm.rank == 0:
        try:
            if cache_dir.exists():
                cache_error = "real small oracle cache must be fresh"
            else:
                cache_dir.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            cache_error = f"real small oracle cache creation failed: {exc}"
    cache_error = comm.bcast(cache_error, root=0)
    comm.barrier()
    if cache_error is not None:
        raise SystemExit(cache_error)

    from petsc4py import PETSc

    runtime_error = None
    runtime_facts = None
    if comm.rank == 0:
        try:
            runtime_facts = _runtime_provenance(PETSc, comm)
        except (RuntimeError, TypeError, ValueError) as exc:
            runtime_error = str(exc)
    runtime_error = comm.bcast(runtime_error, root=0)
    comm.barrier()
    if runtime_error is not None:
        raise SystemExit(runtime_error)
    runtime_facts = comm.bcast(runtime_facts, root=0)

    source_error = None
    source_facts = None
    if comm.rank == 0:
        try:
            source_facts = _source_provenance(args.source_sha)
        except (RuntimeError, OSError, ValueError) as exc:
            source_error = str(exc)
    source_error = comm.bcast(source_error, root=0)
    comm.barrier()
    if source_error is not None:
        raise SystemExit(source_error)
    source_facts = comm.bcast(source_facts, root=0)

    from src.solvers.dtn_port_3d import (
        _ReusableSurfaceComponentAssembler,
        _dtn_surface_quadrature_degree,
    )
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
        build_small_same_mesh_positive_case,
        destroy_small_same_mesh_positive_case,
    )
    from src.solvers.fullspace_physical_wave_diagnostic import (
        V15_MODE_MANIFEST_SHA256,
        V15_SELECTED_MODE_INDICES,
        select_v15_modes,
    )

    case = None
    dtn = None
    vectors = []
    try:
        cfg = _small_config(input_path)
        case = build_small_same_mesh_positive_case(cfg, comm, source_name="random")
        modes, mode_rows, mode_sha = build_dynamic_mode_inventory(cfg)
        if mode_sha != V15_MODE_MANIFEST_SHA256 or len(modes) != 80:
            raise RuntimeError("real small mode inventory is not the frozen 80-mode identity")
        selection = select_v15_modes(
            mode_rows,
            wavelength_nm=cfg.lambda0,
            mode_manifest_sha256=mode_sha,
        )
        qdegree = _dtn_surface_quadrature_degree(cfg, list(modes))
        assemblers = {
            (side, component): _ReusableSurfaceComponentAssembler(
                case["fine_space"],
                case["mesh_data"],
                cfg.tags.z_max if side == "top" else cfg.tags.z_min,
                component,
                quadrature_degree=qdegree,
            )
            for side in ("top", "bottom")
            for component in (0, 1)
        }
        carrier = build_fullspace_dtn_carrier_from_surface(
            modes, assemblers, case["fine_floquet"].mpc, cfg
        )
        dtn = build_fullspace_dtn_action(carrier, comm=comm)
        selected_index = V15_SELECTED_MODE_INDICES[0]
        entry_index = next(
            index
            for index, row in enumerate(mode_rows)
            if int(row["mode_index"]) == selected_index
        )
        amplitudes = np.zeros(len(modes), dtype=np.complex128)
        amplitudes[entry_index] = 1.0 + 0.0j
        amplitudes_before = amplitudes.copy()
        modal = case["fine_matrix"].createVecLeft()
        modal_repeat = case["fine_matrix"].createVecLeft()
        modal_sum = case["fine_matrix"].createVecLeft()
        modal_second = case["fine_matrix"].createVecLeft()
        vectors.extend((modal, modal_repeat, modal_sum, modal_second))
        dtn.apply_modal_rhs(amplitudes, modal)
        dtn.apply_modal_rhs(amplitudes, modal_repeat)
        amplitudes_second = np.zeros_like(amplitudes)
        second_entry = (entry_index + 1) % len(amplitudes)
        amplitudes_second[second_entry] = 1.0 + 0.0j
        dtn.apply_modal_rhs(amplitudes_second, modal_second)
        dtn.apply_modal_rhs(amplitudes + amplitudes_second, modal_sum)
        modal_repeat_rel = _vector_relative(
            modal.getArray(readonly=True), modal_repeat.getArray(readonly=True), comm
        )
        modal_linear_rel = _vector_relative(
            modal_sum.getArray(readonly=True),
            np.asarray(modal.getArray(readonly=True))
            + np.asarray(modal_second.getArray(readonly=True)),
            comm,
        )
        modal_finite, modal_slave_max = _vector_finite_and_slave_max(
            modal, carrier.slave_rows, comm
        )
        if not np.array_equal(amplitudes, amplitudes_before):
            raise RuntimeError("modal one-hot input was modified")
        modal_before = np.asarray(
            modal.getArray(readonly=True), dtype=np.complex128
        ).copy()
        pc = case["pmg"].apply(modal)
        pc_facts = [dict(case["pmg"].last_apply_facts)]
        pc_repeat = case["pmg"].apply(modal)
        pc_repeat_facts = dict(case["pmg"].last_apply_facts)
        pc_second = case["pmg"].apply(modal_second)
        pc_second_facts = dict(case["pmg"].last_apply_facts)
        pc_sum = case["pmg"].apply(modal_sum)
        pc_sum_facts = dict(case["pmg"].last_apply_facts)
        vectors.extend((pc_second, pc_sum, pc, pc_repeat))
        pc_repeat_rel = _vector_relative(
            pc.getArray(readonly=True), pc_repeat.getArray(readonly=True), comm
        )
        pc_linearity_rel = _vector_relative(
            pc_sum.getArray(readonly=True),
            np.asarray(pc.getArray(readonly=True))
            + np.asarray(pc_second.getArray(readonly=True)),
            comm,
        )
        pc_facts.extend((pc_repeat_facts, pc_second_facts, pc_sum_facts))
        pc_finite = all(bool(fact["output_finite"]) for fact in pc_facts)
        pc_slave_max = max(float(fact["owned_slave_max"]) for fact in pc_facts)
        pc_input_unchanged_rel = _vector_relative(
            modal.getArray(readonly=True), modal_before, comm
        )
        coarse = case["coarse_matrix"].createVecRight()
        coarse_before = case["coarse_matrix"].createVecRight()
        coarse_start, coarse_stop = map(int, coarse.getOwnershipRange())
        coarse_values = (1.0 + 0.002 * np.arange(coarse_start, coarse_stop)) + 1j * (
            0.2 - 0.001 * np.arange(coarse_start, coarse_stop)
        )
        coarse.array[:] = np.asarray(coarse_values, dtype=np.complex128)
        coarse.copy(coarse_before)
        primal = case["owner_transfer"].apply_primal(coarse)
        primal_facts = dict(case["owner_transfer"].last_apply_facts)
        primal_repeat = case["owner_transfer"].apply_primal(coarse)
        primal_repeat_facts = dict(case["owner_transfer"].last_apply_facts)
        fine_for_adjoint = modal.copy()
        fine_adjoint_before = np.asarray(
            fine_for_adjoint.getArray(readonly=True), dtype=np.complex128
        ).copy()
        adjoint = case["owner_transfer"].apply_adjoint(fine_for_adjoint)
        adjoint_facts = dict(case["owner_transfer"].last_apply_facts)
        adjoint_repeat = case["owner_transfer"].apply_adjoint(fine_for_adjoint)
        adjoint_repeat_facts = dict(case["owner_transfer"].last_apply_facts)
        vectors.extend(
            (
                coarse,
                coarse_before,
                primal,
                primal_repeat,
                fine_for_adjoint,
                adjoint,
                adjoint_repeat,
            )
        )
        owner_finite = bool(primal_facts["finite"] and adjoint_facts["finite"])
        primal_input_unchanged_rel = _vector_relative(
            coarse.array, coarse_before.array, comm
        )
        adjoint_input_unchanged_rel = _vector_relative(
            fine_for_adjoint.getArray(readonly=True), fine_adjoint_before, comm
        )
        primal_repeat_rel = _vector_relative(
            primal.getArray(readonly=True), primal_repeat.getArray(readonly=True), comm
        )
        adjoint_repeat_rel = _vector_relative(
            adjoint.getArray(readonly=True), adjoint_repeat.getArray(readonly=True), comm
        )
        lhs = complex(primal.dot(fine_for_adjoint))
        rhs = complex(coarse.dot(adjoint))
        adjoint_rel = abs(lhs - rhs) / max(abs(lhs), abs(rhs), np.finfo(float).tiny)
        primal_constraint_residual = float(primal_facts["fine_mpc_constraint_residual"])
        adjoint_slave_max = float(adjoint_facts["coarse_slave_storage_max"])
        modal_digest, modal_global = _partitioned_global_vector(modal, comm)
        pc_digest, pc_global = _partitioned_global_vector(pc, comm)
        if comm.rank == 0:
            np.savez(
                vector_path,
                modal_dual=modal_global,
                pc_output=pc_global,
            )
            vector_sha = _sha256_file(vector_path)
        else:
            vector_sha = None
        vector_sha = comm.bcast(vector_sha, root=0)
        if comm.rank == 0:
            record = {
                "schema": REAL_RECORD_SCHEMA,
                "oracle_kind": "real_small_oracle",
                "stage": "f1-real-small-p3-h50",
                "branch": BRANCH,
                "source_sha": args.source_sha,
                "profile": REAL_PROFILE,
                "identity": {
                    "input_sha256": INPUT_SHA256,
                    "physical_model_sha256": PHYSICAL_MODEL_SHA256,
                    "mode_manifest_sha256": mode_sha,
                },
                "mode_inventory": {
                    "origin": "build_dynamic_mode_inventory",
                    "mode_count": len(mode_rows),
                    "mode_manifest_sha256": mode_sha,
                    "selector_input": "dynamic_mode_rows",
                    "selected_mode_indices": selection["selected_mode_indices"],
                },
                "provenance": {
                    "source": source_facts,
                    "runtime": runtime_facts,
                    "command": {
                        "argv": list(sys.argv),
                        "mode": args.mode,
                        "expected_mpi_size": int(args.expected_mpi_size),
                        "input": str(input_path),
                        "record": str(record_path),
                        "cache_dir": str(cache_dir),
                    },
                },
                "mpi_size": int(comm.size),
                "configuration": {
                    "degree": 3,
                    "mesh_target_nm": 50.0,
                    "mesh_cell_type": "hexahedron",
                    "mesh_axis_cell_counts": [4, 4, 3],
                    "wavelength_nm": float(cfg.lambda0),
                    "grazing_deg": float(90.0 - cfg.incident_theta_deg),
                    "phi_deg": float(cfg.incident_phi_deg),
                    "polarization": str(cfg.polarization_kind),
                    "use_pml": False,
                    "divergence_penalty": 0.0,
                },
                "mode": {
                    "mode_index": int(selected_index),
                    "mode_key": list(carrier.entries[entry_index].mode_key),
                    "selection_schema": selection["schema"],
                    "selector_payload_sha256": selection["selector_payload_sha256"],
                },
                "modal_rhs_apply_count": 4,
                "pmg": {
                    "schema": case["pmg"].audit["schema"],
                    "method": case["pmg"].audit["method"],
                    "levels": list(case["pmg"].audit["levels"]),
                    "apply_count": int(case["pmg"].apply_count),
                },
                "vectors": {
                    "artifact_path": str(vector_path),
                    "artifact_sha256": vector_sha,
                    "modal_dual_sha256": modal_digest,
                    "pc_output_sha256": pc_digest,
                    "modal_dual_global_l2": float(modal.norm()),
                    "pc_output_global_l2": float(pc.norm()),
                    "modal_repeat_relative": modal_repeat_rel,
                    "modal_linearity_relative": modal_linear_rel,
                    "pc_repeat_relative": pc_repeat_rel,
                    "pc_linearity_relative": pc_linearity_rel,
                    "pc_input_unchanged_relative": pc_input_unchanged_rel,
                    "modal_finite": modal_finite,
                    "pc_finite": pc_finite,
                    "modal_owned_slave_max": modal_slave_max,
                    "pc_owned_slave_max": pc_slave_max,
                },
                "owner_transfer": {
                    "finite": owner_finite,
                    "primal_finite": bool(primal_facts["finite"]),
                    "adjoint_finite": bool(adjoint_facts["finite"]),
                    "primal_repeat_relative": primal_repeat_rel,
                    "adjoint_repeat_relative": adjoint_repeat_rel,
                    "adjoint_relative": float(adjoint_rel),
                    "primal_input_unchanged_relative": primal_input_unchanged_rel,
                    "adjoint_input_unchanged_relative": adjoint_input_unchanged_rel,
                    "primal_constraint_residual": primal_constraint_residual,
                    "adjoint_coarse_slave_storage_max": adjoint_slave_max,
                    "primal_apply_count": int(primal_facts["operation"] == "primal")
                    + int(primal_repeat_facts["operation"] == "primal"),
                    "adjoint_apply_count": int(adjoint_facts["operation"] == "adjoint")
                    + int(adjoint_repeat_facts["operation"] == "adjoint"),
                    "owner_transfer_audit": dict(case["owner_transfer"].audit),
                },
                "execution": {
                    "mesh": True,
                    "form_jit": True,
                    "p6": False,
                    "ksp": False,
                    "long_krylov": False,
                    "checkpoint": False,
                    "physical_recovery": False,
                    "official_physics": False,
                },
                "scope": (
                    "F1 real p3/h50 same-mesh modal, PMG, and owner-transfer "
                    "oracle; not p6 or physical qualification"
                ),
            }
            _write_exclusive(record_path, record)
        comm.barrier()
        return 0
    finally:
        if dtn is not None:
            dtn.destroy()
        for vector in reversed(vectors):
            vector.destroy()
        if case is not None:
            destroy_small_same_mesh_positive_case(case)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("selector-only", "real-small-p3-h50"),
        default="selector-only",
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--expected-mpi-size", type=int, default=1)
    args = parser.parse_args()
    _validate_source(args.source_sha)
    if args.mode == "selector-only":
        if args.manifest is None:
            raise SystemExit("selector-only requires --manifest")
        return _run_selector(args)
    if args.expected_mpi_size not in {1, 2}:
        raise SystemExit("real-small-p3-h50 requires MPI size 1 or 2")
    if args.input is None or args.cache_dir is None:
        raise SystemExit("real-small-p3-h50 requires --input and --cache-dir")
    return _run_real_small(args)


if __name__ == "__main__":
    raise SystemExit(main())
