"""Minimal action-only T4 evidence worker; no KSP, PDE, or tracked outcomes."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import replace
import json
import math
from pathlib import Path
import subprocess
import time
from typing import Any

import numpy as np

T4_SCHEMA = "task038.full3d.iterative.t4.action-record.v1"
T4_PROFILE = "full3d_scalable_v1"
T4_TRANSMISSION = "first_order_impedance_robin_v1"
T4_BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
T4_CASES = {
    "p2-mpi1": {"degree": 2, "mpi_size": 1},
    "p2-mpi2": {"degree": 2, "mpi_size": 2},
    "p3-mpi1": {"degree": 3, "mpi_size": 1},
    "p3-mpi2": {"degree": 3, "mpi_size": 2},
}
T4_SLAB_COUNT = 2


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    return _jsonable(value.item()) if hasattr(value, "item") else value


def _source_identity(root: Path) -> dict[str, Any]:
    def git(*arguments: str) -> str:
        result = subprocess.run(["git", "--git-dir=.git-codex", "--work-tree=.", *arguments], cwd=root, check=False, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "git identity probe failed")
        return result.stdout.strip()

    status = git("status", "--short", "--untracked-files=all")
    return {"branch": git("branch", "--show-current"), "commit_sha": git("rev-parse", "HEAD"), "tracked_status": status, "clean": status == ""}


def _prepare_raw_dir(raw_dir: Path, record_path: Path, comm: Any) -> None:
    error: tuple[str, str] | None = None
    if comm.rank == 0:
        try:
            raw_dir.parent.mkdir(parents=True, exist_ok=True)
            record_path.parent.mkdir(parents=True, exist_ok=True)
            if raw_dir.exists() or record_path.exists():
                raise FileExistsError("T4 raw directory or record already exists")
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


def _rss_bytes() -> int:
    with Path("/proc/self/status").open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("current VmRSS is unavailable")


def _swap_used_bytes() -> int:
    with Path("/proc/self/status").open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("VmSwap:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("process VmSwap telemetry is unavailable")


def _rank_max_telemetry(comm: Any, mpi: Any) -> dict[str, int | str]:
    return {
        "rss_semantics": "mpi_rank_max_current_self_rss",
        "swap_semantics": "current_process_VmSwap",
        "rank_max_current_rss_bytes": int(comm.allreduce(_rss_bytes(), op=mpi.MAX)),
        "rank_max_swap_used_bytes": int(comm.allreduce(_swap_used_bytes(), op=mpi.MAX)),
    }


def _copy_vector(field: Any) -> Any:
    vector = field.x.petsc_vec.duplicate()
    field.x.petsc_vec.copy(vector)
    return vector


def _analytic_field(function_space: Any, floquet_data: Any, cfg: Any, polarization: str) -> Any:
    from src.solvers.common_3d_fields import incident_air_plane_wave_field

    if polarization not in {"s", "p"}:
        raise ValueError("T4 analytic source polarization must be 's' or 'p'")
    source_cfg = replace(
        cfg,
        polarization_kind=polarization,
        custom_polarization=None,
    )
    field = incident_air_plane_wave_field(function_space, source_cfg)
    floquet_data.mpc.homogenize(field)
    floquet_data.mpc.backsubstitution(field)
    field.x.scatter_forward()
    return field


def _linear_combination_field(
    function_space: Any,
    s_field: Any,
    p_field: Any,
    s_weight: complex,
    p_weight: complex,
) -> Any:
    from dolfinx import fem

    field = fem.Function(function_space, name="T4_s_plus_p_test")
    field.x.array[:] = (
        complex(s_weight) * s_field.x.array
        + complex(p_weight) * p_field.x.array
    )
    field.x.scatter_forward()
    return field


def _max_error(comm: Any, mpi: Any, value: float) -> float:
    return float(comm.allreduce(float(value), op=mpi.MAX))


def _reconstruction_facts(
    function_space: Any, floquet_data: Any, source_field: Any, comm: Any, mpi: Any
) -> dict[str, float]:
    from dolfinx import fem
    first_relation_error = _max_error(comm, mpi, _local_slave_relation_error(source_field, floquet_data))
    reconstructed = fem.Function(function_space)
    reconstructed.x.array[:] = source_field.x.array
    reconstructed.x.scatter_forward()
    before = reconstructed.x.array.copy()
    floquet_data.mpc.homogenize(reconstructed)
    floquet_data.mpc.backsubstitution(reconstructed)
    reconstructed.x.scatter_forward()
    after = reconstructed.x.array.copy()
    full_error = _max_error(comm, mpi, float(np.max(np.abs(after - before), initial=0.0)))
    slave_rows = np.asarray(floquet_data.local_slave_dofs, dtype=np.int32)
    slave_error = float(np.max(np.abs(after[slave_rows] - before[slave_rows]), initial=0.0)) if slave_rows.size else 0.0
    relation_error = _max_error(comm, mpi, _local_slave_relation_error(reconstructed, floquet_data))
    reconstructed.x.petsc_vec.destroy()
    return {
        "first_reconstruction_relation_error": first_relation_error,
        "second_full_owned_ghost_idempotence_error": full_error,
        "second_slave_idempotence_error": _max_error(comm, mpi, slave_error),
        "second_reconstruction_relation_error": relation_error,
    }


def _local_slave_relation_error(field: Any, floquet_data: Any) -> float:
    coefficients, offsets = floquet_data.mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    values = np.asarray(field.x.array, dtype=np.complex128)
    error = 0.0
    for slave in np.asarray(floquet_data.mpc.slaves, dtype=np.int32):
        row = int(slave)
        masters = np.asarray(floquet_data.mpc.masters.links(row), dtype=np.int32)
        start, stop = int(offsets[row]), int(offsets[row + 1])
        error = max(error, float(abs(values[row] - np.dot(coefficients[start:stop], values[masters]))))
    return error


def _relative_arrays(left: np.ndarray, right: np.ndarray, comm: Any, mpi: Any) -> float:
    difference = np.asarray(left, dtype=np.complex128) - np.asarray(right, dtype=np.complex128)
    numerator = float(comm.allreduce(float(np.vdot(difference, difference).real), op=mpi.SUM))
    denominator = float(comm.allreduce(float(np.vdot(right, right).real), op=mpi.SUM))
    return math.sqrt(max(numerator, 0.0)) / max(math.sqrt(max(denominator, 0.0)), np.finfo(float).tiny)


def _active_pair(topology: Any, output: Any, test_field: Any, comm: Any, mpi: Any) -> complex:
    output_values = np.asarray(output.getArray(readonly=True), dtype=np.complex128)
    test_values = np.asarray(test_field.x.array, dtype=np.complex128)
    rows = topology.owned_trace_local_rows
    local = np.vdot(test_values[rows], output_values[rows])
    return complex(comm.allreduce(local, op=mpi.SUM))


def _oracle_pair(
    topology: Any, source_field: Any, test_field: Any, direction: str, comm: Any, mpi: Any
) -> complex:
    from dolfinx import fem, mesh
    import ufl
    tags = mesh.meshtags(topology.mesh, topology.mesh.topology.dim - 1, topology.interface_facet_indices.copy(), topology.interface_facet_tag_values.copy())
    u_plus = source_field("+")
    v_plus = test_field("+")
    u_t = ufl.as_vector((u_plus[0], u_plus[1], 0.0))
    v_t = ufl.as_vector((v_plus[0], v_plus[1], 0.0))
    dS = ufl.Measure("dS", domain=topology.mesh, subdomain_data=tags)
    expression = 0
    for tag, lower, upper in topology.global_material_pairs:
        material = upper if direction == "forward" else lower
        expression += complex(-1j * topology.cfg.k0 * material.refractive_index) * ufl.inner(u_t, v_t) * dS(int(tag))
    local = fem.assemble_scalar(fem.form(expression))
    return complex(comm.allreduce(local, op=mpi.SUM))


def _write_packet_manifest(
    raw_dir: Path,
    role: str,
    vector: Any,
    function_space: Any,
    floquet_data: Any,
    comm: Any,
) -> dict[str, Any]:
    from benchmarks.canonical_vector_artifacts import canonical_shard_manifest, write_canonical_manifest, write_canonical_packet_shard
    from src.solvers.hcurl_canonical_vector_dolfinx import extract_canonical_full_fe_packets
    packets, extractor_audit = extract_canonical_full_fe_packets(function_space, vector, floquet_data)
    canonical_dir = raw_dir / "canonical"
    shard_path = canonical_dir / f"{role}.rank{comm.rank:04d}.jsonl"
    shard = write_canonical_packet_shard(shard_path, packets, audit_packets=True)
    shards = comm.gather(shard, root=0)
    descriptor = None
    if comm.rank == 0:
        manifest = canonical_shard_manifest(role=role, mpi_size=comm.size, shard_metadata=shards, extractor_audit=_jsonable(dict(extractor_audit)))
        manifest_path = canonical_dir / f"{role}.manifest.json"
        manifest_sha = write_canonical_manifest(manifest_path, manifest)
        descriptor = {
            "kind": "physical_hcurl_packet_manifest",
            "relative_path": str(manifest_path.relative_to(raw_dir)),
            "bytes": int(manifest_path.stat().st_size),
            "sha256": manifest_sha,
            "packet_count": int(manifest["global_summed_packet_count"]),
            "mpi_size": int(comm.size),
        }
    return comm.bcast(descriptor, root=0)


def _topology_facts(topology: Any, floquet_data: Any, comm: Any, mpi: Any) -> dict[str, Any]:
    owner_closure = all(int(owner) in range(comm.size) for facet in topology.facets for owner in facet.trace_owners)
    local_slave_rows = set(int(value) for value in floquet_data.local_slave_dofs)
    owner_closure = owner_closure and all(int(row) not in local_slave_rows for facet in topology.facets for row in facet.trace_local_rows)
    owner_closure = owner_closure and set(map(int, topology.owned_trace_global_rows)).isdisjoint(map(int, topology.ghost_trace_global_rows))
    owner_closure = bool(comm.allreduce(owner_closure, op=mpi.LAND))
    rng = np.random.default_rng(38000 + int(topology.function_space.element.basix_element.degree) + comm.size)
    volume = np.asarray(rng.normal(size=topology.volume_owned_size) + 1j * rng.normal(size=topology.volume_owned_size), dtype=np.complex128)
    trace = np.asarray(rng.normal(size=topology.owned_trace_count) + 1j * rng.normal(size=topology.owned_trace_count), dtype=np.complex128)
    lhs = np.vdot(topology.restrict_volume_to_trace(volume), trace)
    rhs = np.vdot(volume, topology.prolong_trace_to_volume(trace))
    difference = abs(complex(comm.allreduce(lhs - rhs, op=mpi.SUM)))
    reference = abs(complex(comm.allreduce(lhs, op=mpi.SUM)))
    adjoint_error = difference / max(reference, np.finfo(float).tiny)
    phases = {name: [float(complex(value).real), float(complex(value).imag)] for name, value in (("x", floquet_data.phase_x), ("y", floquet_data.phase_y), ("corner", floquet_data.phase_corner))}
    phase_nontrivial = any(abs(complex(*value) - 1.0) > 1.0e-8 for value in phases.values())
    plan = topology.neighbor_plan
    plan_fields = ("forward_send_peers", "forward_recv_peers", "backward_send_peers", "backward_recv_peers", "lower_participant_ranks", "upper_participant_ranks")
    audit_fields = ("restriction_prolongation", "phase_application", "bounded_material_class_collective", "material_class_collective", "cell_tag_scope", "communication_plan_collective", "canonical_identity_collective", "numeric_allgather", "global_aij_materialized", "dense_interface_mass_materialized", "dense_interface_schur_materialized", "slab_factor_materialized", "slave_rows_excluded")
    return {
        "profile": topology.profile,
        "slab_count": int(topology.audit["slab_count"]),
        "transmission": topology.audit["transmission"],
        "global_facet_count": int(topology.canonical_global_count),
        "local_facet_count": int(len(topology.local_canonical_manifest)),
        "canonical_sha256": topology.canonical_sha256,
        "owned_trace_rows": int(topology.owned_trace_count),
        "ghost_trace_rows": int(topology.ghost_trace_count),
        "owner_closure": owner_closure,
        "neighbor_plan": {name: list(getattr(plan, name)) for name in plan_fields},
        "restriction_prolongation_adjoint_relative_error": float(adjoint_error),
        "floquet_phases": phases,
        "floquet_phase_nontrivial": bool(phase_nontrivial),
        "interface_classifications": sorted(topology.audit["interface_classifications"]),
        "audit": _jsonable({key: topology.audit[key] for key in audit_fields}),
    }


def _candidate_audit(candidate: Any) -> dict[str, Any]:
    audit = candidate.audit
    fields = (
        "retained_numeric_payload_local_bytes",
        "retained_numeric_payload_global_max_bytes",
        "per_apply_bounded_temporary_bytes",
        "apply_count",
    )
    actions = {
        direction: {
            field: int(action.audit[field]) for field in fields
        }
        for direction, action in candidate._actions.items()
    }
    return {
        "candidate": audit["candidate"],
        "action": audit["action"],
        "phase_application": audit["phase_application"],
        "numeric_allgather": bool(audit["numeric_allgather"]),
        "global_aij_materialized": bool(audit["global_aij_materialized"]),
        "dense_interface_mass_materialized": bool(audit["dense_interface_mass_materialized"]),
        "dense_interface_schur_materialized": bool(audit["dense_interface_schur_materialized"]),
        "slab_factor_materialized": bool(audit["slab_factor_materialized"]),
        "directions": actions,
    }


def _run_case(root: Path, args: argparse.Namespace) -> int:
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    spec = T4_CASES[args.case]
    if comm.size != int(spec["mpi_size"]):
        raise RuntimeError(f"{args.case} requires MPI size {spec['mpi_size']}")
    raw_dir = Path(args.raw_dir).resolve()
    record_path = Path(args.record).resolve()
    _prepare_raw_dir(raw_dir, record_path, comm)
    source_start = _source_identity(root)
    if source_start["branch"] != T4_BRANCH:
        raise RuntimeError("T4 formal runner is on the wrong branch")
    if not source_start["clean"]:
        raise RuntimeError("T4 formal runner requires a clean source start")
    if source_start["commit_sha"] != args.expected_source_sha:
        raise RuntimeError("T4 source SHA does not match --expected-source-sha")
    if args.expected_mpi_size is not None and comm.size != args.expected_mpi_size:
        raise RuntimeError("T4 MPI size does not match --expected-mpi-size")
    if any(report != source_start for report in comm.allgather(source_start)):
        raise RuntimeError("MPI ranks do not share one source identity")

    from dolfinx import fem
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.fullspace_slab_interface import (
        FirstOrderImpedanceTransmission,
        build_fullspace_slab_interface,
    )
    from src.common.config_3d import target_stage4_config

    cfg = replace(
        target_stage4_config(degree=int(spec["degree"]), h_nm=50.0),
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
    topology_facts = _topology_facts(topology, floquet_data, comm, MPI)
    reconstruction_facts: dict[str, Any] | None = None
    source_fields: dict[str, Any] = {}
    test_field = None
    candidate = None
    artifacts: dict[str, Any] = {}
    action_facts: dict[str, Any] = {}
    telemetry: list[dict[str, Any]] = []
    try:
        source_fields = {
            "source_1": _analytic_field(function_space, floquet_data, cfg, "s"),
            "source_2": _analytic_field(function_space, floquet_data, cfg, "p"),
        }
        test_field = _linear_combination_field(
            function_space,
            source_fields["source_1"],
            source_fields["source_2"],
            0.6 + 0.1j,
            0.35 - 0.2j,
        )
        reconstruction_facts = _reconstruction_facts(
            function_space, floquet_data, source_fields["source_1"], comm, MPI
        )
        candidate = FirstOrderImpedanceTransmission(
            function_space, topology, mpc=floquet_data.mpc
        )
        for source_name, source_field in source_fields.items():
            artifacts[source_name] = _write_packet_manifest(
                raw_dir,
                source_name,
                source_field.x.petsc_vec,
                function_space,
                floquet_data,
                comm,
            )
            source_vector = _copy_vector(source_field)
            source_actions: dict[str, Any] = {}
            try:
                for direction in ("forward", "backward"):
                    expected = _oracle_pair(
                        topology, source_field, test_field, direction, comm, MPI
                    )
                    outputs: list[np.ndarray] = []
                    pairings: list[complex] = []
                    elapsed: list[float] = []
                    output_manifest = None
                    for repeat in range(2):
                        started = time.perf_counter()
                        observed = candidate.apply(source_vector, direction)
                        try:
                            outputs.append(
                                np.asarray(
                                    observed.getArray(readonly=True),
                                    dtype=np.complex128,
                                ).copy()
                            )
                            pairings.append(
                                _active_pair(topology, observed, test_field, comm, MPI)
                            )
                            elapsed.append(time.perf_counter() - started)
                            telemetry.append(
                                {
                                    "source": source_name,
                                    "direction": direction,
                                    "repeat": repeat,
                                    "elapsed_seconds": float(elapsed[-1]),
                                    **_rank_max_telemetry(comm, MPI),
                                }
                            )
                            if repeat == 0:
                                output_manifest = _write_packet_manifest(
                                    raw_dir,
                                    f"{source_name}_{direction}",
                                    observed,
                                    function_space,
                                    floquet_data,
                                    comm,
                                )
                        finally:
                            observed.destroy()
                    assert output_manifest is not None
                    source_actions[direction] = {
                        "oracle_pairing": [float(expected.real), float(expected.imag)],
                        "candidate_pairing": [
                            float(pairings[0].real),
                            float(pairings[0].imag),
                        ],
                        "finite": bool(
                            all(
                                math.isfinite(value.real) and math.isfinite(value.imag)
                                for value in (expected, pairings[0])
                            )
                        ),
                        "repeat_relative_difference": float(
                            _relative_arrays(outputs[0], outputs[1], comm, MPI)
                        ),
                        "canonical": output_manifest,
                    }
            finally:
                source_vector.destroy()
            action_facts[source_name] = source_actions
        candidate_audit = _candidate_audit(candidate)
    finally:
        if candidate is not None:
            candidate.destroy()
        for field in source_fields.values():
            field.x.petsc_vec.destroy()
        if test_field is not None:
            test_field.x.petsc_vec.destroy()
    source_end = _source_identity(root)
    if any(report != source_end for report in comm.allgather(source_end)):
        raise RuntimeError("MPI ranks do not share one source end identity")
    record = {
        "schema": T4_SCHEMA,
        "case": args.case,
        "degree": int(spec["degree"]),
        "mpi_size": int(comm.size),
        "raw_dir": str(raw_dir),
        "profile": T4_PROFILE,
        "source": {
            "branch": source_start["branch"],
            "commit_sha_start": source_start["commit_sha"],
            "commit_sha_end": source_end["commit_sha"],
            "expected_sha": args.expected_source_sha,
            "tracked_status_start": source_start["tracked_status"],
            "tracked_status_end": source_end["tracked_status"],
            "clean_start": bool(source_start["clean"]),
            "clean_end": bool(source_end["clean"]),
        },
        "model": {
            "wavelength_nm": float(cfg.lambda0),
            "mesh_target_nm": float(cfg.mesh_target_size),
            "degree": int(spec["degree"]),
            "analytic_source": "incident_air_plane_wave_field",
            "incident_theta_deg": float(cfg.incident_theta_deg),
            "incident_phi_deg": float(cfg.incident_phi_deg),
            "source_family": "fixed_oblique_s_p",
            "source_polarizations": {"source_1": "s", "source_2": "p"},
            "test_polarization": "fixed_s_plus_p_linear_combination",
            "test_linear_combination": {
                "s": [0.6, 0.1],
                "p": [0.35, -0.2],
            },
        },
        "topology": topology_facts,
        "reconstruction": reconstruction_facts,
        "artifacts": artifacts,
        "actions": action_facts,
        "candidate_audit": candidate_audit,
        "telemetry": telemetry,
        "resource": {
            "rss_semantics": "mpi_rank_max_current_self_rss",
            "process_tree_evidence": "not_measured_t4",
            "swap_semantics": "mpi_rank_max_current_process_VmSwap",
            "swap_used_bytes": max(
                int(item["rank_max_swap_used_bytes"]) for item in telemetry
            ),
        },
        "execution": {
            "ksp_created": False,
            "pde_run": False,
            "official_physics": "not_run",
        },
    }
    if comm.rank == 0:
        record_path.write_bytes(_canonical_json(record))
    comm.barrier()
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run one frozen T4 action-only case")
    run.add_argument("--case", choices=tuple(T4_CASES), required=True)
    run.add_argument("--raw-dir", type=Path, required=True)
    run.add_argument("--record", type=Path, required=True)
    run.add_argument("--expected-source-sha", required=True)
    run.add_argument("--expected-mpi-size", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if args.command == "run":
        return _run_case(root, args)
    raise RuntimeError(f"unsupported T4 command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
