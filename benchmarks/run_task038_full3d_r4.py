"""Thin Candidate-A R4 worker.

The worker builds the current full-space volume-plus-DtN action and the
owner-local two-slab sweep.  It writes only compact JSON plus canonical packet
shards below an ignored raw directory.  The independent checker, rather than
this worker's status field, decides the numerical gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from typing import Any, Iterable, Mapping

import numpy as np

from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    read_canonical_manifest,
    read_canonical_packet_shards,
    write_canonical_manifest,
    write_canonical_packet_shard,
)


R4_SCHEMA = "task038.full3d.iterative.r4.candidate-a-record.v1"
R4_PROFILE = "full3d_scalable_v1"
R4_SOURCE_NAMES = (
    "physical_rhs",
    "gradient",
    "curl",
    "checkerboard",
    "r3_qualified_long_tail",
)
R3_LONG_TAIL_MANIFEST_SHA256 = (
    "62c7824e1032b1a14078d158b0e403b9087dc862bf00386fdce08535e4d76dce"
)
R3_LONG_TAIL_SOURCE_SHA = "2c8fca90c7300b85b30021081868b699c0b306d2"
R3_LONG_TAIL_SOURCE_NAME = "CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE"
R4_GATE_TOLERANCES = {
    "fixture": 1.0e-12,
    "action": 1.0e-11,
    "repeat": 1.0e-12,
    "mpi_identity": 1.0e-12,
}
R4_NORM_DEFINITION = "canonical full_fe_dual coefficient L2"
R4_SOURCE_GENERATION_FORMULAS = {
    "physical_rhs": "current_dtn_compose_physical_rhs(base_incident_traction,frozen_mode_amplitudes)",
    "gradient": "fixed_gradient_of_sin_product_then_current_A",
    "curl": "curl_of_A=(0,0,sin_x*sin_y*sin_z)_then_current_A",
    "checkerboard": "fixed_8_cycle_checkerboard_then_current_A",
    "r3_qualified_long_tail": "R3_canonical_full_fe_dual_reconstruct_no_empirical_scaling",
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


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


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
    failure: tuple[str, str] | None = None
    if comm.rank == 0:
        try:
            if raw_dir.exists() or record_path.exists():
                raise FileExistsError("R4 raw directory or record already exists")
            raw_dir.mkdir(parents=True)
        except FileExistsError as exc:
            failure = ("FileExistsError", str(exc))
        except OSError as exc:
            failure = ("OSError", str(exc))
    failure = comm.bcast(failure, root=0)
    if failure is not None:
        if failure[0] == "FileExistsError":
            raise FileExistsError(failure[1])
        raise OSError(failure[1])
    comm.barrier()


def _write_packet_artifact(
    raw_dir: Path,
    label: str,
    packets: Iterable[tuple[tuple[Any, ...], complex]],
    audit: Mapping[str, Any],
    role: str,
    comm: Any,
) -> dict[str, Any]:
    """Write one vector once, with one shard per rank and one manifest."""

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


def _rss_bytes() -> int:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("VmRSS is unavailable")


def _swap_bytes() -> int:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmSwap:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("VmSwap is unavailable")


def _resolve_case(root: Path, input_path: Path, degree: int, mesh_target: float):
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.io.resolved_config import resolved_config_bytes
    from dataclasses import replace

    specification = load_and_resolve(input_path)
    resolved = resolved_config_bytes(specification)
    cfg = simulation_config_3d_from_normalized(json.loads(resolved))
    return specification, replace(
        cfg,
        nedelec_degree=int(degree),
        mesh_target_size=float(mesh_target),
    ), resolved


def _make_surface_assemblers(function_space: Any, mesh_data: Any, cfg: Any, qdegree: int):
    from src.solvers.dtn_port_3d import _ReusableSurfaceComponentAssembler

    return {
        (side, component): _ReusableSurfaceComponentAssembler(
            function_space,
            mesh_data,
            cfg.tags.z_max if side == "top" else cfg.tags.z_min,
            component,
            quadrature_degree=qdegree,
        )
        for side in ("top", "bottom")
        for component in (0, 1)
    }


def _analytic_primal(space: Any, floquet_data: Any, cfg: Any, family: str):
    from dolfinx import fem

    field = fem.Function(space)
    span = max(float(cfg.domain_z_max - cfg.domain_z_min), 1.0)
    kx = 2.0 * np.pi / max(float(cfg.x_max - cfg.x_min), 1.0)
    ky = 2.0 * np.pi / max(float(cfg.y_max - cfg.y_min), 1.0)
    kz = 2.0 * np.pi / span

    def values(x: np.ndarray) -> np.ndarray:
        xx, yy, zz = x[0], x[1], x[2]
        sx = np.sin(kx * (xx - cfg.x_min))
        cx = np.cos(kx * (xx - cfg.x_min))
        sy = np.sin(ky * (yy - cfg.y_min))
        cy = np.cos(ky * (yy - cfg.y_min))
        sz = np.sin(kz * (zz - cfg.domain_z_min))
        cz = np.cos(kz * (zz - cfg.domain_z_min))
        if family == "gradient":
            return np.vstack((kx * cx * sy * sz, ky * sx * cy * sz, kz * sx * sy * cz))
        if family == "curl":
            # A=(0,0,sx*sy*sz), so this is exactly curl(A).
            return np.vstack((ky * sx * cy * sz, -kx * cx * sy * sz, np.zeros_like(sx)))
        if family == "checkerboard":
            high_x = np.sin(8.0 * kx * (xx - cfg.x_min))
            high_y = np.sin(8.0 * ky * (yy - cfg.y_min))
            high_z = np.sin(8.0 * kz * (zz - cfg.domain_z_min))
            return np.vstack((high_x * high_y * high_z, high_y * high_z, high_z * high_x))
        raise ValueError(family)

    field.interpolate(values)
    field.x.scatter_forward()
    floquet_data.mpc.homogenize(field)
    floquet_data.mpc.backsubstitution(field)
    field.x.scatter_forward()
    return field


def _read_long_tail(path: Path):
    manifest = read_canonical_manifest(path, R3_LONG_TAIL_MANIFEST_SHA256)
    shards = tuple(path.parent / item["filename"] for item in manifest["per_rank_shards"])
    packets = read_canonical_packet_shards(
        shards,
        tuple(item["file_sha256"] for item in manifest["per_rank_shards"]),
    )
    return manifest, packets


def _build_case(root: Path, args: argparse.Namespace):
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
    from src.solvers.fullspace_slab_interface import (
        FirstOrderImpedanceTransmission,
        build_fullspace_slab_interface,
    )
    from src.solvers.fullspace_sweep import (
        build_candidate_a,
        build_fullspace_slab_plan,
        build_slab_volume_actions,
        candidate_a_audit,
    )

    comm = MPI.COMM_WORLD
    specification, cfg, resolved = _resolve_case(
        root, args.input, args.degree, args.mesh_target
    )
    modes, _dynamic_rows, _dynamic_sha = build_dynamic_mode_inventory(cfg)
    mode_rows, mode_bytes, mode_sha = build_ordered_mode_manifest(modes, cfg)
    mesh_data = build_airbox_mesh_3d(cfg, args.raw_dir / "mesh")
    raw_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    space = floquet_data.mpc.function_space
    topology = build_fullspace_slab_interface(space, mesh_data, floquet_data, cfg)
    qdegree = _dtn_surface_quadrature_degree(cfg, list(modes))
    assemblers = _make_surface_assemblers(raw_space, mesh_data, cfg, qdegree)
    carrier = build_fullspace_dtn_carrier_from_surface(
        modes, assemblers, floquet_data.mpc, cfg
    )
    dtn_action = build_fullspace_dtn_action(carrier, comm=comm)
    bilinear, _rhs = _build_variational_forms(
        mesh_data.mesh, mesh_data, cfg, raw_space, field_formulation="total_field"
    )
    volume_action = build_fullspace_mpc_form_action(
        bilinear, raw_space, mpc=floquet_data.mpc
    )
    physical_action = FullspacePhysicalAction(volume_action, dtn_action)
    transmission = FirstOrderImpedanceTransmission(
        space, topology, mpc=floquet_data.mpc
    )
    plan = build_fullspace_slab_plan(topology)
    slab_volume_actions = build_slab_volume_actions(
        plan,
        topology,
        mesh_data,
        raw_space,
        floquet_data.mpc,
        cfg,
    )
    sweep = build_candidate_a(
        plan,
        slab_volume_actions,
        dtn_action,
        transmission,
        physical_action,
    )
    base = _assemble_mpc_vector(
        _incident_top_traction_form(raw_space, mesh_data, cfg),
        floquet_data.mpc,
        quadrature_degree=qdegree,
    )
    amplitudes = tuple(_incident_projection_onto_top_mode(mode, cfg) for mode in modes)
    if args.source == "physical_rhs":
        source = base.duplicate()
        physical_action.compose_physical_rhs(base, amplitudes, source)
        source_field = None
    elif args.source in {"gradient", "curl", "checkerboard"}:
        source_field = _analytic_primal(space, floquet_data, cfg, args.source)
        source = source_field.x.petsc_vec.duplicate()
        physical_action.apply(source_field.x.petsc_vec, source)
    else:
        from src.solvers.hcurl_canonical_vector_dolfinx import (
            reconstruct_canonical_full_fe_dual_vector,
        )

        if args.long_tail_manifest is None:
            raise ValueError("long-tail source requires --long-tail-manifest")
        if comm.size != 1:
            manifest = read_canonical_manifest(args.long_tail_manifest, R3_LONG_TAIL_MANIFEST_SHA256)
            shards = tuple(args.long_tail_manifest.parent / item["filename"] for item in manifest["per_rank_shards"])
            packets = read_canonical_packet_shards(shards, tuple(item["file_sha256"] for item in manifest["per_rank_shards"]))
        else:
            _manifest, packets = _read_long_tail(args.long_tail_manifest)
        source = reconstruct_canonical_full_fe_dual_vector(
            space, floquet_data.mpc, packets
        )
        source_field = None
    base.destroy()
    source_generation_apply_count = int(physical_action.audit["apply_count"])
    return {
        "comm": comm,
        "cfg": cfg,
        "specification": specification,
        "resolved": resolved,
        "space": space,
        "modes": modes,
        "mode_rows": mode_rows,
        "mode_bytes": mode_bytes,
        "mode_sha": mode_sha,
        "mesh_data": mesh_data,
        "floquet_data": floquet_data,
        "topology": topology,
        "physical_action": physical_action,
        "transmission": transmission,
        "sweep": sweep,
        "source": source,
        "source_field": source_field,
        "source_generation_apply_count": source_generation_apply_count,
        "candidate_audit": candidate_a_audit(),
    }


def _write_case(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
        extract_canonical_full_fe_packets,
    )

    comm = _build_case(root, args)
    source = comm["source"]
    sweep = comm["sweep"]
    space = comm["space"]
    mpc = comm["floquet_data"].mpc
    mpi = comm["comm"]
    try:
        first = sweep.sweep(source)
        second = sweep.sweep(source)
        mode_path = args.raw_dir / "mode_manifest.json"
        if mpi.rank == 0:
            mode_path.write_bytes(comm["mode_bytes"])
        mpi.barrier()
        mode_descriptor = None
        if mpi.rank == 0:
            mode_descriptor = {
                "relative_path": "mode_manifest.json",
                "bytes": len(comm["mode_bytes"]),
                "sha256": _sha256_path(mode_path),
            }
        mode_descriptor = mpi.bcast(mode_descriptor, root=0)
        source_packets, source_audit = extract_canonical_full_fe_dual_packets(space, mpc, source)
        action_packets, action_audit = extract_canonical_full_fe_dual_packets(space, mpc, first.action_delta)
        residual_packets, residual_audit = extract_canonical_full_fe_dual_packets(space, mpc, first.residual)
        repeat_packets, repeat_audit = extract_canonical_full_fe_dual_packets(space, mpc, second.residual)
        delta_packets, delta_audit = extract_canonical_full_fe_packets(
            space, first.delta, comm["floquet_data"]
        )
        artifacts = {
            "source": _write_packet_artifact(args.raw_dir, "source", source_packets, source_audit, "full_fe_dual", mpi),
            "delta": _write_packet_artifact(args.raw_dir, "delta", delta_packets, delta_audit, "full_fe", mpi),
            "action_delta": _write_packet_artifact(args.raw_dir, "action_delta", action_packets, action_audit, "full_fe_dual", mpi),
            "r_new": _write_packet_artifact(args.raw_dir, "r_new", residual_packets, residual_audit, "full_fe_dual", mpi),
            "repeat_r_new": _write_packet_artifact(args.raw_dir, "repeat_r_new", repeat_packets, repeat_audit, "full_fe_dual", mpi),
        }
        record = {
            "schema": R4_SCHEMA,
            "source_name": args.source,
            "source": {
                "name": args.source,
                "generation": "current_physical_rhs" if args.source == "physical_rhs" else "fixed_analytic_primal_then_current_A" if args.source != "r3_qualified_long_tail" else R3_LONG_TAIL_SOURCE_NAME,
                "generation_formula": R4_SOURCE_GENERATION_FORMULAS[args.source],
                "empirical_scaling": False,
                "norm_definition": R4_NORM_DEFINITION,
                "long_tail_source_sha": R3_LONG_TAIL_SOURCE_SHA if args.source == "r3_qualified_long_tail" else None,
                "long_tail_manifest_sha256": R3_LONG_TAIL_MANIFEST_SHA256 if args.source == "r3_qualified_long_tail" else None,
            },
            "norm_definition": R4_NORM_DEFINITION,
            "source_generation": {
                "physical_action_apply_count": int(comm["source_generation_apply_count"]),
                "generation_formula": R4_SOURCE_GENERATION_FORMULAS[args.source],
                "empirical_scaling": False,
            },
            "source_identity": {
                "expected_sha": args.expected_source_sha,
                "start": args._source_start,
                "end": _source_identity(root),
            },
            "raw_dir": str(args.raw_dir.resolve()),
            "mpi_size": int(mpi.size),
            "degree": int(comm["cfg"].nedelec_degree),
            "mesh_target_nm": float(comm["cfg"].mesh_target_size),
            "profile": R4_PROFILE,
            "input_identity": {
                "template_path": str(args.input.resolve()),
                "template_sha256": str(comm["specification"].input_sha256),
                "resolved_config_bytes": len(comm["resolved"]),
                "resolved_config_sha256": hashlib.sha256(comm["resolved"]).hexdigest(),
            },
            "mode_count": len(comm["modes"]),
            "mode_manifest_sha256": comm["mode_sha"],
            "mode_manifest": mode_descriptor,
            "artifacts": artifacts,
            "sweep": {
                "ledger": _jsonable(first.ledger),
                "audit": _jsonable(dict(first.audit)),
                "repeat_ledger": _jsonable(second.ledger),
                "exact_update_apply_count": int(first.audit["exact_update_apply_count"]),
                "exact_update_apply_count_cumulative": int(second.audit["exact_update_apply_count_cumulative"]),
                "physical_action_apply_count_after_repeat": int(comm["physical_action"].audit["apply_count"]),
            },
            "resource": {
                "rank_max_current_rss_bytes": int(mpi.allreduce(_rss_bytes(), op=__import__("mpi4py").MPI.MAX)),
                "rank_max_current_swap_bytes": int(mpi.allreduce(_swap_bytes(), op=__import__("mpi4py").MPI.MAX)),
            },
            "operator_audit": _jsonable(dict(comm["physical_action"].audit)),
            "candidate_audit": _jsonable(dict(comm["candidate_audit"])),
        }
        if mpi.rank == 0:
            args.record.write_text(json.dumps(_jsonable(record), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        mpi.barrier()
        return record
    finally:
        for result in (locals().get("first"), locals().get("second")):
            if result is not None:
                result.delta.destroy()
                result.action_delta.destroy()
                result.residual.destroy()
        comm["source"].destroy()
        comm["sweep"].destroy()
        comm["transmission"].destroy()
        comm["physical_action"].destroy()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--source", choices=R4_SOURCE_NAMES, required=True)
    parser.add_argument("--degree", type=int, required=True)
    parser.add_argument("--mesh-target", type=float, required=True)
    parser.add_argument("--long-tail-manifest", type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    root = Path(__file__).resolve().parents[1]
    from mpi4py import MPI

    if MPI.COMM_WORLD.size != args.expected_mpi_size:
        raise SystemExit("MPI size does not match --expected-mpi-size")
    identity = _source_identity(root)
    if identity["commit_sha"] != args.expected_source_sha or identity["tracked_status"]:
        raise SystemExit("R4 source preflight requires the expected clean SHA")
    if not args.raw_dir.is_absolute():
        args.raw_dir = root / args.raw_dir
    if not args.record.is_absolute():
        args.record = root / args.record
    if args.long_tail_manifest is not None and not args.long_tail_manifest.is_absolute():
        args.long_tail_manifest = root / args.long_tail_manifest
    args._source_start = identity
    _prepare_raw_dir(args.raw_dir, args.record, MPI.COMM_WORLD)
    started = time.perf_counter()
    record = _write_case(root, args)
    if MPI.COMM_WORLD.rank == 0:
        print(json.dumps({"written": True, "wall_seconds": time.perf_counter() - started}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
