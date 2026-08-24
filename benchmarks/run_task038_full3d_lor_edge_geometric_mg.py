"""One-case S4-A3 LOR-edge geometric-MG worker.

The numerical path is kept in ``src.solvers``.  This entry point binds one of
the frozen p2/p3 cases, writes per-rank raw evidence, and leaves qualification
to the independent checker.  The existing foundation watchdog is the external
resource authority; this module deliberately has no watchdog mode.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

import numpy as np
from mpi4py import MPI

from benchmarks.run_task038_full3d_lor_hx import (
    _append_stage_marker,
    _prepare_paths,
    _runtime_identity,
    _source_identity,
)
from benchmarks.task034_wsl_resources import resource_authority_sample
from src.solvers.fullspace_lor_edge_geometric_mg_global import (
    HighLORGeometricVcyclePC,
    ImplicitLORTransferCase,
)
from src.solvers.fullspace_lor_native_hx_fixture import (
    L2_SOURCE_NAMES,
    RealL2PositiveHXFixture,
    l2_source_formula,
)
from src.solvers.fullspace_memory_first_krylov import (
    destroy_krylov_result,
    run_restart20_cycles,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
SCHEMA = "task038.lor-edge-geometric-mg.s4-a3-record.v1"
VARIANT = "sequential-v1"
CASES = {
    "p2-mpi1": (2, 1),
    "p2-mpi2": (2, 2),
    "p3-mpi1": (3, 1),
    "p3-mpi2": (3, 2),
}
SOURCES = tuple(L2_SOURCE_NAMES)
MAX_IT = 10000
RESTART = 20
RESIDUAL_LIMIT = 1.0e-8
PC_ALPHA = 0.375 + 0.25j
PC_BETA = -0.625 + 0.5j


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


def _packet_digest(key: Any) -> str:
    return hashlib.sha256(_json_bytes(key)).hexdigest()


def _identity_sha(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _partition_invariant_identities(degree: int, source_name: str) -> dict[str, str]:
    input_definition = {
        "degree": int(degree),
        "h_nm": 50.0,
        "source_name": source_name,
        "source_formula": l2_source_formula(source_name),
    }
    operator_definition = {
        "degree": int(degree),
        "h_nm": 50.0,
        "definition": "exact B_H = K_curl,|mu| + k0^2 M_|epsilon|",
        "scalar_type": "complex128",
        "space": "uncondensed high space",
    }
    physical_definition = {
        "h_nm": 50.0,
        "regions": "fixed Task038 physical regions",
        "coefficient_semantics": "fixed positive |mu| and |epsilon| coefficient semantics",
    }
    return {
        "input_identity_sha256": _identity_sha(input_definition),
        "operator_identity_sha256": _identity_sha(operator_definition),
        "physical_model_sha256": _identity_sha(physical_definition),
    }


def _launch_command(
    command: list[str], mpi_size: int, *, mpiexec_path: str | None = None
) -> list[str]:
    if int(mpi_size) == 1:
        return list(command)
    executable = mpiexec_path or shutil.which("mpiexec")
    if executable is None:
        raise RuntimeError("qualified mpiexec is required for MPI2 launch binding")
    return [str(Path(executable).absolute()), "-n", str(int(mpi_size)), *command]


def _scalar_outer(result: Mapping[str, Any]) -> dict[str, Any]:
    cycle_fields = (
        "start_iteration",
        "end_iteration",
        "iterations",
        "reason",
        "reported_final_residual",
        "explicit_true_residual",
        "matvec_count",
        "pc_apply_count",
        "wall_seconds",
        "ksp_destroyed",
    )
    cycles = [
        {field: _jsonable(cycle[field]) for field in cycle_fields}
        for cycle in result["cycles"]
    ]
    return {
        "cycles": cycles,
        "iterations": int(result["iterations"]),
        "reason": int(result["reason"]),
        "final_true_residual": float(result["final_true_residual"]),
        "matvec_count": int(result["matvec_count"]),
        "pc_apply_count": int(result["pc_apply_count"]),
        "explicit_action_count": int(result["explicit_action_count"]),
        "ksp_destroy_count": int(result["ksp_destroy_count"]),
        "elapsed_seconds": float(result["elapsed_seconds"]),
    }


def _canonical_packets(fixture: Any, vector: Any, role: str) -> list[tuple[Any, complex]]:
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
        extract_canonical_full_fe_packets,
    )

    if role == "primal":
        return extract_canonical_full_fe_packets(
            fixture.high_space, vector, fixture.high_floquet
        )[0]
    if role == "dual":
        return extract_canonical_full_fe_dual_packets(
            fixture.high_space, fixture.high_floquet.mpc, vector
        )[0]
    raise ValueError(f"unknown canonical role {role!r}")


def _array_descriptor(path: Path, values: np.ndarray) -> dict[str, Any]:
    return {
        "relative_path": path.name,
        "bytes": int(path.stat().st_size),
        "sha256": _sha256(path),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _write_layout(raw_dir: Path, name: str, vector: Any, rank: int) -> dict[str, Any]:
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
    path = raw_dir / f"{name}.rank{rank}.values.npy"
    np.save(path, values, allow_pickle=False)
    start, stop = vector.getOwnershipRange()
    return {
        "rank": int(rank),
        "ownership_range": [int(start), int(stop)],
        "local_size": int(vector.getLocalSize()),
        "global_size": int(vector.getSize()),
        "values": _array_descriptor(path, values),
    }


def _write_canonical(
    raw_dir: Path, fixture: Any, vector: Any, role: str, vector_role: str, rank: int
) -> dict[str, Any]:
    packets = sorted(
        _canonical_packets(fixture, vector, vector_role),
        key=lambda item: _packet_digest(item[0]),
    )
    keys = np.asarray([_packet_digest(key) for key, _value in packets], dtype="<U64")
    values = np.asarray([complex(value) for _key, value in packets], dtype=np.complex128)
    key_path = raw_dir / f"{role}.rank{rank}.keys.npy"
    value_path = raw_dir / f"{role}.rank{rank}.values.npy"
    np.save(key_path, keys, allow_pickle=False)
    np.save(value_path, values, allow_pickle=False)
    return {
        "rank": int(rank),
        "role": vector_role,
        "keys": _array_descriptor(key_path, keys),
        "values": _array_descriptor(value_path, values),
    }


def _relative(left: Any, right: Any) -> float:
    difference = left.copy()
    difference.axpy(-1.0, right)
    try:
        return float(difference.norm() / max(right.norm(), np.finfo(float).tiny))
    finally:
        difference.destroy()


def _finite(comm: MPI.Comm, vector: Any) -> bool:
    local = bool(np.all(np.isfinite(vector.getArray(readonly=True))))
    return bool(comm.allreduce(int(local), op=MPI.MIN))


def _slave_indices(fixture: Any, vector: Any) -> np.ndarray:
    raw = np.asarray(fixture.high_floquet.mpc.slaves, dtype=np.int64).reshape(-1)
    local_size = int(vector.getLocalSize())
    return np.unique(np.sort(raw[(raw >= 0) & (raw < local_size)])).astype(np.int32)


def _pc_legality(
    fixture: Any, pc: HighLORGeometricVcyclePC, rhs: Any, raw_dir: Path, rank: int
) -> dict[str, Any]:
    comm = fixture.comm
    row_start, row_stop = rhs.getOwnershipRange()
    row_ids = np.arange(row_start, row_stop, dtype=np.int64)
    first = rhs.copy()
    second = rhs.copy()
    first.array[row_ids % 2 != 0] = 0.0
    second.array[row_ids % 2 == 0] = 0.0
    combined = rhs.copy()
    combined.array[:] = PC_ALPHA * first.array + PC_BETA * second.array
    before = {name: vector.copy() for name, vector in {
        "first": first,
        "second": second,
        "combined": combined,
    }.items()}
    outputs = {
        "first": pc.apply(first),
        "second": pc.apply(second),
        "combined": pc.apply(combined),
        "repeat": pc.apply(combined),
    }
    expected = outputs["first"].copy()
    expected.scale(PC_ALPHA)
    expected.axpy(PC_BETA, outputs["second"])
    linearity = _relative(outputs["combined"], expected)
    repeat = _relative(outputs["repeat"], outputs["combined"])
    input_unchanged = all(
        np.array_equal(before[name].array, {
            "first": first,
            "second": second,
            "combined": combined,
        }[name].array)
        for name in before
    )
    slave = _slave_indices(fixture, outputs["first"])
    slave_max = max(
        (
            float(np.max(np.abs(vector.array[slave])))
            for vector in outputs.values()
            if slave.size
        ),
        default=0.0,
    )
    finite = all(_finite(comm, vector) for vector in (*outputs.values(), first, second, combined))
    artifacts = {}
    for name, vector in {
        "pc_input_first_before": before["first"],
        "pc_input_first_after": first,
        "pc_input_second_before": before["second"],
        "pc_input_second_after": second,
        "pc_input_combined_before": before["combined"],
        "pc_input_combined_after": combined,
        "pc_output_first": outputs["first"],
        "pc_output_second": outputs["second"],
        "pc_output_combined": outputs["combined"],
        "pc_output_repeat": outputs["repeat"],
    }.items():
        artifacts[name] = _write_layout(raw_dir, name, vector, rank)
    for vector in before.values():
        vector.destroy()
    expected.destroy()
    for vector in outputs.values():
        vector.destroy()
    first.destroy()
    second.destroy()
    combined.destroy()
    return {
        "direction_construction": "PETSc_global_row_parity",
        "alpha": [PC_ALPHA.real, PC_ALPHA.imag],
        "beta": [PC_BETA.real, PC_BETA.imag],
        "linearity_relative": float(linearity),
        "repeat_relative": float(repeat),
        "input_unchanged": bool(input_unchanged),
        "finite": bool(finite),
        "slave_local_indices": slave.tolist(),
        "slave_constraint_absolute": float(slave_max),
        "artifacts": artifacts,
    }


def _resource() -> dict[str, Any]:
    value = dict(resource_authority_sample(os.getpid()))
    value["scope"] = "rank_process_tree_diagnostic_excludes_launcher"
    return value


def _closeout(
    comm: MPI.Comm,
    raw_dir: Path,
    record_path: Path,
    expected_sha: str,
    rank_fact: dict[str, Any],
) -> None:
    _append_stage_marker(raw_dir, "a3_metadata_collect_begin", comm.rank)
    rank_facts = comm.allgather(rank_fact)
    _append_stage_marker(raw_dir, "a3_metadata_collect_end", comm.rank)
    result: dict[str, Any] = {"ok": False}
    if comm.rank == 0:
        try:
            root = Path.cwd()
            source_end = _source_identity(root, expected_sha)
            if source_end["branch"] != BRANCH:
                raise RuntimeError("worker branch changed before closeout")
            by_role = {}
            for role in ("source", "rhs", "rhs_repeat", "final_solution", "final_action", "final_true_residual"):
                by_role[role] = {
                    "role": next(item["canonical"][role]["role"] for item in rank_facts),
                    "shards": [item["canonical"][role] for item in rank_facts],
                }
            pc_roles = tuple(rank_facts[0]["pc"]["artifacts"])
            pc_artifacts = {
                role: {"shards": [item["pc"]["artifacts"][role] for item in rank_facts]}
                for role in pc_roles
            }
            root_outer = next(item["outer"] for item in rank_facts if item["outer"] is not None)
            pc_facts = [item["pc"] for item in rank_facts]
            fixture_audit = rank_facts[0]["fixture_audit"]
            high_action_audit = rank_facts[0]["high_action_audit"]
            outer = root_outer
            production = {
                "build_hx": bool(fixture_audit.get("hx_audit", {}).get("constructed", False)),
                "scalar_node_matrix": bool(rank_facts[0]["node_audit"].get("scalar_node_matrix", False)),
                "high_order_global_aij": bool(fixture_audit.get("high_order_global_aij", False)),
                "global_dense_transfer": bool(fixture_audit.get("global_transfer_matrix", False)),
                "global_numeric_allgather": bool(fixture_audit.get("global_numeric_allgather", False)),
                "global_direct_coarse": bool(high_action_audit.get("global_direct_coarse", False)),
                "pcgamg_hierarchy_built": bool(fixture_audit.get("pcgamg_hierarchy_built", False)),
                "p6_exact_edge_factor_built": False,
                "small_oracle_direct_coarse": True,
                "metadata_allgather_only": True,
                "numeric_allgather": False,
            }
            record = {
                "schema": SCHEMA,
                "stage": "s4-a3",
                "case": rank_facts[0]["case"],
                "degree": int(rank_facts[0]["degree"]),
                "h_nm": 50.0,
                "mpi_size": int(comm.size),
                "source_name": rank_facts[0]["source_name"],
                "variant": VARIANT,
                "method": "lor_edge_geometric_mg_v1",
                "settings": {
                    "ksp_type": "gmres",
                    "pc_side": "right",
                    "norm_type": "unpreconditioned",
                    "restart": RESTART,
                    "cycle_max_it": RESTART,
                    "max_it": MAX_IT,
                    "zero_initial_guess": True,
                    "residual_replacement": True,
                    "residual_limit": RESIDUAL_LIMIT,
                    "checkpoint_writer": None,
                },
                "vcycle_settings": {
                    "chebyshev_degree": 3,
                    "power_steps": 10,
                    "lambda_hi_factor": 1.10,
                    "lambda_lo_factor": 0.10,
                    "pre": 1,
                    "post": 1,
                    "vcycle": 1,
                    "coarse_backend": "petsc-preonly-lu-mumps",
                    "coarse_scope": "p2_p3_small_oracle_only",
                },
                "source": rank_facts[0]["source"],
                "source_end": source_end,
                "runtime": rank_facts[0]["runtime"],
                "command": rank_facts[0]["command"],
                "launch_command": rank_facts[0]["launch_command"],
                "raw_dir": str(raw_dir.resolve()),
                "record_path": str(record_path.resolve()),
                "provenance": rank_facts[0]["provenance"],
                "source_unchanged": all(
                    bool(item["source_unchanged"]) for item in rank_facts
                ),
                "production": production,
                "fixture_audit": fixture_audit,
                "high_action_audit": high_action_audit,
                "outer": outer,
                "pc_legality": {
                    "direction_construction": "PETSc_global_row_parity",
                    "alpha": [PC_ALPHA.real, PC_ALPHA.imag],
                    "beta": [PC_BETA.real, PC_BETA.imag],
                    "linearity_relative": max(item["linearity_relative"] for item in pc_facts),
                    "repeat_relative": max(item["repeat_relative"] for item in pc_facts),
                    "input_unchanged": all(item["input_unchanged"] for item in pc_facts),
                    "finite": all(item["finite"] for item in pc_facts),
                    "slave_constraint_absolute": max(item["slave_constraint_absolute"] for item in pc_facts),
                    "slave_local_indices_by_rank": {
                        str(item["rank"]): item["pc"]["slave_local_indices"] for item in rank_facts
                    },
                    "artifacts": pc_artifacts,
                },
                "canonical_artifacts": by_role,
                "rank_facts": rank_facts,
            }
            payload = _json_bytes(record)
            record_path.write_bytes(payload)
            _append_stage_marker(raw_dir, "a3_record_written", 0)
            result = {"ok": True, "bytes": len(payload)}
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result = comm.bcast(result, root=0)
    if not result["ok"]:
        raise RuntimeError(str(result["error"]))
    comm.Barrier()


def run_worker(
    raw_dir: Path,
    record_path: Path,
    expected_source_sha: str,
    expected_mpi_size: int,
    case: str,
    source_name: str,
) -> None:
    comm = MPI.COMM_WORLD
    if case not in CASES or source_name not in SOURCES:
        raise ValueError("S4-A3 case/source is not frozen")
    degree, case_mpi_size = CASES[case]
    if case_mpi_size != expected_mpi_size or comm.size != expected_mpi_size:
        raise ValueError("case MPI identity does not close")
    _prepare_paths(raw_dir, record_path, comm, stage="s4-a3")
    _append_stage_marker(raw_dir, "a3_paths_ready", comm.rank)
    root = Path.cwd()
    source = _source_identity(root, expected_source_sha) if comm.rank == 0 else None
    source = comm.bcast(source, root=0)
    if source["branch"] != BRANCH:
        raise RuntimeError("wrong execution branch")
    runtime = _runtime_identity(root, expected_mpi_size)
    _append_stage_marker(raw_dir, "a3_runtime_identity", comm.rank)

    fixture = None
    transfer_case = None
    pc = None
    source_vector = source_before = rhs = rhs_repeat = final_solution = final_action = final_true = None
    result: dict[str, Any] | None = None
    try:
        fixture = RealL2PositiveHXFixture(
            degree, comm, variant=VARIANT, build_hx=False
        )
        transfer_case = ImplicitLORTransferCase(fixture)
        pc = HighLORGeometricVcyclePC(transfer_case)
        _append_stage_marker(raw_dir, "a3_fixture_and_pc_built", comm.rank)
        source_vector, source_facts = fixture.build_l2_source(source_name)
        source_before = source_vector.copy()
        rhs = fixture.apply_high_action_copy(source_vector)
        rhs_repeat = fixture.apply_high_action_copy(source_vector)
        pc_facts = _pc_legality(fixture, pc, rhs, raw_dir, comm.rank)
        _append_stage_marker(raw_dir, "a3_pc_legality", comm.rank)

        _append_stage_marker(raw_dir, "a3_outer_started", comm.rank)
        result = run_restart20_cycles(
            rhs,
            fixture.apply_high_action_copy,
            pc.apply,
            max_it=MAX_IT,
            residual_limit=RESIDUAL_LIMIT,
            resource_sample=_resource,
            start_iteration=0,
            first_checkpoint_iteration=None,
            checkpoint_interval=200,
            checkpoint_writer=None,
            stop_on_true_residual=True,
        )
        _append_stage_marker(raw_dir, "a3_outer_finished", comm.rank)
        final_solution = result["final_solution"]
        final_action = fixture.apply_high_action_copy(final_solution)
        final_true = rhs.copy()
        final_true.axpy(-1.0, final_action)
        direct_command = [
            str(Path(sys.executable).absolute()),
            "-m",
            "benchmarks.run_task038_full3d_lor_edge_geometric_mg",
            "--stage",
            "s4-a3",
            "--case",
            case,
            "--source",
            source_name,
            "--raw-dir",
            str(raw_dir.resolve()),
            "--record",
            str(record_path.resolve()),
            "--expected-source-sha",
            expected_source_sha,
            "--expected-mpi-size",
            str(expected_mpi_size),
        ]
        launch_command = _launch_command(direct_command, expected_mpi_size)
        provenance = _partition_invariant_identities(degree, source_name)
        canonical = {
            "source": _write_canonical(raw_dir, fixture, source_vector, "source", "primal", comm.rank),
            "rhs": _write_canonical(raw_dir, fixture, rhs, "rhs", "dual", comm.rank),
            "rhs_repeat": _write_canonical(raw_dir, fixture, rhs_repeat, "rhs_repeat", "dual", comm.rank),
            "final_solution": _write_canonical(raw_dir, fixture, final_solution, "final_solution", "primal", comm.rank),
            "final_action": _write_canonical(raw_dir, fixture, final_action, "final_action", "dual", comm.rank),
            "final_true_residual": _write_canonical(raw_dir, fixture, final_true, "final_true_residual", "dual", comm.rank),
        }
        fixture_audit = _jsonable(fixture.audit)
        fixture_audit["hx_audit"] = _jsonable(fixture.hx.audit if fixture.hx is not None else {
            "constructed": False,
            "high_order_aij": False,
            "global_transfer_matrix": False,
            "global_numeric_allgather": False,
        })
        scalar_outer = _scalar_outer(result)
        source_unchanged = bool(np.array_equal(source_before.array, source_vector.array))
        source_before.destroy()
        source_before = None
        rank_fact = {
            "rank": int(comm.rank),
            "case": case,
            "degree": int(degree),
            "source_name": source_name,
            "runtime": _jsonable(runtime),
            "command": direct_command,
            "launch_command": launch_command,
            "source": _jsonable(source),
            "source_facts": _jsonable(source_facts),
            "provenance": provenance,
            "fixture_audit": fixture_audit,
            "high_action_audit": _jsonable(fixture.high_action.audit),
            "node_audit": _jsonable(fixture.lor_node_constraint_audit),
            "pc": {**pc_facts, "rank": int(comm.rank)},
            "canonical": canonical,
            "outer": scalar_outer if comm.rank == 0 else None,
            "outer_scalar": scalar_outer,
            "outer_final_solution_ownership": list(final_solution.getOwnershipRange()),
            "source_unchanged": source_unchanged,
        }
        _closeout(comm, raw_dir, record_path, expected_source_sha, rank_fact)
        if comm.rank == 0:
            print(json.dumps({"record": str(record_path), "case": case, "source": source_name}), flush=True)
    finally:
        if result is not None:
            destroy_krylov_result(result)
        for vector in (source_before, final_action, final_true, rhs_repeat, rhs, source_vector):
            if vector is not None:
                vector.destroy()
        if pc is not None:
            pc.destroy()
        elif transfer_case is not None:
            transfer_case.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("s4-a3",), required=True)
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    parser.add_argument("--source", choices=SOURCES, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, required=True)
    args = parser.parse_args(argv)
    run_worker(
        args.raw_dir,
        args.record,
        args.expected_source_sha,
        args.expected_mpi_size,
        args.case,
        args.source,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
