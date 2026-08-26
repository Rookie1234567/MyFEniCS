"""Thin C0 worker for physical-key source identity on the p3/h50 mesh.

The worker reuses the qualified S2 path/runtime helpers and the existing
same-mesh owner transfer.  It writes owner-local canonical packet shards;
the independent checker, not this worker, decides the C0 gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Mapping

import numpy as np


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
STAGE = "c0"
MODULE = "benchmarks.run_task038_full3d_c0_canonical_source"
SCHEMA = "task038.full3d.canonical-source.c0-record.v1"
MARKER_SCHEMA = "task038.full3d.canonical-source.c0-marker.v1"
C0_CASES = ("p3-h50-mpi1", "p3-h50-mpi2")
C0_DEGREE = 3
C0_H_NM = 50.0
C0_PAIR = (3, 1)
C0_FIXED_SEED = "task038-c0-physical-canonical-source-v1"
C0_MARKERS = (
    "startup",
    "preflight",
    "mesh",
    "sources",
    "transfer",
    "packets",
    "release",
    "record_closeout",
)
C0_SOURCE_HASH_FIELDS = (
    "role",
    "physical_entity_geometry_key",
    "entity_dimension",
    "entity_local_basis_index",
    "canonical_orientation_state",
    "floquet_master_phase_state",
    "fixed_seed",
)
C0_FORBIDDEN_SOURCE_FIELDS = (
    "PETSc global row id",
    "rank id",
    "local row id",
    "ownership range",
    "iteration order",
    "Python object hash",
)


def _scalar_relative(left: complex, right: complex) -> float:
    return float(
        abs(left - right)
        / max(abs(left), abs(right), np.finfo(np.float64).tiny)
    )


def _vector_relative(left: Any, right: Any) -> float:
    difference = left.duplicate()
    left.copy(difference)
    difference.axpy(-1.0, right)
    result = float(
        difference.norm() / max(right.norm(), np.finfo(np.float64).tiny)
    )
    difference.destroy()
    return result


def _finite_vector(vector: Any) -> bool:
    return bool(np.all(np.isfinite(vector.getArray(readonly=True))))


def _c0_marker(
    marker_root: Path,
    name: str,
    source_sha: str,
    comm: Any,
    jsonable: Any,
    **facts: Any,
) -> int:
    if name not in C0_MARKERS:
        raise ValueError(f"unknown C0 marker: {name}")
    wall_time_ns = comm.bcast(time.time_ns() if comm.rank == 0 else None, root=0)
    if comm.rank == 0:
        payload = {
            "schema": MARKER_SCHEMA,
            "marker": name,
            "source_sha": source_sha,
            "wall_time_ns": int(wall_time_ns),
            "facts": jsonable(facts),
        }
        path = marker_root / "markers" / f"{name}.json"
        path.write_bytes(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            + b"\n"
        )
        with path.open("rb") as stream:
            import os

            os.fsync(stream.fileno())
    comm.barrier()
    return int(wall_time_ns)


def _packet_artifact(
    raw_dir: Path,
    label: str,
    packets: Any,
    audit: Mapping[str, Any],
    role: str,
    comm: Any,
    jsonable: Any,
) -> dict[str, Any]:
    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )

    directory = raw_dir / "canonical"
    if comm.rank == 0:
        directory.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    shard_path = directory / f"{label}.rank{comm.rank:04d}.jsonl"
    shard = write_canonical_packet_shard(shard_path, packets, audit_packets=True)
    gathered = comm.gather(shard, root=0)
    descriptor = None
    if comm.rank == 0:
        manifest = canonical_shard_manifest(
            role=role,
            mpi_size=comm.size,
            shard_metadata=gathered,
            extractor_audit=jsonable(dict(audit)),
        )
        manifest_path = directory / f"{label}.manifest.json"
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        descriptor = {
            "role": role,
            "manifest_relative_path": str(manifest_path.relative_to(raw_dir)),
            "manifest_sha256": manifest_sha,
            "packet_count": int(manifest["global_summed_packet_count"]),
            "duplicate_count": int(manifest["summed_local_duplicate_count"]),
            "finite": bool(all(item.get("packet_finite", False) for item in gathered)),
        }
    return comm.bcast(descriptor, root=0)


def _space(mesh: Any, degree: int) -> Any:
    from basix.ufl import element
    from dolfinx import default_real_type, fem

    return fem.functionspace(
        mesh,
        element("N1curl", mesh.basix_cell(), degree, dtype=default_real_type),
    )


def _build_context(comm: Any, cfg: Any) -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    from types import SimpleNamespace

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import (
        _mark_boundary_facets,
        _mark_cells,
        _stage4_axis_plan,
        _structured_hexa_mesh,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg import (
        build_same_mesh_hcurl_transfer,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
        build_same_mesh_hcurl_owner_transfer,
    )

    plan = _stage4_axis_plan(cfg, comm.size)
    mesh = _structured_hexa_mesh(
        comm,
        plan.x_values,
        plan.y_values,
        plan.z_values,
        preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
    )
    facet_tags, _ = _mark_boundary_facets(mesh, cfg)
    cell_tags = _mark_cells(mesh, cfg)
    mesh_data = SimpleNamespace(mesh=mesh, cell_tags=cell_tags, facet_tags=facet_tags)
    fine_space = _space(mesh, 3)
    coarse_space = _space(mesh, 1)
    fine_floquet = build_double_floquet_mpc(fine_space, mesh_data, cfg)
    coarse_cfg = type(cfg)(**cfg.__dict__)
    coarse_cfg.nedelec_degree = 1
    coarse_cfg.visualization_degree = 1
    coarse_floquet = build_double_floquet_mpc(coarse_space, mesh_data, coarse_cfg)
    local_transfer = build_same_mesh_hcurl_transfer(*C0_PAIR)
    owner = build_same_mesh_hcurl_owner_transfer(
        fine_space,
        fine_floquet,
        coarse_space,
        coarse_floquet,
        local_transfer=local_transfer,
    )
    return (
        mesh,
        fine_space,
        fine_floquet,
        coarse_space,
        coarse_floquet,
        local_transfer,
        owner,
    )


def run_c0_worker(
    raw_dir: Path,
    record_path: Path,
    input_path: Path,
    expected_sha: str,
    expected_mpi: int,
    fixed_seed: str = C0_FIXED_SEED,
) -> None:
    import sys

    from mpi4py import MPI

    from benchmarks.run_task038_full3d_lor_s2_memory_first import (
        _input_identity,
        _jsonable,
        _prepare_paths,
        _runtime,
        _source_identity,
        _write_json,
    )
    from benchmarks.run_task038_full3d_r4 import _resolve_case
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        build_physical_canonical_dual_source,
        build_physical_canonical_primal_source,
        extract_canonical_full_fe_dual_packets,
        extract_canonical_full_fe_packets,
    )
    from src.solvers.hcurl_canonical_vector import CANONICAL_SOURCE_SCHEMA
    from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
        explicit_owner_adjoint_audit_only,
    )

    comm = MPI.COMM_WORLD
    if fixed_seed != C0_FIXED_SEED:
        raise ValueError("C0 fixed source seed is frozen")
    if expected_mpi not in (1, 2) or comm.size != int(expected_mpi):
        raise RuntimeError("C0 case requires the expected MPI size")
    case_name = f"p3-h50-mpi{comm.size}"
    if case_name not in C0_CASES:
        raise RuntimeError("unsupported C0 case")
    root = Path(__file__).resolve().parents[1]
    raw_dir = (raw_dir if raw_dir.is_absolute() else root / raw_dir).resolve()
    record_path = (record_path if record_path.is_absolute() else root / record_path).resolve()
    input_path = (input_path if input_path.is_absolute() else root / input_path).resolve()
    _prepare_paths(raw_dir, record_path, comm)
    marker_times: dict[str, int] = {}
    marker_names: list[str] = []

    def emit(name: str, **facts: Any) -> None:
        marker_names.append(name)
        marker_times[name] = _c0_marker(
            raw_dir, name, expected_sha, comm, _jsonable, **facts
        )

    emit("startup", case=case_name, raw_dir=str(raw_dir))
    runtime = _runtime(root, expected_sha, comm)
    emit("preflight", runtime=runtime)
    specification, cfg, resolved = _resolve_case(
        root, input_path, C0_DEGREE, C0_H_NM
    )
    input_identity = _input_identity(root, input_path, specification, resolved)
    emit("mesh", degree=C0_DEGREE, h_nm=C0_H_NM)
    mesh = fine_space = fine_floquet = coarse_space = coarse_floquet = None
    local_transfer = owner = None
    primal = dual = projected = projected_repeat = projected_combo = None
    second_projected = combo = alpha_source = beta_source = None
    adjoint = adjoint_repeat = explicit_adjoint = None
    try:
        (
            mesh,
            fine_space,
            fine_floquet,
            coarse_space,
            coarse_floquet,
            local_transfer,
            owner,
        ) = _build_context(comm, cfg)
        primal, primal_facts = build_physical_canonical_primal_source(
            coarse_space, coarse_floquet, fixed_seed=fixed_seed
        )
        dual, dual_facts = build_physical_canonical_dual_source(
            fine_space, fine_floquet, fixed_seed=fixed_seed
        )
        primal_before = np.asarray(primal.x.array, dtype=np.complex128).copy()
        dual_before = np.asarray(dual.getArray(readonly=True), dtype=np.complex128).copy()
        emit("sources", primal=primal_facts, dual=dual_facts)

        projected = owner.apply_primal(primal.x.petsc_vec)
        primal_phase = owner.last_apply_facts.get("phase_application")
        projected_repeat = owner.apply_primal(primal.x.petsc_vec)
        source2 = primal.x.petsc_vec.copy()
        source2.scale(0.5 - 0.75j)
        second_projected = owner.apply_primal(source2)
        alpha = 0.37 + 0.19j
        beta = -0.23 + 0.41j
        combo = primal.x.petsc_vec.copy()
        combo.scale(alpha)
        combo.axpy(beta, source2)
        projected_combo = owner.apply_primal(combo)
        alpha_source = owner.apply_primal(primal.x.petsc_vec)
        beta_source = owner.apply_primal(source2)
        expected_combo = alpha_source.copy()
        expected_combo.scale(alpha)
        expected_combo.axpy(beta, beta_source)

        adjoint = owner.apply_adjoint(dual)
        adjoint_facts = owner.last_apply_facts
        adjoint_repeat = owner.apply_adjoint(dual)
        explicit_adjoint = explicit_owner_adjoint_audit_only(owner, dual)
        emit(
            "transfer",
            pair=list(C0_PAIR),
            owner_audit=dict(owner.audit),
            local_transfer_audit=dict(local_transfer.audit),
        )
        lhs = projected.dot(dual)
        rhs = primal.x.petsc_vec.dot(adjoint)
        explicit_rhs = primal.x.petsc_vec.dot(explicit_adjoint)
        transfer_facts = {
            "pair_fine_to_coarse": list(C0_PAIR),
            "primal_output_finite": _finite_vector(projected),
            "dual_output_finite": _finite_vector(adjoint),
            "primal_repeat_relative": _vector_relative(projected_repeat, projected),
            "adjoint_repeat_relative": _vector_relative(adjoint_repeat, adjoint),
            "linearity_relative": _vector_relative(projected_combo, expected_combo),
            "input_unchanged": bool(
                np.array_equal(primal.x.array, primal_before)
                and np.array_equal(dual.getArray(readonly=True), dual_before)
            ),
            "global_work_lhs": [float(lhs.real), float(lhs.imag)],
            "global_work_rhs": [float(rhs.real), float(rhs.imag)],
            "explicit_work_rhs": [float(explicit_rhs.real), float(explicit_rhs.imag)],
            "global_adjoint_work_relative": _scalar_relative(lhs, rhs),
            "explicit_adjoint_work_relative": _scalar_relative(lhs, explicit_rhs),
            "implemented_vs_explicit_vector_relative": _vector_relative(
                adjoint, explicit_adjoint
            ),
            "phase_application_primal": primal_phase,
            "phase_application_adjoint": adjoint_facts.get("phase_application"),
            "coarse_dual_reduction": adjoint_facts.get("coarse_dual_reduction"),
            "source_finite": bool(
                np.all(np.isfinite(primal.x.array))
                and np.all(np.isfinite(dual.getArray(readonly=True)))
            ),
            "source_nonzero": bool(
                np.any(np.abs(primal.x.array) > 0.0)
                and np.any(np.abs(dual.getArray(readonly=True)) > 0.0)
            ),
        }
        packet_values = (
            (
                "source_primal",
                primal,
                coarse_space,
                lambda: extract_canonical_full_fe_packets(
                    coarse_space, primal, coarse_floquet
                ),
                "full_fe",
            ),
            (
                "source_dual",
                dual,
                fine_space,
                lambda: extract_canonical_full_fe_dual_packets(
                    fine_space, fine_floquet.mpc, dual
                ),
                "full_fe_dual",
            ),
            (
                "projected_primal",
                projected,
                fine_space,
                lambda: extract_canonical_full_fe_packets(
                    fine_space, projected, fine_floquet
                ),
                "full_fe",
            ),
            (
                "projected_repeat_primal",
                projected_repeat,
                fine_space,
                lambda: extract_canonical_full_fe_packets(
                    fine_space, projected_repeat, fine_floquet
                ),
                "full_fe",
            ),
            (
                "projected_scaled_primal",
                second_projected,
                fine_space,
                lambda: extract_canonical_full_fe_packets(
                    fine_space, second_projected, fine_floquet
                ),
                "full_fe",
            ),
            (
                "projected_combo_primal",
                projected_combo,
                fine_space,
                lambda: extract_canonical_full_fe_packets(
                    fine_space, projected_combo, fine_floquet
                ),
                "full_fe",
            ),
            (
                "adjoint_dual",
                adjoint,
                coarse_space,
                lambda: extract_canonical_full_fe_dual_packets(
                    coarse_space, coarse_floquet.mpc, adjoint
                ),
                "full_fe_dual",
            ),
            (
                "adjoint_repeat_dual",
                adjoint_repeat,
                coarse_space,
                lambda: extract_canonical_full_fe_dual_packets(
                    coarse_space, coarse_floquet.mpc, adjoint_repeat
                ),
                "full_fe_dual",
            ),
            (
                "explicit_adjoint_dual",
                explicit_adjoint,
                coarse_space,
                lambda: extract_canonical_full_fe_dual_packets(
                    coarse_space, coarse_floquet.mpc, explicit_adjoint
                ),
                "full_fe_dual",
            ),
        )
        packet_descriptors: dict[str, Any] = {}
        for label, _vector, _space, extractor, role in packet_values:
            packets, audit = extractor()
            packet_descriptors[label] = _packet_artifact(
                raw_dir, label, packets, audit, role, comm, _jsonable
            )
        emit("packets", labels=list(packet_descriptors))
        source_end = _source_identity(root, expected_sha)
        architecture = {
            "forbidden": {
                "global_transfer_matrix": False,
                "numeric_allgather": False,
                "global_high_order_aij": False,
                "global_direct_coarse": False,
                "p1_factor": False,
                "smoother": False,
                "ksp": False,
                "physical_solve": False,
                "recovery": False,
                "static_condensation": False,
            },
            "owner": dict(owner.audit),
            "levels": {
                "level3": {
                    "degree": 3,
                    "global_rows": int(fine_space.dofmap.index_map.size_global),
                    "local_owned_rows": int(fine_space.dofmap.index_map.size_local),
                },
                "level1": {
                    "degree": 1,
                    "global_rows": int(coarse_space.dofmap.index_map.size_global),
                    "local_owned_rows": int(coarse_space.dofmap.index_map.size_local),
                },
            },
        }
        owner.destroy()
        owner = None
        emit("release", destroyed=True)
        record = {
            "schema": SCHEMA,
            "stage": STAGE,
            "case": case_name,
            "degree": C0_DEGREE,
            "h_nm": C0_H_NM,
            "mpi_size": int(comm.size),
            "branch": BRANCH,
            "raw_dir": str(raw_dir),
            "record_path": str(record_path),
            "command": [
                str(Path(sys.executable).absolute()), "-m", MODULE,
                "--stage", STAGE, "--case", case_name,
                "--raw-dir", str(raw_dir), "--record", str(record_path),
                "--expected-source-sha", expected_sha,
                "--expected-mpi-size", str(expected_mpi),
                "--input", str(input_path), "--fixed-seed", fixed_seed,
            ],
            "source": {
                "start": runtime["source"],
                "end": source_end,
            },
            "runtime": runtime,
            "input_identity": input_identity,
            "provenance": {
                "canonical_source_schema": CANONICAL_SOURCE_SCHEMA,
                "fixed_seed": fixed_seed,
                "hash_fields": list(C0_SOURCE_HASH_FIELDS),
                "forbidden_source_fields": list(C0_FORBIDDEN_SOURCE_FIELDS),
                "source_generation": "physical_canonical_key_sha256_v1",
            },
            "settings": {
                "levels": [3, 1],
                "transfer_pair": list(C0_PAIR),
                "input_relative_limit": 1.0e-13,
                "input_max_abs_limit": 1.0e-12,
                "output_relative_limit": 1.0e-11,
                "adjoint_limit": 1.0e-11,
                "phase_once": "finalized_floquet_mpc_once",
                "canonical_order": "structured physical-key JSON after rank-shard merge",
            },
            "architecture": architecture,
            "source_facts": {"primal": primal_facts, "dual": dual_facts},
            "transfer_facts": transfer_facts,
            "packet_artifacts": packet_descriptors,
            "markers": {
                "relative_dir": "markers",
                "names": list(marker_names),
                "wall_time_ns": dict(marker_times),
            },
            "record_authority": "raw canonical packet shards; checker derives C0 classification",
        }
        if comm.rank == 0:
            _write_json(record_path, record)
        comm.barrier()
        emit(
            "record_closeout",
            record_path=str(record_path),
            record_sha256=hashlib.sha256(record_path.read_bytes()).hexdigest()
            if comm.rank == 0 else None,
        )
    finally:
        for vector in (
            explicit_adjoint,
            adjoint_repeat,
            adjoint,
            expected_combo if "expected_combo" in locals() else None,
            beta_source,
            alpha_source,
            projected_combo,
            combo,
            source2 if "source2" in locals() else None,
            second_projected,
            projected_repeat,
            projected,
            dual,
        ):
            if vector is not None and hasattr(vector, "destroy"):
                vector.destroy()
        if owner is not None:
            owner.destroy()
        del primal, fine_space, coarse_space, fine_floquet, coarse_floquet, local_transfer, mesh


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=(STAGE,), required=True)
    parser.add_argument("--case", choices=C0_CASES, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--fixed-seed", default=C0_FIXED_SEED)
    args = parser.parse_args(argv)
    if args.case != f"p3-h50-mpi{args.expected_mpi_size}":
        parser.error("C0 case and expected MPI size do not match")
    run_c0_worker(
        args.raw_dir.resolve(),
        args.record.resolve(),
        args.input.resolve(),
        args.expected_source_sha,
        args.expected_mpi_size,
        args.fixed_seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
