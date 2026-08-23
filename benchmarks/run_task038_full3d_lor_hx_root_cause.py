"""Thin M0 diagnostic worker for the multiplicative LOR-HX route.

This runner is intentionally separate from the K1 qualification runner.  It
records a p2/h50 random-source diagnostic only; it never changes the
production PC, creates a physical action, or makes a qualification decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI

from benchmarks.run_task038_full3d_lor_hx import (
    _append_stage_marker,
    _l2_canonical_payload,
    _l2_gather_payload,
    _prepare_paths,
    _runtime_identity,
    _source_identity,
)
from benchmarks.run_task038_full3d_lor_hx_krylov import _closeout_record


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SCHEMA = "task038.lor-native-complex-hx.m0-record.v1"
M0_SOURCE = "random"
M0_DIRECT_BACKEND = "petsc-preonly-lu-mumps"
OLD_L2_RECORD_SHA = "0a6ccfdb6a28b003167046e3ca3fc5e4de0d40825784786319661901a65389f3"
OLD_L2_RHO = 1.7348663090876784
OLD_L2_LIMIT = 0.45
OLD_L2_CLASSIFICATION = "CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE"
M0_EXACT_LIMIT = 1.0e-10
M0_PRODUCTION_EQUIVALENCE_LIMIT = 1.0e-13


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    return value


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _jsonable(value),
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


def _artifact(raw_dir: Path, name: str, array: np.ndarray) -> dict[str, Any]:
    array = np.asarray(array)
    path = raw_dir / f"{name}.npy"
    np.save(path, array, allow_pickle=False)
    return {
        "name": name,
        "relative_path": path.name,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
        "dtype": str(array.dtype),
        "shape": list(array.shape),
    }


def _save_pair(
    raw_dir: Path,
    artifacts: dict[str, dict[str, Any]],
    roles: dict[str, dict[str, str]],
    name: str,
    keys: np.ndarray,
    values: np.ndarray,
) -> None:
    key_name = f"{name}_keys"
    value_name = f"{name}_values"
    artifacts[key_name] = _artifact(raw_dir, key_name, np.asarray(keys))
    artifacts[value_name] = _artifact(
        raw_dir, value_name, np.asarray(values, dtype=np.complex128)
    )
    roles[name] = {"keys": key_name, "values": value_name}


def _merge_pairs(parts: list[list[tuple[str, complex]]]) -> tuple[np.ndarray, np.ndarray]:
    merged: dict[str, complex] = {}
    for part in parts:
        for key, value in part:
            if key in merged:
                raise RuntimeError(f"duplicate M0 canonical key {key}")
            merged[key] = complex(value)
    keys = np.asarray(sorted(merged), dtype="<U256")
    values = np.asarray([merged[key] for key in keys], dtype=np.complex128)
    return keys, values


def _gather_pairs(
    comm: MPI.Comm, local_pairs: list[tuple[str, complex]]
) -> tuple[np.ndarray, np.ndarray] | None:
    parts = comm.gather(local_pairs, root=0)
    if comm.rank != 0:
        return None
    return _merge_pairs(parts)


def _owner_pairs(
    fixture: Any, vector: Any, *, dual: bool = False
) -> list[tuple[str, complex]]:
    if dual:
        from src.solvers.fullspace_lor_hx_root_cause import low_dual_owner_packet

        ids, values = low_dual_owner_packet(fixture, vector)
    else:
        ids, values = fixture._route_low_owner_packet(vector)
    return [
        (f"lor-edge:{int(edge_id)}", complex(value))
        for edge_id, value in zip(ids, values, strict=True)
    ]


def _node_pairs(fixture: Any, vector: Any) -> list[tuple[str, complex]]:
    space = fixture.lor_node_space
    index_map = space.dofmap.index_map
    owned = int(index_map.size_local)
    coordinates = np.asarray(space.tabulate_dof_coordinates(), dtype=np.float64)
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    pairs: list[tuple[str, complex]] = []
    for local in range(owned):
        indices = tuple(
            int(np.argmin(np.abs(np.asarray(axis, dtype=np.float64) - value)))
            for axis, value in zip(fixture.refined_axes, coordinates[local], strict=True)
        )
        if any(
            not np.isclose(
                float(fixture.refined_axes[axis][index]),
                float(coordinates[local, axis]),
                rtol=1.0e-12,
                atol=1.0e-12,
            )
            for axis, index in enumerate(indices)
        ):
            raise ValueError("node coordinate is not on the fixed refined lattice")
        pairs.append(
            (
                "node:lattice:" + ",".join(str(index) for index in indices),
                complex(values[local]),
            )
        )
    if len({key for key, _value in pairs}) != len(pairs):
        raise ValueError("duplicate owned node lattice key")
    return pairs


def _collect_low_trace(
    comm: MPI.Comm,
    fixture: Any,
    trace: dict[str, Any],
) -> dict[str, tuple[np.ndarray, np.ndarray] | None]:
    result: dict[str, tuple[np.ndarray, np.ndarray] | None] = {}
    for field in ("result", "edge_delta"):
        result[field] = _gather_pairs(comm, _owner_pairs(fixture, trace[field]))
    for field in ("remaining", "edge_action"):
        result[field] = _gather_pairs(
            comm, _owner_pairs(fixture, trace[field], dual=True)
        )
    for field in ("rhs", "nodal_delta"):
        vector = trace[field]
        result[field] = (
            None if vector is None else _gather_pairs(comm, _node_pairs(fixture, vector))
        )
    return result


def _collect_trace_set(
    comm: MPI.Comm,
    fixture: Any,
    traces: list[dict[str, Any]],
    prefix: str,
) -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], list[dict[str, Any]]]:
    collected: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    facts: list[dict[str, Any]] = []
    for trace in traces:
        name = str(trace["name"])
        fields = _collect_low_trace(comm, fixture, trace)
        if comm.rank == 0:
            for field, pair in fields.items():
                if pair is not None:
                    collected[f"{prefix}_{name}_{field}"] = pair
        facts.append({"name": name, "solver": trace["solver"]})
    return collected, facts


def _global_finite(comm: MPI.Comm, vectors: list[Any]) -> bool:
    local = all(
        bool(np.all(np.isfinite(np.asarray(vector.getArray(readonly=True)))))
        for vector in vectors
    )
    return bool(comm.allreduce(int(local), op=MPI.MIN))


def _relative(left: Any, right: Any) -> float:
    difference = left.copy()
    difference.axpy(-1.0, right)
    value = float(difference.norm()) / max(float(right.norm()), np.finfo(float).tiny)
    difference.destroy()
    return value


def _run_diagnostic(
    fixture: Any, source: Any, residual: Any, comm: MPI.Comm
) -> tuple[dict[str, Any], dict[str, np.ndarray], dict[str, Any]]:
    from src.solvers.fullspace_lor_hx_root_cause import (
        DiagnosticDirectSolver,
        exact_edge_reference,
        lift_low_primal,
        low_input_from_high_dual,
        replay_multiplicative_components,
        _production_nodal_solver,
        destroy_replay,
        destroy_outer_right_gmres,
        run_outer_right_gmres,
    )

    exact_edge = exact_edge_reference(fixture, residual)
    low_input = exact_edge["low_input"]
    production_trace = replay_multiplicative_components(
        fixture, low_input, _production_nodal_solver(fixture)
    )
    direct_nodal = DiagnosticDirectSolver(
        fixture.node_matrix, label="exact-nodal"
    )
    exact_trace = replay_multiplicative_components(
        fixture, low_input, direct_nodal.solve
    )
    production_replay_high = lift_low_primal(fixture, production_trace["result"])
    exact_replay_high = lift_low_primal(fixture, exact_trace["result"])
    production_actual = fixture.apply_high_preconditioner(residual)
    production_repeat = fixture.apply_high_preconditioner(residual)
    production_action = fixture.apply_high_action_copy(production_actual)
    production_replay_relative = _relative(production_replay_high, production_actual)
    exact_replay_relative = _relative(exact_replay_high, production_actual)

    def exact_preconditioner(vector: Any) -> Any:
        exact_low_input, _ = low_input_from_high_dual(fixture, vector)
        exact_replay = replay_multiplicative_components(
            fixture,
            exact_low_input,
            direct_nodal.solve_lean,
            capture_traces=False,
        )
        try:
            return lift_low_primal(fixture, exact_replay["result"])
        finally:
            exact_low_input.destroy()
            destroy_replay(exact_replay)

    production_outer = run_outer_right_gmres(
        residual,
        fixture.apply_high_action_copy,
        fixture.apply_high_preconditioner,
        label="production-v1",
    )
    exact_outer = run_outer_right_gmres(
        residual,
        fixture.apply_high_action_copy,
        exact_preconditioner,
        label="exact-nodal-direct",
    )

    def outer_facts(result: dict[str, Any]) -> dict[str, Any]:
        excluded = {
            "final_solution",
            "final_action",
            "final_true_residual",
        }
        return _jsonable({key: value for key, value in result.items() if key not in excluded})

    outer_histories = {
        "production": outer_facts(production_outer),
        "exact_nodal": outer_facts(exact_outer),
    }
    outer_artifact_labels: list[str] = []
    facts = {
        "direct_edge": exact_edge["direct_facts"],
        "production_replay_relative": production_replay_relative,
        "exact_nodal_vs_production_relative": exact_replay_relative,
        "production_repeat_relative": _relative(production_repeat, production_actual),
        "trace_count": 6,
        "nodal_correction_count": 4,
        "production_components": [
            {"name": item["name"], "solver": item["solver"]}
            for item in production_trace["traces"]
        ],
        "exact_nodal_components": [
            {"name": item["name"], "solver": item["solver"]}
            for item in exact_trace["traces"]
        ],
        "outer_histories": outer_histories,
    }
    high_vectors = {
        "high_source_before": (source, "primal"),
        "high_residual": (residual, "dual"),
        "production_output": (production_actual, "primal"),
        "production_repeat": (production_repeat, "primal"),
        "production_action": (production_action, "dual"),
        "exact_edge_correction": (exact_edge["high_correction"], "primal"),
        "exact_edge_action": (exact_edge["high_action"], "dual"),
        "production_replay_output": (production_replay_high, "primal"),
        "exact_nodal_output": (exact_replay_high, "primal"),
    }
    for prefix, result in (
        ("production_outer", production_outer),
        ("exact_nodal_outer", exact_outer),
    ):
        for suffix, kind in (
            ("final_solution", "primal"),
            ("final_action", "dual"),
            ("final_true_residual", "dual"),
        ):
            label = f"{prefix}_{suffix}"
            high_vectors[label] = (result[suffix], kind)
            outer_artifact_labels.append(label)
    facts["outer_artifact_labels"] = outer_artifact_labels
    gathered_high = _l2_gather_payload(
        comm,
        _l2_canonical_payload(fixture, high_vectors),
    )
    high_payload: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if comm.rank == 0 and gathered_high is not None:
        high_payload = {
            label: (gathered_high[f"{label}_keys"], gathered_high[f"{label}_values"])
            for label in high_vectors
        }
    low_payload: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    owner_pair = _gather_pairs(
        comm,
        [
            (f"lor-edge:{int(edge_id)}", complex(value))
            for edge_id, value in zip(
                exact_edge["owner_packet_ids"],
                exact_edge["owner_packet_values"],
                strict=True,
            )
        ],
    )
    if comm.rank == 0 and owner_pair is not None:
        low_payload["low_input"] = owner_pair
    for prefix, trace_set in (
        ("production", production_trace["traces"]),
        ("exact_nodal", exact_trace["traces"]),
    ):
        trace_payload, trace_facts = _collect_trace_set(
            comm, fixture, trace_set, prefix
        )
        if comm.rank == 0:
            low_payload.update(trace_payload)
            facts[f"{prefix}_trace"] = trace_facts
    for vector in (
        production_actual,
        production_repeat,
        production_action,
        production_replay_high,
        exact_replay_high,
    ):
        vector.destroy()
    exact_edge["low_solution"].destroy()
    exact_edge["low_input"].destroy()
    exact_edge["high_correction"].destroy()
    exact_edge["high_action"].destroy()
    destroy_replay(production_trace)
    destroy_replay(exact_trace)
    destroy_outer_right_gmres(production_outer)
    destroy_outer_right_gmres(exact_outer)
    direct_nodal.destroy()
    return facts, high_payload if comm.rank == 0 else {}, low_payload


def _build_record(
    args: argparse.Namespace,
    source: dict[str, Any],
    runtime: dict[str, Any],
    rank_facts: list[dict[str, Any]],
    fixture_audit: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    roles: dict[str, dict[str, str]],
    facts: dict[str, Any],
    *,
    status: str,
) -> dict[str, Any]:
    canonical_role_kinds = {
        "high_source_before": "primal",
        "high_source_after": "primal",
        "high_residual": "dual",
        "high_residual_before": "dual",
        "high_residual_after": "dual",
        "production_output": "primal",
        "production_repeat": "primal",
        "production_action": "dual",
        "exact_edge_correction": "primal",
        "exact_edge_action": "dual",
        "production_replay_output": "primal",
        "exact_nodal_output": "primal",
        "low_input": "dual",
    }
    for prefix in ("production", "exact_nodal"):
        for name in (
            "edge_jacobi_pre",
            "gradient",
            "pi_x",
            "pi_y",
            "pi_z",
            "edge_jacobi_post",
        ):
            stem = f"{prefix}_{name}"
            canonical_role_kinds.update(
                {
                    f"{stem}_result": "primal",
                    f"{stem}_remaining": "dual",
                    f"{stem}_edge_delta": "primal",
                    f"{stem}_edge_action": "dual",
                }
            )
            if name != "edge_jacobi_pre" and name != "edge_jacobi_post":
                canonical_role_kinds.update(
                    {
                        f"{stem}_rhs": "dual",
                        f"{stem}_nodal_delta": "primal",
                    }
                )
    for label in facts.get("outer_artifact_labels", []):
        if label.endswith("_solution") or label.endswith("_final_solution"):
            canonical_role_kinds[label] = "primal"
        elif label.endswith("_action") or label.endswith("_true_residual"):
            canonical_role_kinds[label] = "dual"
    return {
        "schema": SCHEMA,
        "stage": "m0",
        "status": status,
        "case": args.case,
        "degree": 2,
        "mpi_size": int(args.expected_mpi_size),
        "raw_dir": str(args.raw_dir.resolve()),
        "record": str(args.record.resolve()),
        "source": source,
        "runtime": runtime,
        "rank_facts": rank_facts,
        "settings": {
            "variant": "sequential-v1",
            "source": M0_SOURCE,
            "direct_backend": M0_DIRECT_BACKEND,
            "exact_nodal_direct": {
                "ksp_type": "preonly",
                "pc_type": "lu",
                "factor_solver_type": "mumps",
                "factor_reused_within_diagnostic_apply": True,
            },
            "outer_gmres": {
                "ksp_type": "gmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 20,
                "cycle_max_it": 20,
                "max_cycles": 10,
                "max_it": 200,
                "rtol": 1.0e-8,
                "atol": 0.0,
                "zero_initial_guess": True,
                "residual_replacement": True,
            },
            "pair_gates": {
                "input": 1.0e-12,
                "exact_correction_action": M0_EXACT_LIMIT,
                "exact_component": M0_EXACT_LIMIT,
            },
        },
        "old_l2_reference": {
            "record_sha256": OLD_L2_RECORD_SHA,
            "rho": OLD_L2_RHO,
            "limit": OLD_L2_LIMIT,
            "classification": OLD_L2_CLASSIFICATION,
        },
        "production": {
            "variant": "sequential-v1",
            "production_pc_alpha_applied": False,
            "global_transfer_matrix": False,
            "global_numeric_allgather": False,
            "global_direct_coarse": False,
            "high_order_global_aij": False,
            "additive_v2": False,
            "ordinary_default_changed": False,
        },
        "fixture_audit": fixture_audit,
        "facts": facts,
        "canonical_role_kinds": canonical_role_kinds,
        "canonical_roles": roles,
        "artifacts": list(artifacts.values()),
    }


def run(args: argparse.Namespace) -> int:
    from petsc4py import PETSc
    from src.solvers.fullspace_lor_native_hx_fixture import (
        build_real_l2_positive_hx_fixture,
    )

    comm = MPI.COMM_WORLD
    root = Path(__file__).resolve().parents[1]
    if args.expected_mpi_size != comm.size:
        raise ValueError("expected MPI size does not match COMM_WORLD")
    _prepare_paths(args.raw_dir.resolve(), args.record.resolve(), comm, stage="m0")
    _append_stage_marker(args.raw_dir, "paths_ready", comm.rank)
    source: dict[str, Any] | None = None
    source_error: tuple[str, str] | None = None
    if comm.rank == 0:
        try:
            source = _source_identity(root, args.expected_source_sha)
        except Exception as exc:
            source_error = (type(exc).__name__, str(exc))
    source, source_error = comm.bcast((source, source_error), root=0)
    if source_error is not None:
        raise RuntimeError(f"{source_error[0]}: {source_error[1]}")
    _append_stage_marker(args.raw_dir, "source_identity_closed", comm.rank)
    runtime = _runtime_identity(root, args.expected_mpi_size)
    _append_stage_marker(args.raw_dir, "runtime_identity", comm.rank)

    fixture = build_real_l2_positive_hx_fixture(2, comm, variant="sequential-v1")
    _append_stage_marker(args.raw_dir, "fixture_built", comm.rank)
    artifacts: dict[str, dict[str, Any]] = {}
    roles: dict[str, dict[str, str]] = {}
    facts: dict[str, Any]
    source_vector = None
    residual = None
    source_before = None
    residual_before = None
    source_after = None
    residual_after = None
    if args.mode == "smoke":
        source_vector, source_audit = fixture.build_l2_source(M0_SOURCE)
        facts = {
            "mode": "lifecycle_smoke",
            "source_formula": source_audit["formula"],
            "numerical_diagnostic": "not_run_by_smoke_contract",
        }
        status = "lifecycle_smoke"
    else:
        source_vector, source_audit = fixture.build_l2_source(M0_SOURCE)
        source_before = source_vector.copy()
        residual = fixture.apply_high_action_copy(source_vector)
        residual_before = residual.copy()
        _append_stage_marker(args.raw_dir, "m0_reference_built", comm.rank)
        facts, high_payload, low_payload = _run_diagnostic(
            fixture, source_vector, residual, comm
        )
        _append_stage_marker(args.raw_dir, "m0_trace_built", comm.rank)
        source_after = source_vector.copy()
        residual_after = residual.copy()
        gathered_snapshot = _l2_gather_payload(
            comm,
            _l2_canonical_payload(
                fixture,
                {
                    "high_source_after": (source_after, "primal"),
                    "high_residual_before": (residual_before, "dual"),
                    "high_residual_after": (residual_after, "dual"),
                },
            ),
        )
        if comm.rank == 0 and gathered_snapshot is not None:
            high_payload.update(
                {
                    label: (
                        gathered_snapshot[f"{label}_keys"],
                        gathered_snapshot[f"{label}_values"],
                    )
                    for label in (
                        "high_source_after",
                        "high_residual_before",
                        "high_residual_after",
                    )
                }
            )
        facts.update(
            {
                "source_formula": source_audit["formula"],
                "source_phase_application": source_audit["phase_application"],
                "source_unchanged": bool(
                    comm.allreduce(
                        int(np.array_equal(source_before.array, source_after.array)),
                        op=MPI.MIN,
                    )
                ),
                "residual_input_unchanged": bool(
                    comm.allreduce(
                        int(np.array_equal(residual_before.array, residual_after.array)),
                        op=MPI.MIN,
                    )
                ),
                "finite": _global_finite(
                    comm,
                    [
                        source_vector,
                        residual,
                        source_after,
                        residual_after,
                    ],
                ),
                "residual_norm": float(residual.norm()),
            }
        )
        if comm.rank == 0:
            for label, pair in high_payload.items():
                _save_pair(args.raw_dir, artifacts, roles, label, pair[0], pair[1])
            for label, pair in low_payload.items():
                _save_pair(args.raw_dir, artifacts, roles, label, pair[0], pair[1])
        _append_stage_marker(args.raw_dir, "canonical_packets_gathered", comm.rank)
        status = "facts_written_not_qualified"
    comm.barrier()

    rank_fact = {
        "rank": int(comm.rank),
        "runtime": runtime,
        "mode": args.mode,
    }
    fixture_audit = _jsonable(fixture.audit)
    fixture_audit["global_direct_coarse"] = False
    fixture_audit["hx_audit_after_diagnostic"] = _jsonable(fixture.hx.audit)

    def build_record(rank_facts: list[dict[str, Any]]) -> dict[str, Any]:
        return _build_record(
            args,
            source,
            runtime,
            rank_facts,
            fixture_audit,
            artifacts,
            roles,
            facts,
            status=status,
        )

    _closeout_record(
        comm,
        args.raw_dir.resolve(),
        args.record.resolve(),
        rank_fact,
        build_record,
    )
    _append_stage_marker(args.raw_dir, "cleanup_begin", comm.rank)
    for vector in (source_before, source_after, residual_before, residual_after):
        if vector is not None:
            vector.destroy()
    if source_vector is not None:
        source_vector.destroy()
    if residual is not None:
        residual.destroy()
    fixture.destroy()
    _append_stage_marker(args.raw_dir, "cleanup_end", comm.rank)
    comm.barrier()
    if comm.rank == 0:
        print(json.dumps({"record": str(args.record.resolve()), "status": status}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("diagnostic", "smoke"), default="diagnostic")
    parser.add_argument("--case", choices=("p2-mpi1", "p2-mpi2"), required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
