"""Thin L1/L2 LOR/HX oracle worker.

The numerical transfer lives in ``src.solvers.fullspace_lor_transfer``.  This
entry point only resolves one small oracle case, writes ignored raw arrays and
records facts for the independent checker.  It does not run a
physical/exact-A/PDE contraction.  The L2 route records only positive-auxiliary
source, one-apply, and fixed-CG facts for an independent checker.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import numpy as np
from mpi4py import MPI


SCHEMA = "task038.lor-native-complex-hx.l1-record.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
EXPECTED_CASES = {
    "p2-mpi1": (2, 1),
    "p2-mpi2": (2, 2),
    "p3-mpi1": (3, 1),
    "p3-mpi2": (3, 2),
    "p6-mpi1": (6, 1),
}
TRANSFER_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
SPECTRAL_LIMIT = 100.0
L2_SCHEMA = "task038.lor-native-complex-hx.l2-record.v1"
L2_EXPECTED_CASES = {
    "p2-mpi1": (2, 1),
    "p2-mpi2": (2, 2),
    "p3-mpi1": (3, 1),
    "p3-mpi2": (3, 2),
}
L2_SOURCE_NAMES = ("random", "gradient", "curl", "checkerboard")
L2_RHO_LIMITS = {
    "random": 0.45,
    "gradient": 0.25,
    "curl": 0.45,
    "checkerboard": 0.60,
}
L2_CG_TRUE_RESIDUAL_LIMIT = 1.0e-8
L2_REPEAT_LIMIT = 1.0e-13


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    return value


def _json_bytes(value: Any) -> bytes:
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


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "--git-dir=.git-codex", "--work-tree=.", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git identity probe failed")
    return result.stdout.strip()


def _source_identity(root: Path, expected_sha: str) -> dict[str, Any]:
    status = _git(root, "status", "--short", "--untracked-files=all")
    commit = _git(root, "rev-parse", "HEAD")
    if commit != expected_sha:
        raise RuntimeError(f"source SHA {commit} does not match {expected_sha}")
    return {
        "expected_sha": expected_sha,
        "commit_sha_start": commit,
        "commit_sha_end": commit,
        "branch": _git(root, "branch", "--show-current"),
        "tracked_status_start": status,
        "tracked_status_end": status,
        "clean_start": status == "",
        "clean_end": status == "",
    }


def _runtime_identity(root: Path, expected_mpi_size: int) -> dict[str, Any]:
    import basix
    import dolfinx
    import scipy
    import slepc4py
    from petsc4py import PETSc

    executable = Path(sys.executable).absolute()
    qualified_bin = (root / ".venv" / "bin").resolve()
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("LOR/HX requires qualified activation marker=1")
    if executable.parent.resolve() != qualified_bin:
        raise RuntimeError("LOR/HX requires the repository qualified .venv")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("LOR/HX requires PETSc complex128")
    if np.dtype(PETSc.IntType) != np.dtype(np.int32):
        raise RuntimeError("LOR/HX requires PETSc int32")
    if MPI.COMM_WORLD.size != expected_mpi_size:
        raise RuntimeError("MPI size does not match the case identity")
    return {
        "qualified_activation": "1",
        "mpi_size": int(MPI.COMM_WORLD.size),
        "python": sys.version.split()[0],
        "sys_executable": str(executable),
        "qualified_venv_bin_resolved": str(qualified_bin),
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
        "petsc4py": str(PETSc.Sys.getVersion()),
        "slepc4py": str(slepc4py.__version__),
        "dolfinx": str(dolfinx.__version__),
        "basix": str(basix.__version__),
        "scipy": str(scipy.__version__),
        "threads": {
            name: os.environ.get(name, "")
            for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        },
    }


def _artifact(path: Path, name: str, array: np.ndarray) -> dict[str, Any]:
    np.save(path, np.asarray(array), allow_pickle=False)
    return {
        "name": name,
        "relative_path": path.name,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
        "dtype": str(np.asarray(array).dtype),
        "shape": list(np.asarray(array).shape),
    }


def _packet_digest(key: Any) -> str:
    return hashlib.sha256(_json_bytes(key)).hexdigest()


def _merge_canonical_packets(parts: list[list[tuple[Any, complex]]]) -> tuple[np.ndarray, np.ndarray]:
    merged: dict[str, complex] = {}
    for packets in parts:
        for key, value in packets:
            digest = _packet_digest(key)
            if digest in merged:
                raise RuntimeError(f"duplicate canonical packet digest {digest}")
            merged[digest] = complex(value)
    keys = np.asarray(sorted(merged), dtype="<U64")
    values = np.asarray([merged[key] for key in keys], dtype=np.complex128)
    return keys, values


def _merge_lor_packets(
    parts: list[tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray]:
    rows = [
        (int(edge_id), complex(value))
        for edge_ids, edge_values in parts
        for edge_id, value in zip(edge_ids, edge_values, strict=True)
    ]
    rows.sort(key=lambda item: item[0])
    if any(left[0] == right[0] for left, right in zip(rows, rows[1:])):
        raise RuntimeError("duplicate owner-LOR canonical edge id")
    return (
        np.asarray([row[0] for row in rows], dtype=np.uint32),
        np.asarray([row[1] for row in rows], dtype=np.complex128),
    )


def _prepare_paths(
    raw_dir: Path, record_path: Path, comm: MPI.Comm, stage: str = "l1"
) -> None:
    failure: tuple[str, str] | None = None
    if comm.rank == 0:
        try:
            raw_dir.parent.mkdir(parents=True, exist_ok=True)
            record_path.parent.mkdir(parents=True, exist_ok=True)
            if raw_dir.exists() or record_path.exists():
                raise FileExistsError(
                    f"{stage.upper()} raw directory or record already exists"
                )
            raw_dir.mkdir()
        except Exception as exc:  # only path ownership is handled here
            failure = (type(exc).__name__, str(exc))
    failure = comm.bcast(failure, root=0)
    if failure is not None:
        raise RuntimeError(f"{failure[0]}: {failure[1]}")
    comm.barrier()


def _append_stage_marker(raw_dir: Path, stage: str, rank: int) -> None:
    marker_path = raw_dir / f"stage-rank{int(rank)}.jsonl"
    with marker_path.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {"stage": stage, "rank": int(rank), "time": time.time()},
                sort_keys=True,
            )
            + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())


def _parse_case(case: str) -> tuple[int, int]:
    if case not in EXPECTED_CASES:
        raise ValueError(f"unsupported L1 case {case!r}")
    return EXPECTED_CASES[case]


def _periodic_context(comm: MPI.Comm, degree: int):
    from types import SimpleNamespace

    import ufl
    from basix.ufl import element
    from dolfinx import default_real_type, fem
    from src.common.config_3d import target_stage4_config
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import (
        _mark_boundary_facets,
        _mark_cells,
        _stage4_axis_plan,
        _structured_hexa_mesh,
    )

    cfg = target_stage4_config(degree=degree, h_nm=50.0)
    plan = _stage4_axis_plan(cfg, comm.size)
    msh = _structured_hexa_mesh(
        comm,
        plan.x_values,
        plan.y_values,
        plan.z_values,
        preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
    )
    facet_tags, _ = _mark_boundary_facets(msh, cfg)
    cell_tags = _mark_cells(msh, cfg)
    mesh_data = SimpleNamespace(mesh=msh, cell_tags=cell_tags, facet_tags=facet_tags)
    space = fem.functionspace(
        msh,
        element("N1curl", msh.basix_cell(), degree, dtype=default_real_type),
    )
    floquet = build_double_floquet_mpc(space, mesh_data, cfg)
    return space, floquet


def _periodic_source(space: Any, floquet: Any):
    from dolfinx import fem

    field = fem.Function(space)
    field.interpolate(
        lambda x: np.vstack(
            (
                x[0] + 1j * (1.0 + x[1]),
                2.0 * x[1] + 1j * (2.0 + x[2]),
                -x[2] + 1j * (3.0 + x[0]),
            )
        )
    )
    floquet.mpc.homogenize(field)
    floquet.mpc.backsubstitution(field)
    field.x.scatter_forward()
    return field


def _periodic_action(space: Any, floquet: Any):
    import ufl
    from petsc4py import PETSc
    from src.solvers.fullspace_mpc_action import build_fullspace_mpc_form_action

    u = ufl.TrialFunction(space)
    v = ufl.TestFunction(space)
    form = (
        ufl.inner(ufl.curl(u), ufl.curl(v))
        + PETSc.ScalarType(2.5) * ufl.inner(u, v)
    ) * ufl.dx
    return build_fullspace_mpc_form_action(form, space, mpc=floquet.mpc)


def _apply_copy(action: Any, vector: Any):
    return action.apply(vector).copy()


def _periodic_evidence(degree: int, transfer: Any, comm: MPI.Comm, raw_dir: Path):
    from src.solvers.fullspace_lor_topology import global_lor_edge_roundtrip
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
        extract_canonical_full_fe_packets,
    )

    space, floquet = _periodic_context(comm, degree)
    _append_stage_marker(raw_dir, "periodic_context_built", comm.rank)
    field = _periodic_source(space, floquet)
    _append_stage_marker(raw_dir, "periodic_source_built", comm.rank)
    action = _periodic_action(space, floquet)
    roundtrip, lor_packets, local_transfer_error, topology = global_lor_edge_roundtrip(
        space, floquet, field, transfer
    )
    _append_stage_marker(raw_dir, "global_roundtrip_built", comm.rank)
    source = field.x.petsc_vec.copy()
    mapped_source = roundtrip.x.petsc_vec.copy()
    observed = _apply_copy(action, source)
    mapped_observed = _apply_copy(action, mapped_source)
    repeated = _apply_copy(action, mapped_source)
    _append_stage_marker(raw_dir, "positive_action_applied", comm.rank)
    source_packets = extract_canonical_full_fe_packets(space, source, floquet)[0]
    mapped_source_packets = extract_canonical_full_fe_packets(
        space, mapped_source, floquet
    )[0]
    action_packets = extract_canonical_full_fe_dual_packets(
        space, floquet.mpc, observed
    )[0]
    mapped_action_packets = extract_canonical_full_fe_dual_packets(
        space, floquet.mpc, mapped_observed
    )[0]
    repeat_packets = extract_canonical_full_fe_dual_packets(
        space, floquet.mpc, repeated
    )[0]
    packet_parts = comm.gather(
        (
            source_packets,
            mapped_source_packets,
            action_packets,
            mapped_action_packets,
            repeat_packets,
            lor_packets,
        ),
        root=0,
    )
    _append_stage_marker(raw_dir, "canonical_packets_gathered", comm.rank)
    result = None
    if comm.rank == 0:
        source_keys, source_values = _merge_canonical_packets(
            [part[0] for part in packet_parts]
        )
        mapped_source_keys, mapped_source_values = _merge_canonical_packets(
            [part[1] for part in packet_parts]
        )
        action_keys, action_values = _merge_canonical_packets(
            [part[2] for part in packet_parts]
        )
        mapped_action_keys, mapped_action_values = _merge_canonical_packets(
            [part[3] for part in packet_parts]
        )
        repeat_keys, repeat_values = _merge_canonical_packets(
            [part[4] for part in packet_parts]
        )
        lor_keys, lor_values = _merge_lor_packets([part[5] for part in packet_parts])
        result = {
            "arrays": {
                "canonical_source_keys": source_keys,
                "canonical_source_values": source_values,
                "canonical_mapped_source_keys": mapped_source_keys,
                "canonical_mapped_source_values": mapped_source_values,
                "canonical_action_keys": action_keys,
                "canonical_action_values": action_values,
                "canonical_mapped_action_keys": mapped_action_keys,
                "canonical_mapped_action_values": mapped_action_values,
                "canonical_repeat_keys": repeat_keys,
                "canonical_repeat_values": repeat_values,
                "canonical_lor_keys": lor_keys,
                "canonical_lor_values": lor_values,
            },
            "audit": {
                "fixture": "periodic_h50_positive_action",
                "root_gather_evidence_only": True,
                "production_numeric_allgather": False,
                "canonical_roles": {
                    "source": "full_fe",
                    "mapped_source": "full_fe",
                    "action": "full_fe_dual",
                    "mapped_action": "full_fe_dual",
                    "repeat": "full_fe_dual",
                    "lor": "owner_local_lor_edge",
                },
                "local_transfer_relative": float(local_transfer_error),
                "owner_lor_edge_count": int(lor_keys.size),
                "topology_audit": _jsonable(topology.audit),
            },
        }
    mapped_observed.destroy()
    mapped_source.destroy()
    repeated.destroy()
    observed.destroy()
    source.destroy()
    action.destroy()
    del roundtrip, field, floquet, space
    return result


def _build_case(degree: int):
    from src.solvers.fullspace_lor_transfer import (
        build_local_lor_transfer,
        build_reference_factor_lor_transfer,
    )

    started = time.perf_counter()
    local = build_local_lor_transfer(degree)
    reference = build_reference_factor_lor_transfer(degree)
    return local, reference, time.perf_counter() - started


def _write_success(
    root: Path,
    raw_dir: Path,
    record_path: Path,
    case: str,
    degree: int,
    mpi_size: int,
    source: dict[str, Any],
    runtime: dict[str, Any],
    rank_facts: list[dict[str, Any]],
    local: Any,
    reference: Any,
    build_wall: float,
    periodic: dict[str, Any] | None,
) -> None:
    arrays: dict[str, np.ndarray] = {
        "nodes": local.nodes,
        "high_to_lor": local.high_to_lor_matrix,
        "lor_to_high": local.lor_to_high_matrix,
        "high_matrix": local.high_matrix,
        "lor_matrix": local.lor_matrix,
        "h1_transfer": local.h1_transfer,
        "high_gradient_edge": local.high_gradient_edge,
        "high_curl_face": local.high_curl_face,
        "lor_gradient": local.lor_gradient,
        "lor_curl_incidence": local.lor_curl_incidence,
        "probe": np.arange(local.high_to_lor_matrix.shape[1], dtype=np.float64) + 1j,
    }
    probe = arrays["probe"]
    arrays["local_probe_forward_1"] = local.high_to_lor_matrix @ probe
    arrays["local_probe_forward_2"] = local.high_to_lor_matrix @ probe
    arrays["local_probe_roundtrip"] = local.lor_to_high_matrix @ arrays["local_probe_forward_1"]
    arrays["reference_probe_forward_1"] = reference.high_to_lor(probe)
    arrays["reference_probe_forward_2"] = reference.high_to_lor(probe)
    arrays["reference_probe_inverse_1"] = reference.lor_to_high(
        arrays["reference_probe_forward_1"]
    )
    arrays["reference_probe_inverse_2"] = reference.lor_to_high(
        arrays["reference_probe_forward_2"]
    )
    for axis, group in enumerate(reference.high_edge_groups):
        arrays[f"reference_group_{axis}"] = group
        arrays[f"reference_forward_tensor_{axis}"] = reference.forward_tensors[axis]
        arrays[f"reference_inverse_tensor_{axis}"] = reference.inverse_tensors[axis]
    canonical_status = "not_applicable_by_frozen_case"
    canonical_reason = "p6 is the frozen single-cell case; periodic canonical packets do not apply"
    periodic_audit: dict[str, Any] = {}
    if periodic is not None:
        arrays.update(periodic["arrays"])
        canonical_status = "measured"
        canonical_reason = "root gather is evidence-only; production route uses typed owner-local packets"
        periodic_audit = periodic["audit"]
    source_end = _source_identity(root, source["expected_sha"])
    closed_source = {
        **source,
        "commit_sha_end": source_end["commit_sha_end"],
        "tracked_status_end": source_end["tracked_status_end"],
        "clean_end": source_end["clean_end"],
    }
    artifacts = [
        _artifact(raw_dir / f"{name}.npy", name, array)
        for name, array in arrays.items()
    ]
    record = {
        "schema": SCHEMA,
        "stage": "l1",
        "scope": "l1_transfer_and_periodic_identity_oracle",
        "case": case,
        "degree": int(degree),
        "mpi_size": int(mpi_size),
        "raw_dir": str(raw_dir.resolve()),
        "source": closed_source,
        "runtime": runtime,
        "rank_facts": rank_facts,
        "build_wall_seconds": float(build_wall),
        "recorded_local_audit": _jsonable(local.audit),
        "recorded_reference_audit": _jsonable(reference.audit),
        "artifacts": artifacts,
        "canonical_mpi_identity": {
            "status": canonical_status,
            "reason": canonical_reason,
            "relative_limit": 1.0e-12,
            "root_gather_evidence_only": periodic is not None,
            "production_numeric_allgather": False,
            "audit": periodic_audit,
        },
        "forbidden": {
            "global_numeric_allgather": False,
            "global_aij_in_production": False,
            "global_schur": False,
            "global_direct_coarse": False,
            "per_rank_full_basis_replication": False,
            "production_dense_transfer": False,
        },
        "production": {
            "global_transfer_matrix": False,
            "local_tensor_action": bool(reference.audit["production_local_tensor_action"]),
            "owner_local_maps": True,
            "numeric_allgather": False,
            "retained_dense_transfer_bytes": int(reference.audit["retained_dense_transfer_bytes"]),
            "oracle_local_dense": True,
            "local_dense_oracle_only": True,
        },
        "status": "facts_written_not_qualified",
    }
    record_path.write_bytes(_json_bytes(record))
    print(
        json.dumps(
            {
                "record": str(record_path),
                "case": case,
                "degree": degree,
                "mpi_size": mpi_size,
                "artifact_count": len(artifacts),
                "status": record["status"],
            },
            sort_keys=True,
        )
    )


def _l2_artifact_names(source_name: str) -> dict[str, str]:
    prefix = f"l2_{source_name}"
    return {
        "source_before": f"{prefix}_source_before",
        "source_after": f"{prefix}_source_after",
        "pc_output": f"{prefix}_pc_output",
        "pc_repeat": f"{prefix}_pc_repeat",
        "residual": f"{prefix}_residual",
        "applied_output": f"{prefix}_applied_output",
        "true_residual": f"{prefix}_true_residual",
        "cg_solution": f"{prefix}_cg_solution",
        "cg_action": f"{prefix}_cg_action",
        "cg_true_residual": f"{prefix}_cg_true_residual",
    }


def _l2_canonical_payload(fixture: Any, vectors: dict[str, tuple[Any, str]]) -> dict[str, Any]:
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
        extract_canonical_full_fe_packets,
    )

    payload: dict[str, Any] = {}
    for label, (vector, role) in vectors.items():
        if role == "primal":
            packets = extract_canonical_full_fe_packets(
                fixture.high_space, vector, fixture.high_floquet
            )[0]
        elif role == "dual":
            packets = extract_canonical_full_fe_dual_packets(
                fixture.high_space, fixture.high_floquet.mpc, vector
            )[0]
        else:
            raise ValueError(f"unknown L2 canonical role {role!r}")
        payload[label] = packets
    return payload


def _l2_gather_payload(
    comm: MPI.Comm, payload: dict[str, Any]
) -> dict[str, np.ndarray] | None:
    parts = comm.gather(payload, root=0)
    if comm.rank != 0:
        return None
    arrays: dict[str, np.ndarray] = {}
    for label in payload:
        keys, values = _merge_canonical_packets(
            [part[label] for part in parts]
        )
        arrays[f"{label}_keys"] = keys
        arrays[f"{label}_values"] = values
    return arrays


def _destroy_l2_apply_result(result: dict[str, Any]) -> None:
    for name in ("true_residual", "applied_output", "output", "residual"):
        vector = result.get(name)
        if vector is not None:
            vector.destroy()


def _l2_vector_finite(vector: Any) -> bool:
    return bool(np.all(np.isfinite(np.asarray(vector.array))))


def _l2_source_fact(
    name: str,
    status: str,
    formula: str,
    artifact_names: dict[str, str],
    **facts: Any,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "formula": formula,
        "artifact_names": artifact_names,
        **facts,
    }


def _write_l2_record(
    root: Path,
    raw_dir: Path,
    record_path: Path,
    case: str,
    degree: int,
    mpi_size: int,
    source: dict[str, Any],
    runtime: dict[str, Any],
    rank_facts: list[dict[str, Any]],
    fixture_audit: dict[str, Any],
    source_facts: list[dict[str, Any]],
    arrays: dict[str, np.ndarray],
    control_flow: dict[str, Any],
) -> None:
    source_end = _source_identity(root, source["expected_sha"])
    closed_source = {
        **source,
        "commit_sha_end": source_end["commit_sha_end"],
        "tracked_status_end": source_end["tracked_status_end"],
        "clean_end": source_end["clean_end"],
    }
    artifacts = [
        _artifact(raw_dir / f"{name}.npy", name, array)
        for name, array in arrays.items()
    ]
    record = {
        "schema": L2_SCHEMA,
        "stage": "l2",
        "scope": "l2_positive_auxiliary_one_apply_and_fixed_cg",
        "case": case,
        "degree": int(degree),
        "mpi_size": int(mpi_size),
        "raw_dir": str(raw_dir.resolve()),
        "command": list(sys.argv),
        "source": closed_source,
        "runtime": runtime,
        "rank_facts": rank_facts,
        "fixture_audit": fixture_audit,
        "sources": source_facts,
        "control_flow": control_flow,
        "canonical_roles": {
            "source_before": "full_fe_primal",
            "source_after": "full_fe_primal",
            "pc_output": "full_fe_primal",
            "pc_repeat": "full_fe_primal",
            "residual": "full_fe_dual",
            "applied_output": "full_fe_dual",
            "true_residual": "full_fe_dual",
            "cg_solution": "full_fe_primal",
            "cg_action": "full_fe_dual",
            "cg_true_residual": "full_fe_dual",
        },
        "canonical_evidence": {
            "root_gather_evidence_only": True,
            "production_numeric_allgather": False,
        },
        "artifacts": artifacts,
        "forbidden": {
            "physical_action": False,
            "dynamic_dtn": False,
            "global_numeric_allgather": False,
            "high_order_global_aij": False,
            "global_transfer_matrix": False,
            "global_direct_coarse": False,
            "real_imag_split": False,
            "hypre_ams": False,
        },
        "production": {
            "positive_auxiliary_only": True,
            "high_order_matrix_free": True,
            "numeric_allgather": False,
            "global_high_order_aij": False,
            "global_transfer_matrix": False,
            "global_direct_coarse": False,
            "physical_action": False,
            "dynamic_dtn": False,
        },
        "status": "facts_written_not_qualified",
    }
    record_path.write_bytes(_json_bytes(record))
    print(
        json.dumps(
            {
                "record": str(record_path),
                "case": case,
                "degree": degree,
                "mpi_size": mpi_size,
                "artifact_count": len(artifacts),
                "status": record["status"],
            },
            sort_keys=True,
        )
    )


def _run_l2(args: argparse.Namespace, root: Path, comm: MPI.Comm) -> int:
    from petsc4py import PETSc
    from src.solvers.fullspace_lor_native_hx_fixture import (
        build_real_l2_positive_hx_fixture,
        destroy_l2_cg_result,
        l2_one_apply,
        l2_source_formula,
        solve_l2_cg,
    )

    if args.case not in L2_EXPECTED_CASES:
        raise ValueError(f"unsupported L2 case {args.case!r}")
    degree, case_mpi_size = L2_EXPECTED_CASES[args.case]
    if case_mpi_size != args.expected_mpi_size:
        raise ValueError("case and expected MPI size do not agree")
    raw_dir = args.raw_dir.resolve()
    record_path = args.record.resolve()
    _prepare_paths(raw_dir, record_path, comm, stage="l2")
    _append_stage_marker(raw_dir, "paths_ready", comm.rank)

    source_error: tuple[str, str] | None = None
    source: dict[str, Any] | None = None
    if comm.rank == 0:
        try:
            source = _source_identity(root, args.expected_source_sha)
        except Exception as exc:
            source_error = (type(exc).__name__, str(exc))
    source, source_error = comm.bcast((source, source_error), root=0)
    if source_error is not None:
        raise RuntimeError(f"{source_error[0]}: {source_error[1]}")
    _append_stage_marker(raw_dir, "source_identity_closed", comm.rank)
    runtime = _runtime_identity(root, args.expected_mpi_size)
    _append_stage_marker(raw_dir, "runtime_identity", comm.rank)

    fixture = build_real_l2_positive_hx_fixture(degree, comm)
    _append_stage_marker(raw_dir, "fixture_built", comm.rank)
    source_facts: list[dict[str, Any]] = []
    source_rhs: dict[str, Any] = {}
    arrays: dict[str, np.ndarray] = {}
    measured_names: list[str] = []
    control_flow: dict[str, Any] = {
        "early_stop": False,
        "stop_reason": None,
        "first_failed_source": None,
    }
    contraction_stopped = False

    for name in L2_SOURCE_NAMES:
        artifact_names = _l2_artifact_names(name)
        formula = l2_source_formula(name)
        if contraction_stopped:
            source_facts.append(
                _l2_source_fact(
                    name,
                    "not_run_by_prior_contraction_gate",
                    formula,
                    artifact_names,
                    cg={"status": "not_run_by_prior_contraction_gate"},
                )
            )
            continue

        source_vector, source_audit = fixture.build_l2_source(name)
        source_before = source_vector.copy()
        first = l2_one_apply(fixture, source_vector)
        second = l2_one_apply(fixture, source_vector)
        source_after = source_vector.copy()
        _append_stage_marker(raw_dir, f"l2_source_{name}", comm.rank)
        repeat_delta = second["output"].copy()
        repeat_delta.axpy(PETSc.ScalarType(-1.0), first["output"])
        repeat_relative = float(
            repeat_delta.norm()
            / max(first["output"].norm(), np.finfo(float).tiny)
        )
        repeat_delta.destroy()
        local_finite = all(
            _l2_vector_finite(first[key])
            and _l2_vector_finite(second[key])
            for key in ("residual", "output", "applied_output", "true_residual")
        ) and _l2_vector_finite(source_vector)
        rho = float(first["rho"])
        global_rho = float(comm.allreduce(rho, op=MPI.MAX))
        global_repeat = float(comm.allreduce(repeat_relative, op=MPI.MAX))
        global_finite = bool(comm.allreduce(int(local_finite), op=MPI.MIN))
        input_unchanged = bool(
            comm.allreduce(
                int(first["input_unchanged"] and second["input_unchanged"]),
                op=MPI.MIN,
            )
        )
        payload = _l2_canonical_payload(
            fixture,
            {
                "source_before": (source_before, "primal"),
                "source_after": (source_after, "primal"),
                "pc_output": (first["output"], "primal"),
                "pc_repeat": (second["output"], "primal"),
                "residual": (first["residual"], "dual"),
                "applied_output": (first["applied_output"], "dual"),
                "true_residual": (first["true_residual"], "dual"),
            },
        )
        merged = _l2_gather_payload(comm, payload)
        _append_stage_marker(raw_dir, "canonical_packets_gathered", comm.rank)
        if comm.rank == 0 and merged is not None:
            arrays.update(
                {
                    f"{artifact_names[label]}_{suffix}": value
                    for label in (
                        "source_before",
                        "source_after",
                        "pc_output",
                        "pc_repeat",
                        "residual",
                        "applied_output",
                        "true_residual",
                    )
                    for suffix, value in (
                        ("keys", merged[f"{label}_keys"]),
                        ("values", merged[f"{label}_values"]),
                    )
                }
            )
        comm.barrier()
        source_rhs[name] = first["residual"].copy()
        gate_reason = None
        if not global_finite:
            gate_reason = "non_finite_source_or_one_apply"
        elif not input_unchanged:
            gate_reason = "source_input_changed"
        elif global_repeat > L2_REPEAT_LIMIT:
            gate_reason = "repeat_relative_above_fixed_limit"
        elif global_rho > L2_RHO_LIMITS[name]:
            gate_reason = "rho_above_source_fixed_limit"
        source_facts.append(
            _l2_source_fact(
                name,
                "measured",
                formula,
                artifact_names,
                phase_application=source_audit["phase_application"],
                rho=global_rho,
                rho_limit=L2_RHO_LIMITS[name],
                repeat_relative=global_repeat,
                repeat_limit=L2_REPEAT_LIMIT,
                input_unchanged=input_unchanged,
                finite=global_finite,
                residual_norm=float(first["residual_norm"]),
                source_identity={
                    "before": artifact_names["source_before"],
                    "after": artifact_names["source_after"],
                    "before_role": "full_fe_primal_input_snapshot",
                    "after_role": "full_fe_primal_post_apply_snapshot",
                    "relative_limit": L2_REPEAT_LIMIT,
                },
                cg={"status": "not_run_by_prior_contraction_gate"},
            )
        )
        measured_names.append(name)
        _destroy_l2_apply_result(first)
        _destroy_l2_apply_result(second)
        source_before.destroy()
        source_after.destroy()
        source_vector.destroy()
        if gate_reason is not None:
            contraction_stopped = True
            control_flow.update(
                {
                    "early_stop": True,
                    "stop_reason": gate_reason,
                    "first_failed_source": name,
                }
            )

    if not contraction_stopped:
        _append_stage_marker(raw_dir, "l2_sources_complete", comm.rank)
        for index, name in enumerate(measured_names):
            cg = solve_l2_cg(fixture, source_rhs[name])
            local_true_residual = float(cg["true_residual_relative"])
            true_residual = float(comm.allreduce(local_true_residual, op=MPI.MAX))
            local_cg_failed = (
                int(cg["reason"]) <= 0
                or int(cg["iterations"]) > 40
                or true_residual > L2_CG_TRUE_RESIDUAL_LIMIT
            )
            cg_failed = bool(comm.allreduce(int(local_cg_failed), op=MPI.MAX))
            artifact_names = source_facts[index]["artifact_names"]
            cg_payload = _l2_canonical_payload(
                fixture,
                {
                    "cg_solution": (cg["solution"], "primal"),
                    "cg_action": (cg["action"], "dual"),
                    "cg_true_residual": (cg["true_residual"], "dual"),
                },
            )
            merged = _l2_gather_payload(comm, cg_payload)
            _append_stage_marker(raw_dir, "cg_canonical_packets_gathered", comm.rank)
            if comm.rank == 0 and merged is not None:
                arrays.update(
                    {
                        f"{artifact_names[label]}_{suffix}": value
                        for label in (
                            "cg_solution",
                            "cg_action",
                            "cg_true_residual",
                        )
                        for suffix, value in (
                            ("keys", merged[f"{label}_keys"]),
                            ("values", merged[f"{label}_values"]),
                        )
                    }
                )
            comm.barrier()
            source_facts[index]["cg"] = {
                "status": "measured",
                "reason": int(cg["reason"]),
                "iterations": int(cg["iterations"]),
                "ksp_type": "cg",
                "rtol": 1.0e-8,
                "max_it": 40,
                "reported_residual_norm": float(cg["reported_residual_norm"]),
                "true_residual_relative": true_residual,
                "true_residual_limit": L2_CG_TRUE_RESIDUAL_LIMIT,
                "pc_apply_count": int(cg["pc_context"].apply_count),
            }
            destroy_l2_cg_result(cg)
            if cg_failed:
                control_flow.update(
                    {
                        "early_stop": True,
                        "stop_reason": "cg_fact_observed_outside_fixed_limit",
                        "first_failed_cg_source": name,
                    }
                )
                for later in source_facts[index + 1 :]:
                    later["cg"] = {"status": "not_run_by_prior_cg_gate"}
                break

    for vector in source_rhs.values():
        vector.destroy()
    fixture_audit = _jsonable(fixture.audit)
    rank_facts = comm.gather(
        {"rank": int(comm.rank), "runtime": runtime},
        root=0,
    )
    if comm.rank == 0:
        _write_l2_record(
            root,
            raw_dir,
            record_path,
            args.case,
            degree,
            args.expected_mpi_size,
            source,
            runtime,
            rank_facts,
            fixture_audit,
            source_facts,
            arrays,
            control_flow,
        )
    comm.barrier()
    fixture.destroy()
    _append_stage_marker(raw_dir, "record_written", comm.rank)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("l1", "l2"), required=True)
    parser.add_argument(
        "--case",
        choices=tuple(sorted(set(EXPECTED_CASES) | set(L2_EXPECTED_CASES))),
        required=True,
    )
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    comm = MPI.COMM_WORLD
    if args.stage == "l2":
        return _run_l2(args, root, comm)
    degree, case_mpi_size = _parse_case(args.case)
    if case_mpi_size != args.expected_mpi_size:
        raise ValueError("case and expected MPI size do not agree")
    raw_dir = args.raw_dir.resolve()
    record_path = args.record.resolve()
    _prepare_paths(raw_dir, record_path, comm)
    _append_stage_marker(raw_dir, "paths_ready", comm.rank)
    source = None
    runtime = None
    periodic = None
    source_error: tuple[str, str] | None = None
    setup_error: tuple[str, str] | None = None
    try:
        if comm.rank == 0:
            try:
                source = _source_identity(root, args.expected_source_sha)
            except Exception as exc:
                source_error = (type(exc).__name__, str(exc))
        source, source_error = comm.bcast((source, source_error), root=0)
        if source_error is not None:
            raise RuntimeError(f"{source_error[0]}: {source_error[1]}")
        _append_stage_marker(raw_dir, "source_identity_closed", comm.rank)
        runtime = _runtime_identity(root, args.expected_mpi_size)
        _append_stage_marker(raw_dir, "runtime_identity", comm.rank)
        local, reference, build_wall = _build_case(degree)
        _append_stage_marker(raw_dir, "local_transfer_built", comm.rank)
        if degree in {2, 3}:
            periodic = _periodic_evidence(degree, reference, comm, raw_dir)
    except Exception as exc:
        setup_error = (type(exc).__name__, str(exc))
    failed = comm.allreduce(int(setup_error is not None), op=MPI.MAX)
    if failed:
        raise RuntimeError(setup_error[1] if setup_error is not None else "another MPI rank failed")
    rank_facts = comm.gather(
        {
            "rank": int(comm.rank),
            "runtime": runtime,
            "local_audit": _jsonable(local.audit),
            "reference_audit": _jsonable(reference.audit),
        },
        root=0,
    )
    if comm.rank == 0:
        _write_success(
            root,
            raw_dir,
            record_path,
            args.case,
            degree,
            args.expected_mpi_size,
            source,
            runtime,
            rank_facts,
            local,
            reference,
            build_wall,
            periodic,
        )
    comm.barrier()
    _append_stage_marker(raw_dir, "record_written", comm.rank)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
