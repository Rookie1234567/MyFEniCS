"""Thin R3 worker for the current residual at the historical W5 primal state.

Path A (the historical W5 dual) is deliberately not qualified.  Path B maps
only the old primal solution through the existing physical canonical API, then
evaluates the current volume-plus-dynamic-DtN action.  This worker writes raw
canonical packets below an ignored artifact directory; the checker derives all
numeric gates from those packets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from typing import Any, Callable, Iterable, Mapping

import numpy as np

from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    read_canonical_manifest,
    read_canonical_packet_shards,
    write_canonical_manifest,
    write_canonical_packet_shard,
)


R3_SCHEMA = "task038.full3d.iterative.r3.residual-record.v1"
R3_PROFILE = "full3d_scalable_v1"
R3_SOURCE_NAME = "CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE"
PATH_A_SOURCE_NAME = "HISTORICAL_W5_LONG_TAIL_DUAL"
TEMPLATE_RELATIVE_PATH = "input/templates/full3d_iterative_example.dat"
EXPECTED_INPUT_BYTES = 2119
EXPECTED_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
EXPECTED_RESOLVED_BYTES = 4076
EXPECTED_RESOLVED_SHA256 = "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
EXPECTED_PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
EXPECTED_MODE_COUNT = 80
EXPECTED_MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
OLD_SOURCE_SHA = "41cbbd454eb8336d9ea5378ed618447acfc60aac"
OLD_SOLUTION_FACTS = {
    "file_sha256": "d2a5a7e7b94a73d5212bc693d43282cace2883aadd0bb66780a3f8ae7b9e535e",
    "array_sha256": "620b5e496536d69c0bc471731b09a15424c29044e6836881ccd85340cbee0c39",
    "shape": [173802],
    "dtype": "complex128",
}
OLD_RESIDUAL_FACTS = {
    "file_sha256": "4166665f2e3c302f0645d9581856ec1bc433de4679540e45f98eb1e161093cc6",
    "array_sha256": "35de8f03a1fdf4c410cff33ceee44a31831df418443c7534650308505114de98",
    "shape": [173802],
    "dtype": "complex128",
}


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
        return [float(value.real), float(value.imag)]
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    return str(value)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).view(np.uint8)).hexdigest()


def _source_identity(root: Path) -> dict[str, str]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "--git-dir=.git-codex", "--work-tree=.", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Git identity probe failed")
        return result.stdout.strip()

    return {
        "commit_sha": git("rev-parse", "HEAD"),
        "tracked_status": git("status", "--short", "--untracked-files=all"),
    }


def _prepare_raw_dir(raw_dir: Path, record_path: Path, comm: Any) -> None:
    error: tuple[str, str] | None = None
    if comm.rank == 0:
        try:
            if raw_dir.exists() or record_path.exists():
                raise FileExistsError("R3 raw directory or record already exists")
            raw_dir.mkdir(parents=True)
        except FileExistsError as exc:
            error = ("FileExistsError", str(exc))
        except OSError as exc:
            error = ("OSError", str(exc))
    error = comm.bcast(error, root=0)
    if error is not None:
        if error[0] == "FileExistsError":
            raise FileExistsError(error[1])
        raise OSError(error[1])
    comm.barrier()


def _write_bytes_artifact(
    raw_dir: Path,
    relative_path: str,
    payload: bytes,
    kind: str,
    comm: Any,
) -> dict[str, Any]:
    path = raw_dir / relative_path
    if comm.rank == 0:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        descriptor = {
            "kind": kind,
            "relative_path": relative_path,
            "bytes": int(len(payload)),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    else:
        descriptor = None
    comm.barrier()
    return comm.bcast(descriptor, root=0)


def _write_packet_artifact(
    raw_dir: Path,
    label: str,
    packets: Iterable[tuple[tuple[Any, ...], complex]],
    audit: Mapping[str, Any],
    role: str,
    comm: Any,
) -> dict[str, Any]:
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
            extractor_audit=_jsonable(dict(audit)),
        )
        manifest_path = directory / f"{label}.manifest.json"
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        descriptor = {
            "kind": "canonical_packet_manifest",
            "role": role,
            "manifest_relative_path": str(manifest_path.relative_to(raw_dir)),
            "manifest_sha256": manifest_sha,
            "packet_count": int(manifest["global_summed_packet_count"]),
            "duplicate_count": int(manifest["summed_local_duplicate_count"]),
            "finite": bool(
                all(item.get("packet_finite", True) for item in gathered)
            ),
        }
    return comm.bcast(descriptor, root=0)


def _read_input_primal_manifest(path: Path) -> tuple[dict[str, Any], tuple[Any, ...]]:
    manifest = read_canonical_manifest(path)
    if manifest.get("role") != "full_fe" or int(manifest.get("mpi_size", 0)) != 1:
        raise RuntimeError("MPI2 requires a single-rank full_fe primal manifest")
    shards = tuple(path.parent / item["filename"] for item in manifest["per_rank_shards"])
    packets = read_canonical_packet_shards(
        shards,
        tuple(item["file_sha256"] for item in manifest["per_rank_shards"]),
    )
    return manifest, packets


def _load_old_array(path: Path, facts: Mapping[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    array = np.asarray(np.load(path, allow_pickle=False))
    observed = {
        "path": str(path.resolve()),
        "bytes": int(path.stat().st_size),
        "file_sha256": _sha256_path(path),
        "array_sha256": _array_sha256(array),
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "finite": bool(np.all(np.isfinite(array))),
    }
    for key, expected in facts.items():
        if observed.get(key) != expected:
            raise RuntimeError(f"historical artifact identity mismatch for {path.name}: {key}")
    if not observed["finite"]:
        raise RuntimeError(f"historical artifact is not finite: {path}")
    return np.asarray(array, dtype=np.complex128), observed


def _current_input(root: Path, input_path: Path) -> tuple[Any, Any, bytes, dict[str, Any]]:
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.io.resolved_config import resolved_config_bytes

    specification = load_and_resolve(input_path)
    resolved = resolved_config_bytes(specification)
    if len(specification.raw_input_bytes) != EXPECTED_INPUT_BYTES:
        raise RuntimeError("frozen input byte count changed")
    if specification.input_sha256 != EXPECTED_INPUT_SHA256:
        raise RuntimeError("frozen input SHA changed")
    if len(resolved) != EXPECTED_RESOLVED_BYTES:
        raise RuntimeError("frozen resolved-config byte count changed")
    if hashlib.sha256(resolved).hexdigest() != EXPECTED_RESOLVED_SHA256:
        raise RuntimeError("frozen resolved-config SHA changed")
    if specification.physical_model_sha256 != EXPECTED_PHYSICAL_MODEL_SHA256:
        raise RuntimeError("frozen physical-model SHA changed")
    cfg = simulation_config_3d_from_normalized(json.loads(resolved))
    if (
        float(cfg.lambda0) != 13.5
        or int(cfg.nedelec_degree) != 6
        or float(cfg.mesh_target_size) != 10.0
        or cfg.stage4_boundary_model != "dtn_port"
    ):
        raise RuntimeError("R3 requires the frozen p6/h10 dynamic-DtN input")
    facts = {
        "template_relative_path": str(input_path.relative_to(root)),
        "template_bytes": len(specification.raw_input_bytes),
        "template_sha256": specification.input_sha256,
        "resolved_config_bytes": len(resolved),
        "resolved_config_sha256": hashlib.sha256(resolved).hexdigest(),
        "physical_model_sha256": specification.physical_model_sha256,
    }
    return specification, cfg, resolved, facts


def _set_historical_solution(space: Any, array: np.ndarray) -> Any:
    from dolfinx import fem

    field = fem.Function(space)
    start, stop = map(int, field.x.petsc_vec.getOwnershipRange())
    if stop - start != field.x.array.size - int(space.dofmap.index_map.num_ghosts):
        raise RuntimeError("historical solution owned layout does not close")
    field.x.array[: stop - start] = array[start:stop]
    field.x.scatter_forward()
    return field


def _relative_vec(left: Any, right: Any) -> float:
    difference = left.copy()
    difference.axpy(-1.0, right)
    try:
        return float(difference.norm() / max(right.norm(), 1.0e-300))
    finally:
        difference.destroy()


def _rss_bytes() -> int:
    with Path("/proc/self/status").open(encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("VmRSS is unavailable")


def _swap_bytes() -> int:
    with Path("/proc/self/status").open(encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("VmSwap:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("VmSwap is unavailable")


def _old_residual_diagnostic(
    old_dir: Path, fresh: Any, fresh_packets: Iterable[tuple[Any, complex]]
) -> dict[str, Any]:
    old, facts = _load_old_array(
        old_dir / "m6b_iter200_residual.npy", OLD_RESIDUAL_FACTS
    )
    current = np.asarray(fresh.getArray(readonly=True), dtype=np.complex128)
    if current.shape != old.shape:
        raise RuntimeError("current MPI1 residual row layout differs from old residual")
    old_norm = float(np.linalg.norm(old))
    current_norm = float(np.linalg.norm(current))
    difference = old - current
    cosine = abs(np.vdot(old, current)) / max(old_norm * current_norm, 1.0e-300)
    dimension_energy: dict[str, float] = {}
    for key, value in fresh_packets:
        dimension = str(key[1])
        dimension_energy[dimension] = dimension_energy.get(dimension, 0.0) + abs(complex(value)) ** 2
    return {
        "status": "diagnostic_only",
        "source": "old m6b_iter200_residual.npy versus fresh current residual row values",
        "old_facts": facts,
        "old_norm": old_norm,
        "fresh_norm": current_norm,
        "difference_norm": float(np.linalg.norm(difference)),
        "cosine_abs": float(cosine),
        "angle_radians": float(np.arccos(np.clip(cosine, 0.0, 1.0))),
        "fresh_canonical_dimension_energy": dimension_energy,
        "old_dimension_energy": "unavailable_without_qualified_old_dual_map",
    }


def _make_surface_assemblers(
    function_space: Any, mesh_data: Any, cfg: Any, quadrature_degree: int
) -> dict[tuple[str, int], Any]:
    """Create the four current production facet assemblers for top/bottom sides."""

    from src.solvers.dtn_port_3d import _ReusableSurfaceComponentAssembler

    return {
        (side, component): _ReusableSurfaceComponentAssembler(
            function_space,
            mesh_data,
            cfg.tags.z_max if side == "top" else cfg.tags.z_min,
            component,
            quadrature_degree=quadrature_degree,
        )
        for side in ("top", "bottom")
        for component in (0, 1)
    }


def _run_case(
    *,
    root: Path,
    input_path: Path,
    old_dir: Path,
    raw_dir: Path,
    record_path: Path,
    expected_source_sha: str,
    mpi1_primal_manifest: Path | None,
) -> dict[str, Any]:
    from mpi4py import MPI
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_forms import _build_variational_forms
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.dtn_port_3d import (
        _assemble_mpc_vector,
        _dtn_surface_quadrature_degree,
        _incident_projection_onto_top_mode,
        _incident_top_traction_form,
    )
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_ordered_mode_manifest,
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from src.solvers.fullspace_mpc_action import build_fullspace_mpc_form_action
    from src.solvers.fullspace_physical_action import FullspacePhysicalAction
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
        extract_canonical_full_fe_packets,
        reconstruct_canonical_full_fe_function,
    )
    from petsc4py import PETSc

    comm = MPI.COMM_WORLD
    start_identity = _source_identity(root)
    if start_identity["commit_sha"] != expected_source_sha or start_identity["tracked_status"]:
        raise RuntimeError("R3 source preflight is not clean at start")
    _prepare_raw_dir(raw_dir, record_path, comm)
    specification, cfg, resolved_bytes, input_facts = _current_input(root, input_path)
    modes, _dynamic_rows, _dynamic_sha = build_dynamic_mode_inventory(cfg)
    _dynamic_rows, dynamic_manifest_bytes, dynamic_manifest_sha = build_ordered_mode_manifest(
        modes, cfg
    )
    if len(modes) != EXPECTED_MODE_COUNT:
        raise RuntimeError(f"frozen dynamic mode count changed: {len(modes)}")

    if comm.rank == 0:
        (raw_dir / "benchmark_input").mkdir(parents=True, exist_ok=True)
        (raw_dir / "benchmark_input" / "full3d_iterative_example.dat").write_bytes(
            specification.raw_input_bytes
        )
        (raw_dir / "benchmark_input" / "resolved_config.json").write_bytes(resolved_bytes)
        (raw_dir / "mode_manifest.json").write_bytes(dynamic_manifest_bytes)
    comm.barrier()
    mode_descriptor = {
        "kind": "ordered_mode_manifest",
        "relative_path": "mode_manifest.json",
        "bytes": len(dynamic_manifest_bytes),
        "sha256": _sha256_path(raw_dir / "mode_manifest.json") if comm.rank == 0 else None,
    }
    mode_descriptor = comm.bcast(mode_descriptor if comm.rank == 0 else None, root=0)
    if mode_descriptor["sha256"] != EXPECTED_MODE_MANIFEST_SHA256 or dynamic_manifest_sha != EXPECTED_MODE_MANIFEST_SHA256:
        raise RuntimeError("frozen dynamic mode manifest identity changed")

    mesh_data = build_airbox_mesh_3d(cfg, raw_dir / "mesh")
    raw_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    space = floquet_data.mpc.function_space
    quadrature_degree = _dtn_surface_quadrature_degree(cfg, list(modes))
    surface_assemblers = _make_surface_assemblers(
        raw_space, mesh_data, cfg, quadrature_degree
    )
    carrier = build_fullspace_dtn_carrier_from_surface(
        modes, surface_assemblers, floquet_data.mpc, cfg
    )
    dtn_action = build_fullspace_dtn_action(carrier, comm=comm)
    bilinear_form, _rhs = _build_variational_forms(
        mesh_data.mesh, mesh_data, cfg, raw_space, field_formulation="total_field"
    )
    volume_action = build_fullspace_mpc_form_action(
        bilinear_form, raw_space, mpc=floquet_data.mpc
    )
    physical_action = FullspacePhysicalAction(volume_action, dtn_action)
    base_incident = _assemble_mpc_vector(
        _incident_top_traction_form(raw_space, mesh_data, cfg),
        floquet_data.mpc,
        quadrature_degree=quadrature_degree,
    )
    amplitudes = tuple(_incident_projection_onto_top_mode(mode, cfg) for mode in modes)
    current_rhs = base_incident.duplicate()
    physical_action.compose_physical_rhs(base_incident, amplitudes, current_rhs)

    historical_facts: dict[str, Any]
    input_manifest_facts: dict[str, Any] | None = None
    historical_field = None
    roundtrip_field = None
    old_solution = None
    if comm.size == 1:
        old_solution, historical_facts = _load_old_array(
            old_dir / "m6b_iter200_solution.npy", OLD_SOLUTION_FACTS
        )
        if old_solution.size != int(space.dofmap.index_map.size_global):
            raise RuntimeError("old solution size does not match current finalized rows")
        historical_field = _set_historical_solution(space, old_solution)
        primal_packets, primal_audit = extract_canonical_full_fe_packets(
            space, historical_field.x.petsc_vec, floquet_data
        )
        primal_source = _write_packet_artifact(
            raw_dir, "mapped_solution", primal_packets, primal_audit, "full_fe", comm
        )
        roundtrip_field = reconstruct_canonical_full_fe_function(
            space, primal_packets, floquet_data
        )
        roundtrip_packets, roundtrip_audit = extract_canonical_full_fe_packets(
            space, roundtrip_field.x.petsc_vec, floquet_data
        )
        primal_roundtrip = _write_packet_artifact(
            raw_dir,
            "mapped_solution_roundtrip",
            roundtrip_packets,
            roundtrip_audit,
            "full_fe",
            comm,
        )
        x = roundtrip_field.x.petsc_vec
        primal_roundtrip_error = _relative_vec(x, historical_field.x.petsc_vec)
    else:
        if mpi1_primal_manifest is None:
            raise RuntimeError("MPI2 requires --mpi1-primal-manifest")
        input_manifest, input_packets = _read_input_primal_manifest(
            mpi1_primal_manifest
        )
        input_manifest_facts = {
            "path": str(mpi1_primal_manifest.resolve()),
            "sha256": _sha256_path(mpi1_primal_manifest),
            "packet_count": int(input_manifest["global_summed_packet_count"]),
            "role": input_manifest["role"],
        }
        mapped_field = reconstruct_canonical_full_fe_function(
            space, input_packets, floquet_data
        )
        mapped_packets, mapped_audit = extract_canonical_full_fe_packets(
            space, mapped_field.x.petsc_vec, floquet_data
        )
        primal_source = _write_packet_artifact(
            raw_dir, "mapped_solution", mapped_packets, mapped_audit, "full_fe", comm
        )
        primal_roundtrip = None
        x = mapped_field.x.petsc_vec
        primal_roundtrip_error = None
        roundtrip_field = mapped_field

    action_first = x.duplicate()
    action_repeat = x.duplicate()
    residual = None
    try:
        apply_telemetry: list[dict[str, Any]] = []
        for target in (action_first, action_repeat):
            started = time.perf_counter()
            physical_action.apply(x, target)
            apply_telemetry.append(
                {
                    "elapsed_seconds": float(time.perf_counter() - started),
                    "rank_max_current_rss_bytes": int(
                        comm.allreduce(_rss_bytes(), op=MPI.MAX)
                    ),
                    "rank_max_current_swap_bytes": int(
                        comm.allreduce(_swap_bytes(), op=MPI.MAX)
                    ),
                }
            )
        residual = current_rhs.copy()
        residual.axpy(PETSc.ScalarType(-1.0), action_first)

        rhs_packets, rhs_audit = extract_canonical_full_fe_dual_packets(
            space, floquet_data.mpc, current_rhs
        )
        action_packets, action_audit = extract_canonical_full_fe_dual_packets(
            space, floquet_data.mpc, action_first
        )
        repeat_packets, repeat_audit = extract_canonical_full_fe_dual_packets(
            space, floquet_data.mpc, action_repeat
        )
        residual_packets, residual_audit = extract_canonical_full_fe_dual_packets(
            space, floquet_data.mpc, residual
        )
        artifacts = {
            "input_template": {
                "kind": "input_template",
                "relative_path": "benchmark_input/full3d_iterative_example.dat",
                "bytes": len(specification.raw_input_bytes),
                "sha256": specification.input_sha256,
            },
            "resolved_config": {
                "kind": "resolved_config",
                "relative_path": "benchmark_input/resolved_config.json",
                "bytes": len(resolved_bytes),
                "sha256": hashlib.sha256(resolved_bytes).hexdigest(),
            },
            "mode_manifest": mode_descriptor,
            "primal_source": primal_source,
            "primal_roundtrip": primal_roundtrip,
            "current_rhs": _write_packet_artifact(
                raw_dir, "current_rhs", rhs_packets, rhs_audit, "full_fe_dual", comm
            ),
            "action": _write_packet_artifact(
                raw_dir, "action", action_packets, action_audit, "full_fe_dual", comm
            ),
            "action_repeat": _write_packet_artifact(
                raw_dir,
                "action_repeat",
                repeat_packets,
                repeat_audit,
                "full_fe_dual",
                comm,
            ),
            "residual": _write_packet_artifact(
                raw_dir,
                "residual",
                residual_packets,
                residual_audit,
                "full_fe_dual",
                comm,
            ),
        }
        operator_audit = _jsonable(dict(physical_action.audit))
        operator_descriptor = _write_bytes_artifact(
            raw_dir,
            "operator_audit.json",
            _canonical_json(operator_audit) + b"\n",
            "operator_audit",
            comm,
        )
        old_diagnostic = (
            _old_residual_diagnostic(old_dir, residual, residual_packets)
            if comm.size == 1
            else {"status": "not_run_mpi2", "reason": "MPI2 did not read old raw residual"}
        )
        end_identity = _source_identity(root)
        record = {
            "schema": R3_SCHEMA,
            "profile": R3_PROFILE,
            "case": "p6-h10",
            "source_name": R3_SOURCE_NAME,
            "path_a": {
                "status": "NOT_QUALIFIED",
                "source_name": PATH_A_SOURCE_NAME,
                "reason": "R1 old mandatory physics/Floquet/orientation fields unavailable; R2 classified OLD_W5_PHYSICAL_DUAL_NOT_CURRENT_AUTHORITY",
                "fit_or_scaling": "forbidden_and_not_attempted",
            },
            "path_b": {
                "status": "current_operator_at_mapped_historical_w5_primal_state",
                "boundary": "current b_current - A_current x_old_mapped; not the current PC 200-step residual",
                "source_name": R3_SOURCE_NAME,
                "old_source_sha": OLD_SOURCE_SHA,
                "empirical_scaling": False,
            },
            "source": {
                "expected_sha": expected_source_sha,
                "commit_sha_start": start_identity["commit_sha"],
                "commit_sha_end": end_identity["commit_sha"],
                "tracked_status_start": start_identity["tracked_status"],
                "tracked_status_end": end_identity["tracked_status"],
            },
            "raw_dir": str(raw_dir),
            "input": input_facts,
            "historical_solution": historical_facts
            if comm.size == 1
            else {"status": "not_read_mpi2", "mpi1_manifest": input_manifest_facts},
            "mpi": {
                "size": int(comm.size),
                "mpi1_primal_manifest": input_manifest_facts,
            },
            "model": {
                "wavelength_nm": float(cfg.lambda0),
                "nedelec_degree": int(cfg.nedelec_degree),
                "mesh_target_nm": float(cfg.mesh_target_size),
                "mode_count": len(modes),
                "mode_manifest_sha256": EXPECTED_MODE_MANIFEST_SHA256,
            },
            "artifacts": artifacts,
            "operator": {
                "audit": operator_audit,
                "audit_artifact": operator_descriptor,
                "audit_sha256": operator_descriptor["sha256"],
            },
            "observations": {
                "primal_roundtrip_relative_l2": primal_roundtrip_error,
                "apply_count": 2,
                "apply_telemetry": apply_telemetry,
                "swap_required_bytes": 0,
            },
            "old_residual_diagnostic": old_diagnostic,
            "resource": {
                "semantics": "rank-max current self RSS and VmSwap sampled immediately after each apply",
                "process_tree": "not_measured_r3",
            },
            "pde_solved": False,
            "ksp_created": False,
        }
        if comm.rank == 0:
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_path.write_bytes(_canonical_json(record) + b"\n")
        comm.barrier()
        return record
    finally:
        if residual is not None:
            residual.destroy()
        action_repeat.destroy()
        action_first.destroy()
        base_incident.destroy()
        current_rhs.destroy()
        physical_action.destroy()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R3 current residual authority worker")
    parser.add_argument("--input-template", type=Path, required=True)
    parser.add_argument("--old-w5-dir", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--mpi1-primal-manifest", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    root = Path(__file__).resolve().parents[1]
    from petsc4py import PETSc

    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise RuntimeError("R3 requires PETSc complex128")
    _run_case(
        root=root,
        input_path=args.input_template.resolve(),
        old_dir=args.old_w5_dir.resolve(),
        raw_dir=args.raw_dir.resolve(),
        record_path=args.record.resolve(),
        expected_source_sha=args.expected_source_sha,
        mpi1_primal_manifest=(
            None
            if args.mpi1_primal_manifest is None
            else args.mpi1_primal_manifest.resolve()
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
