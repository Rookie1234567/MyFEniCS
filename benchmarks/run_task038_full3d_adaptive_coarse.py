"""Thin D1 worker for the owner-local trace-harmonic oracle.

The numerical definition lives in ``src.solvers.fullspace_trace_harmonic``.
This worker only builds the already-qualified small real fixture, writes
owner-local canonical shards, and records the serial assembled oracle when
running with one rank.  It has no D2/D3 correction or residual input path.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np


D1_SCHEMA = "task038.full3d.iterative.adaptive-coarse-record.v1"
D1_PROFILE = "adaptive_trace_harmonic_two_level_v1"
D1_BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
D1_CASES = {
    "p2-mpi1": {"degree": 2, "mpi_size": 1},
    "p2-mpi2": {"degree": 2, "mpi_size": 2},
    "p3-mpi1": {"degree": 3, "mpi_size": 1},
    "p3-mpi2": {"degree": 3, "mpi_size": 2},
}
D1_MESH_TARGET_NM = 50.0
D1_MPI2_SERIAL_BOUNDARY = (
    "distributed_action_identity_only; serial assembled algebra is MPI1-only"
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _source_identity(root: Path) -> dict[str, Any]:
    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", "--git-dir=.git-codex", "--work-tree=.", *arguments],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "git identity probe failed")
        return result.stdout.strip()

    status = git("status", "--short", "--untracked-files=all")
    return {
        "branch": git("branch", "--show-current"),
        "commit_sha": git("rev-parse", "HEAD"),
        "tracked_status": status,
        "clean": status == "",
    }


def _prepare_raw_dir(raw_dir: Path, record_path: Path, comm: Any) -> None:
    error: tuple[str, str] | None = None
    if comm.rank == 0:
        try:
            raw_dir.parent.mkdir(parents=True, exist_ok=True)
            record_path.parent.mkdir(parents=True, exist_ok=True)
            if raw_dir.exists() or record_path.exists():
                raise FileExistsError("D1 raw directory or record already exists")
            raw_dir.mkdir()
        except FileExistsError as exc:
            error = ("FileExistsError", str(exc))
        except OSError as exc:
            error = ("OSError", str(exc))
    error = comm.bcast(error, root=0)
    if error is not None:
        kind, message = error
        if kind == "FileExistsError":
            raise FileExistsError(message)
        raise OSError(message)
    comm.barrier()


def _runtime_identity(root: Path) -> dict[str, Any]:
    import basix
    import dolfinx
    from mpi4py import MPI
    from petsc4py import PETSc
    import slepc4py

    marker = os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION", "")
    lexical_executable = Path(sys.executable).absolute()
    qualified_bin_resolved = (root / ".venv" / "bin").resolve()
    if marker != "1":
        raise RuntimeError("D1 requires qualified activation marker=1")
    if lexical_executable.parent.resolve() != qualified_bin_resolved:
        raise RuntimeError("D1 requires the repository .venv interpreter")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("D1 requires PETSc complex128")
    if np.dtype(PETSc.IntType) != np.dtype(np.int32):
        raise RuntimeError("D1 requires PETSc int32 indices")
    if MPI.Query_thread() < MPI.THREAD_FUNNELED:
        raise RuntimeError("D1 MPI thread level is insufficient")
    return {
        "qualified_marker": marker,
        "python": sys.version.split()[0],
        "sys_executable": str(lexical_executable),
        "qualified_venv_bin_resolved": str(qualified_bin_resolved),
        "mpi_library": MPI.Get_library_version().splitlines()[0],
        "mpi_thread_level": int(MPI.Query_thread()),
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
        "petsc4py": str(PETSc.Sys.getVersion()),
        "slepc4py": str(slepc4py.__version__),
        "dolfinx": str(dolfinx.__version__),
        "basix": str(basix.__version__),
        "mpi4py": str(MPI.Get_version()),
        "threads": {
            name: os.environ.get(name, "")
            for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        },
    }


def _rss_bytes() -> int:
    with Path("/proc/self/status").open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("current VmRSS is unavailable")


def _swap_bytes() -> int:
    with Path("/proc/self/status").open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("VmSwap:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("current process VmSwap is unavailable")


def _telemetry(comm: Any, mpi: Any) -> dict[str, Any]:
    return {
        "rss_semantics": "mpi_rank_max_current_self_rss",
        "swap_semantics": "current_process_VmSwap",
        "rank_max_current_rss_bytes": int(comm.allreduce(_rss_bytes(), op=mpi.MAX)),
        "rank_max_swap_used_bytes": int(comm.allreduce(_swap_bytes(), op=mpi.MAX)),
    }


def _key_value(key: Any) -> complex:
    from benchmarks.canonical_vector_artifacts import canonical_key_json_bytes

    digest = hashlib.sha256(canonical_key_json_bytes(key)).digest()
    real = int.from_bytes(digest[:8], "big") / float(1 << 64)
    imag = int.from_bytes(digest[8:16], "big") / float(1 << 64)
    return complex(0.25 + 0.5 * real, -0.20 + 0.4 * imag)


def _deterministic_source(function_space: Any, floquet_data: Any) -> Any:
    from dolfinx import fem
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_packets,
        reconstruct_canonical_full_fe_function,
    )

    zero = fem.Function(function_space)
    zero.x.array[:] = 0.0
    zero.x.scatter_forward()
    packets, _audit = extract_canonical_full_fe_packets(
        function_space, zero.x.petsc_vec, floquet_data
    )
    deterministic = tuple((key, _key_value(key)) for key, _value in packets)
    if not deterministic:
        raise RuntimeError("D1 canonical source has no owner-local packets")
    field = reconstruct_canonical_full_fe_function(
        function_space, deterministic, floquet_data
    )
    field.x.scatter_forward()
    return field


def _write_packet_manifest(
    raw_dir: Path,
    artifact_name: str,
    vector: Any,
    function_space: Any,
    floquet_data: Any,
    comm: Any,
    *,
    vector_role: str,
) -> dict[str, Any]:
    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
        extract_canonical_full_fe_packets,
    )

    if vector_role == "full_fe":
        packets, extractor_audit = extract_canonical_full_fe_packets(
            function_space, vector, floquet_data
        )
        manifest_kind = "physical_hcurl_primal_packet_manifest"
    elif vector_role == "full_fe_dual":
        packets, extractor_audit = extract_canonical_full_fe_dual_packets(
            function_space, floquet_data.mpc, vector
        )
        manifest_kind = "physical_hcurl_dual_packet_manifest"
    else:
        raise ValueError(f"unsupported D1 packet role: {vector_role}")
    canonical_dir = raw_dir / "canonical"
    shard_path = canonical_dir / f"{artifact_name}.rank{comm.rank:04d}.jsonl"
    shard = write_canonical_packet_shard(shard_path, packets, audit_packets=True)
    shard_metadata = comm.gather(shard, root=0)
    descriptor = None
    if comm.rank == 0:
        manifest = canonical_shard_manifest(
            role=vector_role,
            mpi_size=comm.size,
            shard_metadata=shard_metadata,
            extractor_audit=_jsonable(dict(extractor_audit)),
        )
        manifest_path = canonical_dir / f"{artifact_name}.manifest.json"
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        descriptor = {
            "kind": manifest_kind,
            "name": artifact_name,
            "role": vector_role,
            "relative_path": str(manifest_path.relative_to(raw_dir)),
            "bytes": int(manifest_path.stat().st_size),
            "sha256": manifest_sha,
            "packet_count": int(manifest["global_summed_packet_count"]),
            "mpi_size": int(comm.size),
        }
    return comm.bcast(descriptor, root=0)


def _relative_vec(left: Any, right: Any, comm: Any, mpi: Any) -> float:
    difference = np.asarray(left.getArray(readonly=True)) - np.asarray(
        right.getArray(readonly=True)
    )
    numerator = float(comm.allreduce(float(np.vdot(difference, difference).real), op=mpi.SUM))
    denominator = float(comm.allreduce(float(np.vdot(np.asarray(right.getArray(readonly=True)), np.asarray(right.getArray(readonly=True))).real), op=mpi.SUM))
    return math.sqrt(max(numerator, 0.0)) / max(math.sqrt(max(denominator, 0.0)), np.finfo(float).tiny)


def _topology_facts(topology: Any, floquet_data: Any, comm: Any, mpi: Any) -> dict[str, Any]:
    local_slaves = set(int(row) for row in floquet_data.local_slave_dofs)
    owner_closure = all(
        int(owner) in range(comm.size)
        for facet in topology.facets
        for owner in facet.trace_owners
    )
    owner_closure = owner_closure and all(
        int(row) not in local_slaves
        for facet in topology.facets
        for row in facet.trace_local_rows
    )
    owner_closure = owner_closure and set(
        map(int, topology.owned_trace_global_rows)
    ).isdisjoint(map(int, topology.ghost_trace_global_rows))
    owner_closure = bool(comm.allreduce(owner_closure, op=mpi.LAND))
    volume = np.asarray(
        np.arange(topology.volume_owned_size, dtype=np.float64)
        + 1j * np.arange(topology.volume_owned_size, dtype=np.float64),
        dtype=np.complex128,
    )
    trace = np.asarray(
        np.arange(topology.owned_trace_count, dtype=np.float64) + 1.0
        - 1j * np.arange(topology.owned_trace_count, dtype=np.float64),
        dtype=np.complex128,
    )
    lhs = np.vdot(topology.restrict_volume_to_trace(volume), trace)
    rhs = np.vdot(volume, topology.prolong_trace_to_volume(trace))
    scale = abs(complex(comm.allreduce(lhs, op=mpi.SUM)))
    rp_error = abs(complex(comm.allreduce(lhs - rhs, op=mpi.SUM))) / max(
        scale, np.finfo(float).tiny
    )
    phases = {
        name: [float(complex(value).real), float(complex(value).imag)]
        for name, value in (
            ("x", floquet_data.phase_x),
            ("y", floquet_data.phase_y),
            ("corner", floquet_data.phase_corner),
        )
    }
    plan = topology.neighbor_plan
    plan_fields = (
        "forward_send_peers",
        "forward_recv_peers",
        "backward_send_peers",
        "backward_recv_peers",
        "lower_participant_ranks",
        "upper_participant_ranks",
    )
    return {
        "profile": topology.profile,
        "slab_count": int(topology.audit["slab_count"]),
        "global_facet_count": int(topology.canonical_global_count),
        "local_facet_count": int(len(topology.local_canonical_manifest)),
        "canonical_sha256": topology.canonical_sha256,
        "owned_trace_rows": int(topology.owned_trace_count),
        "ghost_trace_rows": int(topology.ghost_trace_count),
        "owner_closure": owner_closure,
        "neighbor_plan": {
            name: list(getattr(plan, name)) for name in plan_fields
        },
        "restriction_prolongation_adjoint_relative_error": float(rp_error),
        "floquet_phases": phases,
        "floquet_phase_nontrivial": any(
            abs(complex(*value) - 1.0) > 1.0e-8 for value in phases.values()
        ),
        "interface_classifications": sorted(
            topology.audit["interface_classifications"]
        ),
        "audit": _jsonable(
            {
                key: topology.audit[key]
                for key in (
                    "restriction_prolongation",
                    "phase_application",
                    "bounded_material_class_collective",
                    "material_class_collective",
                    "cell_tag_scope",
                    "communication_plan_collective",
                    "canonical_identity_collective",
                    "numeric_allgather",
                    "global_aij_materialized",
                    "dense_interface_mass_materialized",
                    "dense_interface_schur_materialized",
                    "slab_factor_materialized",
                    "slave_rows_excluded",
                )
            }
        ),
    }


def _assemble_dense(form: Any) -> np.ndarray:
    from dolfinx import fem
    from dolfinx.fem import petsc as fem_petsc

    assembled = fem_petsc.assemble_matrix(fem.form(form), bcs=[])
    assembled.assemble()
    dense = assembled.convert("dense")
    values = np.asarray(dense.getDenseArray(), dtype=np.complex128).copy()
    dense.destroy()
    assembled.destroy()
    return values


def _constrained_dense(
    form: Any, raw_space: Any, constrained_space: Any, mpc: Any
) -> tuple[np.ndarray, np.ndarray]:
    from dolfinx import fem

    raw_matrix = _assemble_dense(form)
    index_map = constrained_space.dofmap.index_map
    if int(index_map.num_ghosts) != 0:
        raise RuntimeError("serial D1 oracle unexpectedly has ghost rows")
    slaves = {int(row) for row in np.asarray(mpc.slaves, dtype=np.int32)}
    free_rows = np.asarray(
        [row for row in range(int(index_map.size_local)) if row not in slaves],
        dtype=np.int64,
    )
    transform = np.empty((int(index_map.size_local), free_rows.size), dtype=np.complex128)
    field = fem.Function(constrained_space)
    for column, row in enumerate(free_rows):
        field.x.array[:] = 0.0
        field.x.array[int(row)] = 1.0 + 0.0j
        field.x.scatter_forward()
        mpc.homogenize(field)
        mpc.backsubstitution(field)
        field.x.scatter_forward()
        transform[:, column] = np.asarray(field.x.array, dtype=np.complex128)
    if raw_matrix.shape[0] != transform.shape[0]:
        raise RuntimeError("D1 raw and constrained oracle layouts differ")
    return transform.conj().T @ raw_matrix @ transform, free_rows


def _support_rows(space: Any, topology: Any, floquet_data: Any, slab_id: int):
    cells = np.flatnonzero(
        np.asarray(topology.owned_slab_ids, dtype=np.int8) == int(slab_id)
    )
    slaves = set(int(row) for row in floquet_data.local_slave_dofs)
    rows = {
        int(row)
        for cell in cells
        for row in space.dofmap.cell_dofs(int(cell))
        if int(row) not in slaves
    }
    active = np.asarray(sorted(rows), dtype=np.int64)
    trace_set = set(int(row) for row in topology.owned_trace_local_rows)
    trace = np.asarray(sorted(set(active.tolist()) & trace_set), dtype=np.int64)
    interior = np.asarray(
        sorted(set(active.tolist()) - set(trace.tolist())), dtype=np.int64
    )
    return active, trace, interior


def _serial_algebra(
    raw_dir: Path,
    definitions: tuple[Any, Any],
    raw_space: Any,
    space: Any,
    floquet_data: Any,
    topology: Any,
    source_field: Any,
) -> dict[str, Any]:
    from src.solvers.fullspace_trace_harmonic import (
        generalized_trace_eigenpairs,
        harmonic_extension_from_blocks,
    )

    arrays: dict[str, np.ndarray] = {}
    facts: dict[str, Any] = {
        "status": "measured",
        "fixture": "serial_p2_p3_assembled_oracle_only",
        "global_numeric_allgather": False,
        "ksp_created": False,
        "slabs": {},
    }
    free_rows_reference: np.ndarray | None = None
    for slab_id, definition in enumerate(definitions):
        auxiliary, interface_mass = _constrained_dense(
            definition.auxiliary_form, raw_space, space, floquet_data.mpc
        )
        mass_full, free_rows = _constrained_dense(
            definition.interface_mass_form, raw_space, space, floquet_data.mpc
        )
        if free_rows_reference is None:
            free_rows_reference = free_rows
        elif not np.array_equal(free_rows_reference, free_rows):
            raise RuntimeError("D1 B/M free row maps differ")
        active_rows, trace_rows, interior_rows = _support_rows(
            space, topology, floquet_data, slab_id
        )
        positions = {int(row): index for index, row in enumerate(free_rows)}
        active = np.asarray([positions[int(row)] for row in active_rows], dtype=np.int64)
        trace = np.asarray([positions[int(row)] for row in trace_rows], dtype=np.int64)
        interior = np.asarray([positions[int(row)] for row in interior_rows], dtype=np.int64)
        if active.size <= trace.size or trace.size == 0:
            raise RuntimeError("D1 slab support does not contain trace and interior rows")
        block = auxiliary[np.ix_(active, active)]
        trace_positions = np.asarray(
            [int(np.flatnonzero(active == row)[0]) for row in trace], dtype=np.int64
        )
        interior_positions = np.asarray(
            [int(np.flatnonzero(active == row)[0]) for row in interior], dtype=np.int64
        )
        mass = mass_full[np.ix_(trace, trace)]
        source_values = np.asarray(source_field.x.array, dtype=np.complex128)
        trace_values = source_values[trace_rows].copy()
        columns = []
        for column in range(trace.size):
            values = np.zeros(trace.size, dtype=np.complex128)
            values[column] = 1.0 + 0.0j
            columns.append(
                harmonic_extension_from_blocks(
                    block, trace_positions, values, interior_positions
                )
            )
        harmonic = np.column_stack(columns)
        stiffness = harmonic.conj().T @ block @ harmonic
        eigenvalues, eigenvectors = generalized_trace_eigenpairs(
            stiffness, mass
        )
        repeat_eigenvalues, repeat_eigenvectors = generalized_trace_eigenpairs(
            stiffness, mass
        )
        first = harmonic_extension_from_blocks(
            block, trace_positions, trace_values, interior_positions
        )
        second = harmonic_extension_from_blocks(
            block, trace_positions, trace_values, interior_positions
        )
        arrays.update(
            {
                f"B_slab{slab_id}": auxiliary,
                f"M_slab{slab_id}": mass_full,
                f"active_free_positions_slab{slab_id}": active,
                f"trace_free_positions_slab{slab_id}": trace,
                f"interior_free_positions_slab{slab_id}": interior,
                f"block_slab{slab_id}": block,
                f"mass_trace_slab{slab_id}": mass,
                f"stiffness_slab{slab_id}": stiffness,
                f"trace_positions_slab{slab_id}": trace_positions,
                f"interior_positions_slab{slab_id}": interior_positions,
                f"trace_values_slab{slab_id}": trace_values,
                f"harmonic_slab{slab_id}": harmonic,
                f"harmonic_first_slab{slab_id}": first,
                f"harmonic_second_slab{slab_id}": second,
                f"eigenvalues_slab{slab_id}": eigenvalues,
                f"eigenvectors_slab{slab_id}": eigenvectors,
                f"eigenvalues_repeat_slab{slab_id}": repeat_eigenvalues,
                f"eigenvectors_repeat_slab{slab_id}": repeat_eigenvectors,
            }
        )
        facts["slabs"][f"slab{slab_id}"] = {
            "active_rows": int(active.size),
            "trace_rows": int(trace.size),
            "interior_rows": int(interior.size),
            "eigen_rank": int(eigenvalues.size),
            "eigen_repeat_exact": bool(
                np.array_equal(eigenvalues, repeat_eigenvalues)
                and np.array_equal(eigenvectors, repeat_eigenvectors)
            ),
        }

    rng = np.random.default_rng(281000 + int(space.element.basix_element.degree))
    volume = np.asarray(
        rng.normal(size=int(space.dofmap.index_map.size_local))
        + 1j * rng.normal(size=int(space.dofmap.index_map.size_local)),
        dtype=np.complex128,
    )
    trace = np.asarray(
        rng.normal(size=topology.owned_trace_count)
        + 1j * rng.normal(size=topology.owned_trace_count),
        dtype=np.complex128,
    )
    arrays["rp_volume"] = volume
    arrays["rp_trace"] = trace
    arrays["rp_restricted"] = topology.restrict_volume_to_trace(volume)
    arrays["rp_prolonged"] = topology.prolong_trace_to_volume(trace)

    npz_path = raw_dir / "serial_algebra.npz"
    np.savez(npz_path, **arrays)
    return {
        **facts,
        "relative_path": str(npz_path.relative_to(raw_dir)),
        "bytes": int(npz_path.stat().st_size),
        "sha256": _sha256(npz_path),
        "dtype": "complex128",
    }


def _run_case(root: Path, args: argparse.Namespace) -> int:
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    spec = D1_CASES[args.case]
    if comm.size != int(spec["mpi_size"]):
        raise RuntimeError(f"{args.case} requires MPI size {spec['mpi_size']}")
    raw_dir = Path(args.raw_dir).resolve()
    record_path = Path(args.record).resolve()
    _prepare_raw_dir(raw_dir, record_path, comm)
    source_start = _source_identity(root)
    if source_start["branch"] != D1_BRANCH:
        raise RuntimeError("D1 runner is on the wrong branch")
    if not source_start["clean"] or source_start["commit_sha"] != args.expected_source_sha:
        raise RuntimeError("D1 runner requires the expected clean source SHA")
    if args.expected_mpi_size is not None and comm.size != args.expected_mpi_size:
        raise RuntimeError("D1 MPI size does not match --expected-mpi-size")
    runtime = _runtime_identity(root)
    rank_runtime_ok = comm.allreduce(runtime == comm.bcast(runtime if comm.rank == 0 else None, root=0), op=MPI.LAND)
    if not rank_runtime_ok:
        raise RuntimeError("MPI ranks do not share the qualified runtime identity")

    from dataclasses import replace as dataclass_replace
    from src.common.config_3d import target_stage4_config
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.fullspace_slab_interface import build_fullspace_slab_interface
    from src.solvers.fullspace_trace_harmonic import build_trace_harmonic_definition

    cfg = dataclass_replace(
        target_stage4_config(degree=int(spec["degree"]), h_nm=D1_MESH_TARGET_NM),
        incident_theta_deg=21.131,
        incident_phi_deg=33.690,
    )
    mesh_data = build_airbox_mesh_3d(
        cfg, raw_dir / f"mesh-p{int(spec['degree'])}-n{comm.size}"
    )
    raw_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    function_space = floquet_data.mpc.function_space
    topology = build_fullspace_slab_interface(
        function_space, mesh_data, floquet_data, cfg
    )
    canonical_dir = raw_dir / "canonical"
    if comm.rank == 0:
        canonical_dir.mkdir()
    comm.barrier()

    definitions = tuple(
        build_trace_harmonic_definition(
            topology, mesh_data, raw_space, floquet_data.mpc, slab_id
        )
        for slab_id in (0, 1)
    )
    source_field = _deterministic_source(function_space, floquet_data)
    artifacts: dict[str, Any] = {
        "source": _write_packet_manifest(
            raw_dir,
            "source",
            source_field.x.petsc_vec,
            function_space,
            floquet_data,
            comm,
            vector_role="full_fe",
        ),
        "operators": {},
    }
    actions: list[Any] = []
    copies: list[Any] = []
    try:
        for slab_id, definition in enumerate(definitions):
            auxiliary, interface_mass = definition.build_actions()
            actions.extend((auxiliary, interface_mass))
            slab_artifacts: dict[str, Any] = {}
            for name, action in (("B", auxiliary), ("M_Gamma", interface_mass)):
                first = action.apply(source_field.x.petsc_vec).copy()
                second = action.apply(source_field.x.petsc_vec).copy()
                copies.extend((first, second))
                artifact_name = f"{'M' if name == 'M_Gamma' else name}_slab{slab_id}"
                first_descriptor = _write_packet_manifest(
                    raw_dir,
                    artifact_name,
                    first,
                    function_space,
                    floquet_data,
                    comm,
                    vector_role="full_fe_dual",
                )
                repeat_descriptor = _write_packet_manifest(
                    raw_dir,
                    f"{artifact_name}_repeat",
                    second,
                    function_space,
                    floquet_data,
                    comm,
                    vector_role="full_fe_dual",
                )
                slab_artifacts[name] = {
                    "action": first_descriptor,
                    "repeat": repeat_descriptor,
                    "worker_repeat_relative_l2": _relative_vec(
                        first, second, comm, MPI
                    ),
                }
            artifacts["operators"][f"slab{slab_id}"] = slab_artifacts

        serial_algebra = (
            _serial_algebra(
                raw_dir,
                definitions,
                raw_space,
                function_space,
                floquet_data,
                topology,
                source_field,
            )
            if comm.size == 1
            else {
                "status": "not_run",
                "boundary": D1_MPI2_SERIAL_BOUNDARY,
            }
        )
        topology_facts = _topology_facts(topology, floquet_data, comm, MPI)
        source_end = _source_identity(root)
        record = {
            "schema_version": D1_SCHEMA,
            "stage": "d1",
            "case": args.case,
            "degree": int(spec["degree"]),
            "mpi_size": int(comm.size),
            "profile": D1_PROFILE,
            "mesh_target_nm": D1_MESH_TARGET_NM,
            "raw_dir": str(raw_dir),
            "source": {
                "branch": source_start["branch"],
                "expected_sha": args.expected_source_sha,
                "commit_sha_start": source_start["commit_sha"],
                "commit_sha_end": source_end["commit_sha"],
                "tracked_status_start": source_start["tracked_status"],
                "tracked_status_end": source_end["tracked_status"],
                "clean_start": bool(source_start["clean"]),
                "clean_end": bool(source_end["clean"]),
            },
            "runtime": runtime,
            "model": {
                "wavelength_nm": float(cfg.lambda0),
                "incident_theta_deg": float(cfg.incident_theta_deg),
                "incident_phi_deg": float(cfg.incident_phi_deg),
                "source_formula": "complex_value=stable_sha256(canonical_full_fe_key)",
                "source_key_identity": "physical full_fe canonical key; no local row/rank/mpi-size input",
            },
            "topology": topology_facts,
            "definitions": {
                f"slab{slab_id}": _jsonable(dict(definition.audit))
                for slab_id, definition in enumerate(definitions)
            },
            "artifacts": artifacts,
            "serial_algebra": serial_algebra,
            "resource": _telemetry(comm, MPI),
            "execution": {
                "ksp_created": False,
                "slepc_used": False,
                "global_numeric_allgather": False,
                "pde_solve": False,
                "stage_only": "d1",
            },
        }
        if comm.rank == 0:
            record_path.write_bytes(_canonical_json(record))
        comm.barrier()
        return 0
    finally:
        for vector in copies:
            vector.destroy()
        for action in actions:
            action.destroy()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("d1",), required=True)
    parser.add_argument("--case", choices=tuple(D1_CASES), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    return _run_case(root, args)


if __name__ == "__main__":
    raise SystemExit(main())
