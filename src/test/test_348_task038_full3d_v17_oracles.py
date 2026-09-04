"""Focused pure contracts for the V17 Oracle A/B building blocks."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pytest

from benchmarks import run_task038_v17_oracles as runner
from benchmarks import task038_v17_oracle_checker as checker
from src.solvers import disk_backed_flexible_gmres as disk


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source() -> dict[str, object]:
    return {
        "commit_sha": checker.SOURCE_SHA,
        "branch": checker.BRANCH,
        "upstream": f"origin/{checker.BRANCH}",
        "upstream_sha": checker.SOURCE_SHA,
        "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
        "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
        "ahead": 0,
        "behind": 0,
        "tracked_worktree_clean": True,
        "qualified_activation": "1",
        "input_sha256": checker.INPUT_SHA256,
    }


def test_v17_jsonable_serializes_nested_mappingproxy(tmp_path: Path) -> None:
    value = MappingProxyType(
        {
            "audit": MappingProxyType(
                {"pair": "owner", "flags": {"numeric_allgather": False}}
            )
        }
    )
    output = tmp_path / "mappingproxy.json"

    runner._write_json(output, value)

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "audit": {"pair": "owner", "flags": {"numeric_allgather": False}}
    }


def _reference_right_fgmres(
    rhs: np.ndarray,
    matrix: np.ndarray,
    initial: np.ndarray,
    steps: int,
) -> tuple[np.ndarray, float]:
    action = lambda value: matrix @ value
    pc_calls = 0

    def pc(value: np.ndarray) -> np.ndarray:
        nonlocal pc_calls
        pc_calls += 1
        return (1.0 + 0.01 * pc_calls) * value

    residual = rhs - action(initial)
    beta = float(np.linalg.norm(residual))
    vectors = [residual / beta]
    preconditioned: list[np.ndarray] = []
    hessenberg = np.zeros((steps + 1, steps), dtype=np.complex128)
    for column in range(steps):
        z = pc(vectors[column])
        preconditioned.append(z)
        work = action(z)
        for _ in range(2):
            for previous, vector in enumerate(vectors):
                coefficient = np.vdot(vector, work)
                hessenberg[previous, column] += coefficient
                work -= coefficient * vector
        next_norm = float(np.linalg.norm(work))
        hessenberg[column + 1, column] = next_norm
        if next_norm == 0.0:
            break
        vectors.append(work / next_norm)
    used = len(preconditioned)
    h_rows = used + 1
    coefficients = np.linalg.lstsq(
        hessenberg[:h_rows, :used],
        np.r_[beta, np.zeros(h_rows - 1, dtype=np.complex128)],
        rcond=None,
    )[0]
    solution = initial.copy()
    for coefficient, vector in zip(coefficients, preconditioned, strict=True):
        solution += coefficient * vector
    return solution, float(np.linalg.norm(rhs - action(solution))) / beta


def test_disk_fgmres_matches_memory_reference_and_records_disk_contract(
    tmp_path: Path,
) -> None:
    rows = 32
    matrix = np.diag(np.linspace(1.0, 2.0, rows)).astype(np.complex128)
    rhs = (1.0 + 0.2j) ** np.arange(rows, dtype=np.complex128)
    initial = np.linspace(0.1, 0.4, rows).astype(np.complex128)
    pc_calls: list[int] = []

    def action(value: np.ndarray) -> np.ndarray:
        return matrix @ value

    def pc(value: np.ndarray) -> np.ndarray:
        pc_calls.append(1)
        return (1.0 + 0.01 * len(pc_calls)) * value

    observations: list[int] = []
    basis_root = tmp_path / "unrestarted" / "basis"
    basis_root.parent.mkdir()
    result = disk.run_disk_backed_right_fgmres(
        rhs,
        action,
        pc,
        scratch_root=basis_root,
        max_steps=20,
        initial_solution=initial,
        observer=lambda row: observations.append(int(row["iteration"])),
    )
    reference, reference_residual = _reference_right_fgmres(rhs, matrix, initial, 20)

    np.testing.assert_allclose(result["solution"], reference, rtol=1e-11, atol=1e-11)
    assert result["final_relative_residual"] == pytest.approx(reference_residual, abs=1e-12)
    assert observations == [20]
    assert result["iterations"] == 20
    assert len(pc_calls) == 20
    audit = result["audit"]
    assert audit["action_count"] == 22
    assert audit["pc_count"] == 20
    assert audit["explicit_action_count"] == 1
    assert audit["input_unchanged"] is True
    assert audit["input_rhs_before_sha256"] == disk._array_sha256(rhs)
    assert audit["input_rhs_after_sha256"] == disk._array_sha256(rhs)
    assert audit["input_initial_before_sha256"] == disk._array_sha256(initial)
    assert audit["input_initial_after_sha256"] == disk._array_sha256(initial)
    assert audit["orthogonalization_passes"] == 2
    assert audit["persistent_full_vector_buffer_count"] == 7
    assert audit["callback_output_buffer_count"] == 1
    assert "z_read" not in audit["buffer_lifecycle"]["arnoldi"]["names"]
    assert audit["buffer_lifecycle"]["arnoldi"]["count"] == 8
    assert all(item["count"] == 8 for item in audit["buffer_lifecycle"].values())
    assert audit["sync_columns"] == [{"iteration": 20, "V": 20, "Z": 20}]
    assert audit["orthogonality_max_abs"] <= disk.ORTHOGONALITY_LIMIT
    assert all(
        row["explicit_vs_arnoldi_relative"] <= disk.EXPLICIT_ARNOLDI_LIMIT
        for row in result["history"]
    )

    manifest = json.loads((basis_root / "basis_manifest.json").read_text())
    assert manifest["V"]["written_count"] == 21
    assert manifest["Z"]["written_count"] == 20
    assert manifest["H"]["sha256"] == audit["hessenberg"]["sha256"]
    for name in ("V", "Z"):
        descriptor = manifest[name]
        path = basis_root / descriptor["path"]
        assert path.stat().st_size == descriptor["allocated_bytes"]
    with (basis_root / "V.bin").open("rb") as stream:
        first_column = stream.read(rows * 16)
    assert hashlib.sha256(first_column).hexdigest() == manifest["V"]["records"][0]["sha256"]
    with pytest.raises(FileExistsError):
        disk.run_disk_backed_right_fgmres(
            rhs,
            action,
            pc,
            scratch_root=basis_root,
            max_steps=20,
            initial_solution=initial,
        )
    with pytest.raises(ValueError):
        disk.run_disk_backed_right_fgmres(
            rhs,
            action,
            pc,
            scratch_root=tmp_path / "over-cap",
            max_steps=501,
            initial_solution=initial,
        )


def test_disk_fgmres_zero_residual_and_happy_breakdown_are_defined(
    tmp_path: Path,
) -> None:
    zero_parent = tmp_path / "zero"
    zero_parent.mkdir()
    value = np.asarray([1.0 + 0.25j], dtype=np.complex128)
    zero = disk.run_disk_backed_right_fgmres(
        value,
        lambda vector: vector.copy(),
        lambda vector: vector.copy(),
        scratch_root=zero_parent / "basis",
        max_steps=1,
        initial_solution=value.copy(),
    )
    assert zero["iterations"] == 0
    assert zero["final_true_residual_norm"] == 0.0
    assert zero["history"] == []

    happy_parent = tmp_path / "happy"
    happy_parent.mkdir()
    happy = disk.run_disk_backed_right_fgmres(
        np.asarray([1.0 + 0.0j], dtype=np.complex128),
        lambda vector: np.zeros_like(vector),
        lambda vector: vector.copy(),
        scratch_root=happy_parent / "basis",
        max_steps=1,
    )
    breakdown = happy["audit"]["happy_breakdown_records"]
    assert len(breakdown) == 1
    assert breakdown[0]["triggered"] is True
    assert breakdown[0]["threshold"] > 0.0


def test_mumps_analysis_and_solve_use_one_real_complex_factor() -> None:
    code = """
import json
import numpy as np
from petsc4py import PETSc
from src.solvers import fullspace_v17_p3_oracle as oracle

matrix = PETSc.Mat().createAIJ(size=(2, 2), nnz=2, comm=PETSc.COMM_SELF)
matrix.setUp()
matrix.setValues(
    np.asarray([0, 1], dtype=PETSc.IntType),
    np.asarray([0, 1], dtype=PETSc.IntType),
    np.asarray(
        [[2.0 + 0.2j, 1.0 - 0.1j], [0.5 + 0.3j, 3.0 - 0.4j]],
        dtype=PETSc.ScalarType,
    ),
)
matrix.assemble()
rhs = matrix.createVecRight()
rhs.array[:] = np.asarray([1.0 + 0.5j, 2.0 - 0.25j], dtype=PETSc.ScalarType)
factor = None
solution = None
check = matrix.createVecLeft()
try:
    factor, facts = oracle.analyze_mumps_p3(matrix)
    blocked, blocked_facts = oracle.solve_mumps_p3(
        factor,
        matrix,
        rhs,
        predicted_peak_bytes=oracle.ORACLE_A_PARENT_HARD_BYTES,
    )
    solution, solve_facts = oracle.solve_mumps_p3(
        factor,
        matrix,
        rhs,
        predicted_peak_bytes=1,
    )
    matrix.mult(solution, check)
    check.axpy(-1.0, rhs)
    print(json.dumps({
        "preferred_ordering": facts["preferred_ordering"],
        "ordering_via": facts["ordering_via"],
        "analysis_only": facts["analysis_only"],
        "symbolic_calls": facts["symbolic_calls"],
        "numeric_before": factor.numeric_calls - 1,
        "blocked": blocked is None and blocked_facts["resource_preflight"] == "blocked",
        "numeric_calls": solve_facts["numeric_calls"],
        "solve_calls": solve_facts["solve_calls"],
        "infog16": facts["raw_info"]["infog"].get("16"),
        "residual": check.norm(),
    }, allow_nan=False))
finally:
    if solution is not None:
        solution.destroy()
    check.destroy()
    rhs.destroy()
    if factor is not None:
        factor.destroy()
    matrix.destroy()
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"MUMPS subprocess rc={completed.returncode}\n"
        f"stdout={completed.stdout}\nstderr={completed.stderr}"
    )
    facts = json.loads(completed.stdout)
    assert facts == {
        "preferred_ordering": "external",
        "ordering_via": "mumps_internal_auto_icntl7",
        "analysis_only": True,
        "symbolic_calls": 1,
        "numeric_before": 0,
        "blocked": True,
        "numeric_calls": 1,
        "solve_calls": 1,
        "infog16": facts["infog16"],
        "residual": facts["residual"],
    }
    assert isinstance(facts["infog16"], int)
    assert facts["residual"] <= 1.0e-12


def _vector_descriptor(raw_dir: Path, relative: str, values: np.ndarray) -> dict[str, object]:
    path = raw_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        np.save(stream, values, allow_pickle=False)
    return {
        "relative_path": str(path.relative_to(raw_dir.parent)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "array_sha256": hashlib.sha256(
            memoryview(np.ascontiguousarray(values)).cast("B")
        ).hexdigest(),
        "dtype": "complex128",
        "shape": [int(values.size)],
        "norm": float(np.linalg.norm(values)),
        "finite": True,
    }


def _make_basis_checker_context(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, object], Path]:
    raw_dir = tmp_path / "raw"
    basis_root = raw_dir / "unrestarted" / "basis"
    basis_root.parent.mkdir(parents=True)
    rows = 32
    matrix = np.diag(np.linspace(1.0, 2.0, rows)).astype(np.complex128)
    rhs = (1.0 + 0.2j) ** np.arange(rows, dtype=np.complex128)
    result = disk.run_disk_backed_right_fgmres(
        rhs,
        lambda value: matrix @ value,
        lambda value: value.copy(),
        scratch_root=basis_root,
        max_steps=20,
    )
    audit = dict(result["audit"])
    manifest_path = basis_root / "basis_manifest.json"
    audit["scratch_manifest_sha256"] = _sha256(manifest_path)
    hessenberg_path = basis_root / "H.npy"
    facts = {
        "audit": audit,
        "hessenberg_shape": list(result["hessenberg"].shape),
        "hessenberg": {
            "relative_path": str(hessenberg_path.relative_to(raw_dir.parent)),
            "bytes": hessenberg_path.stat().st_size,
            "sha256": _sha256(hessenberg_path),
            "dtype": "complex128",
            "shape": list(result["hessenberg"].shape),
        },
    }
    return {"raw_dir": raw_dir}, facts, basis_root


@pytest.mark.parametrize("tamper", ("H", "V", "Z", "sync"))
def test_checker_b_basis_raw_mutations_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tamper: str,
) -> None:
    monkeypatch.setattr(checker, "B_STEPS", 20)
    context, facts, basis_root = _make_basis_checker_context(tmp_path)
    if tamper == "H":
        path = basis_root / "H.npy"
        values = np.asarray(np.load(path, allow_pickle=False))
        values[0, 0] += 1.0
        with path.open("wb") as stream:
            np.save(stream, values, allow_pickle=False)
        expected = "H SHA/size mismatch"
    elif tamper in {"V", "Z"}:
        path = basis_root / f"{tamper}.bin"
        with path.open("r+b") as stream:
            first = stream.read(1)
            stream.seek(0)
            stream.write(bytes([first[0] ^ 1]))
        expected = f"{tamper} column SHA mismatch"
    else:
        manifest_path = basis_root / "basis_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["V"]["sync_columns"] = []
        _write_json(manifest_path, manifest)
        facts["audit"]["scratch_manifest_sha256"] = _sha256(manifest_path)
        expected = "V fsync cadence mismatch"
    errors: list[str] = []
    checker._check_basis(context, facts, errors)
    assert any(expected in error for error in errors), errors


def _canonical_fixture_descriptor(
    raw_dir: Path,
    name: str,
    role: str,
    values: np.ndarray,
    *,
    identity_name: str | None = None,
) -> dict[str, object]:
    from benchmarks.canonical_vector_artifacts import (
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )

    key_name = name if identity_name is None else identity_name
    packets = tuple(
        (
            (
                role,
                3,
                ("fixture", key_name),
                index,
                ("fixture",),
                None,
                None,
            ),
            complex(value),
        )
        for index, value in enumerate(values)
    )
    directory = raw_dir / "canonical"
    directory.mkdir(parents=True, exist_ok=True)
    shard_path = directory / f"{name}.rank0000.jsonl"
    shard = write_canonical_packet_shard(
        shard_path, packets, audit_packets=True
    )
    shard.update(
        {
            "rank": 0,
            "key_inventory_sha256": runner._canonical_key_inventory_hash(packets),
        }
    )
    manifest = canonical_shard_manifest(
        role=role,
        mpi_size=1,
        shard_metadata=(shard,),
        extractor_audit={
            "role": role,
            "fixture": True,
            "numeric_allgather": False,
            **(
                {"slave_exclusion": True}
                if role == "full_fe_dual"
                else {}
            ),
        },
    )
    manifest["key_inventory_sha256"] = hashlib.sha256(
        json.dumps(
            [
                {
                    "rank": 0,
                    "key_inventory_sha256": shard["key_inventory_sha256"],
                }
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    manifest_path = directory / f"{name}.manifest.json"
    manifest_sha = write_canonical_manifest(manifest_path, manifest)
    return {
        "manifest_relative_path": str(
            manifest_path.relative_to(raw_dir.parent)
        ),
        "manifest_sha256": manifest_sha,
        "role": role,
        "packet_count": int(manifest["global_summed_packet_count"]),
        "key_inventory_sha256": manifest["key_inventory_sha256"],
        "extractor_audit": manifest["extractor_audit"],
        "mpi_size": 1,
    }


def _process_result(stage: str) -> dict[str, object]:
    return {
        "stage": stage,
        "argv": ["synthetic", stage],
        "returncode": 0,
        "stop_reason": None,
        "signals": [],
        "max_swap_bytes": 0,
        "all_status_readable": True,
        "process_group_gone": True,
        "lifecycle_failure": False,
        "rss_watchdog_bytes": checker.A_HARD_BYTES,
    }


def _owned_descriptor(descriptor: dict[str, object]) -> dict[str, object]:
    return {
        **descriptor,
        "finite": True,
        "owned_slave_max": 0.0,
        "owned_slave_count": 0,
    }


def _make_oracle_a_artifact(tmp_path: Path) -> Path:
    root = tmp_path / "oracle-a"
    raw = root / "raw"
    cache = root / "jit_cache"
    markers = root / "markers"
    for directory in (raw, cache, markers):
        directory.mkdir(parents=True)
    values = np.asarray([1.0 + 0.5j, 2.0 - 0.25j], dtype=np.complex128)
    zero = np.zeros(2, dtype=np.complex128)
    r6 = _vector_descriptor(raw, "A1/r6.npy", values)
    r3 = _vector_descriptor(raw, "A1/r3.npy", values)
    rhs = _vector_descriptor(raw, "A2/rhs.npy", values)
    action2 = _vector_descriptor(raw, "A2/action.npy", values)
    residual2 = _vector_descriptor(raw, "A2/residual.npy", zero)
    e3 = _vector_descriptor(raw, "A2/e3.npy", values)
    e6_full = _vector_descriptor(raw, "A3/e6_full.npy", values)
    e6_algebraic = _vector_descriptor(raw, "A3/e6_algebraic.npy", zero)
    action = _vector_descriptor(raw, "A3/action.npy", values)
    r6_new = _vector_descriptor(raw, "A3/r6_new.npy", zero)
    r3_new = _vector_descriptor(raw, "A3/r3_new.npy", zero)
    r6_canonical = _canonical_fixture_descriptor(
        raw, "A1_r6", "full_fe_dual", values, identity_name="p6_dual"
    )
    r3_canonical = _canonical_fixture_descriptor(
        raw, "A1_r3", "full_fe_dual", values, identity_name="p3_dual"
    )
    e3_canonical = _canonical_fixture_descriptor(
        raw, "A2_e3", "full_fe", values, identity_name="p3_primal"
    )
    e3_loaded_canonical = _canonical_fixture_descriptor(
        raw,
        "A3_e3_loaded",
        "full_fe",
        values,
        identity_name="p3_primal",
    )
    e6_full_canonical = _canonical_fixture_descriptor(
        raw, "A3_e6_full", "full_fe", values, identity_name="p6_primal"
    )
    action_canonical = _canonical_fixture_descriptor(
        raw,
        "A3_action",
        "full_fe_dual",
        values,
        identity_name="p6_dual",
    )
    r6_new_canonical = _canonical_fixture_descriptor(
        raw,
        "A3_r6_new",
        "full_fe_dual",
        zero,
        identity_name="p6_dual",
    )
    r3_new_canonical = _canonical_fixture_descriptor(
        raw,
        "A3_r3_new",
        "full_fe_dual",
        zero,
        identity_name="p3_dual",
    )
    r6_facts = _owned_descriptor(r6)
    r3_facts = _owned_descriptor(r3)
    rhs_facts = _owned_descriptor(rhs)
    action2_facts = _owned_descriptor(action2)
    residual2_facts = _owned_descriptor(residual2)
    e3_facts = _owned_descriptor(e3)
    e3_loaded_facts = {
        **e3_facts,
        "source_array_sha256": e3_facts["array_sha256"],
        "loaded_array_sha256": e3_facts["array_sha256"],
        "loaded_unchanged": True,
    }
    e6_full_facts = _owned_descriptor(e6_full)
    e6_full_facts.update(
        {
            "owned_slave_max": float(np.max(np.abs(values))),
            "owned_slave_count": 1,
            "fine_mpc_constraint_residual": 1.0e-12,
            "transfer_last_apply_facts": {
                "operation": "primal",
                "finite": True,
                "input_unchanged": True,
                "fine_mpc_constraint_residual": 1.0e-12,
            },
        }
    )
    e6_algebraic_facts = _owned_descriptor(e6_algebraic)
    action_facts = _owned_descriptor(action)
    r6_new_facts = _owned_descriptor(r6_new)
    r3_new_facts = _owned_descriptor(r3_new)

    transfer_audit = {
        "global_transfer_matrix": False,
        "numeric_allgather": False,
        "static_condensation": False,
        "owner_local": True,
        "coarse_dual_reduction": "C^H_once",
    }

    def record(stage: str) -> dict[str, object]:
        base = {
            "schema": (
                "task038.v17.oracle-a3.v2"
                if stage == "A3"
                else f"task038.v17.oracle-{stage.lower()}.v1"
            ),
            "stage": stage,
            "source": _source(),
            "input": {
                "template_sha256": checker.INPUT_SHA256,
                "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
                "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
            },
        }
        if stage == "A1":
            base.update(
                {
                    "checkpoint": {
                        "iteration": 1000,
                        "input_identity_sha256": checker.CHECKPOINT_INPUT_IDENTITY_SHA256,
                        "operator_identity_sha256": checker.CHECKPOINT_OPERATOR_IDENTITY_SHA256,
                        "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
                        "manifest_sha256": checker.CHECKPOINT_MANIFEST_SHA256,
                        "solution_sha256": checker.CHECKPOINT_SOLUTION_SHA256,
                        "source_sha": checker.CHECKPOINT_SOURCE_SHA,
                        "mpi_size": 1,
                    },
                    "vectors": {
                        "r6": {**r6_facts, "canonical": r6_canonical},
                        "r3": {**r3_facts, "canonical": r3_canonical},
                    },
                    "rhs": r6_facts,
                    "checkpoint_reproduction": {
                        "expected": checker.CHECKPOINT_EXPLICIT_RESIDUAL,
                        "actual": checker.CHECKPOINT_EXPLICIT_RESIDUAL,
                        "absolute_difference": 0.0,
                        "relative_difference": 0.0,
                        "relative_limit": 1.0e-8,
                    },
                    "input_unchanged": {
                        "checkpoint_solution_before_sha256": r6["sha256"],
                        "checkpoint_solution_after_sha256": r6["sha256"],
                        "rhs_before_sha256": r6["sha256"],
                        "rhs_after_sha256": r6["sha256"],
                        "unchanged": True,
                    },
                    "operation_counts": {
                        "p6_action": 1,
                        "p63_adjoint": 1,
                        "p63_primal": 0,
                    },
                    "architecture": {
                        "global_physical_aij": False,
                        "global_schur": False,
                        "dense_dtn": False,
                        "factor": False,
                        "numeric_allgather": False,
                        "phase_once": True,
                        "p63_owner_transfer": transfer_audit,
                    },
                }
            )
        elif stage == "A2":
            base.update(
                {
                    "vectors": {
                        "rhs": {**rhs_facts},
                        "action": {**action2_facts},
                        "residual": {**residual2_facts},
                        "e3": {**e3_facts, "canonical": e3_canonical},
                    },
                    "rhs": {
                        "before": {**rhs_facts},
                        "after": {**rhs_facts},
                        "unchanged": True,
                    },
                    "finite": True,
                    "explicit_true_residual": 0.0,
                    "direct_solve": {
                        "resource_preflight": "passed",
                        "analysis_only": False,
                        "numeric_factor_called": True,
                        "solve_called": True,
                        "symbolic_calls": 1,
                        "numeric_calls": 1,
                        "solve_calls": 1,
                    },
                    "architecture": {
                        "global_physical_aij": True,
                        "production_global_aij": False,
                        "numeric_allgather": False,
                        "factor_destroyed_before_a3": True,
                        "phase_once": True,
                    },
                }
            )
        else:
            base.update(
                {
                    "vectors": {
                        "r6": {**r6_facts, "canonical": r6_canonical},
                        "r3": {**r3_facts, "canonical": r3_canonical},
                        "e3_loaded": {
                            **e3_loaded_facts,
                            "canonical": e3_loaded_canonical,
                        },
                        "e6_full": {
                            **e6_full_facts,
                            "canonical": e6_full_canonical,
                        },
                        "e6_algebraic": {
                            **e6_algebraic_facts,
                        },
                        "action": {
                            **action_facts,
                            "input_array_sha256": e6_algebraic_facts[
                                "array_sha256"
                            ],
                            "canonical": action_canonical,
                        },
                        "r6_new": {
                            **r6_new_facts,
                            "canonical": r6_new_canonical,
                        },
                        "r3_new": {
                            **r3_new_facts,
                            "canonical": r3_new_canonical,
                        },
                    },
                    "loaded_inputs": {
                        "r6": {
                            "before": {**r6_facts},
                            "after": {**r6_facts},
                            "unchanged": True,
                        },
                        "e3": {
                            "before": {**e3_facts},
                            "after": {**e3_facts},
                            "unchanged": True,
                        },
                    },
                    "rho_ref": 0.0,
                    "rho3": 0.0,
                    "operation_counts": {"p6_action": 1, "p63_primal": 1, "p63_adjoint": 1},
                    "architecture": {
                        "global_physical_aij": False,
                        "global_schur": False,
                        "dense_dtn": False,
                        "factor": False,
                        "numeric_allgather": False,
                        "phase_once": True,
                        "p63_owner_transfer": transfer_audit,
                    },
                }
            )
        return base

    stage_paths = {}
    for stage in ("A1", "A2", "A3"):
        path = raw / f"{stage}_record.json"
        _write_json(path, record(stage))
        stage_paths[stage] = path

    marker_rows = []
    for index, name in enumerate(checker.A_MARKER_ORDER):
        path = markers / f"{index:03d}_{name}.json"
        _write_json(path, {"name": name})
        marker_rows.append({"name": name, "sha256": _sha256(path)})
    marker_manifest = root / "marker_manifest.json"
    _write_json(marker_manifest, marker_rows)

    samples = {
        "rss_bytes": 100_000,
        "swap_bytes": 0,
        "all_status_readable": True,
        "compiler_descendant_count": 0,
    }
    (root / "parent_process.jsonl").write_text(json.dumps(samples) + "\n")
    stages = []
    for stage in ("A1", "A2", "A3"):
        item = _process_result(stage)
        item.update(
            {
                "stage": stage,
                "record": str(stage_paths[stage].relative_to(root)),
                "sha256": _sha256(stage_paths[stage]),
            }
        )
        stages.append(item)
    cache_empty = checker._cache_snapshot(cache, [])
    parent = {
        "schema": "task038.v17.oracle.parent.v1",
        "source": _source(),
        "phase": "oracle-a",
        "resource_contract": {
            "warning_bytes": checker.A_HARD_BYTES - 2_000_000_000,
            "rss_watchdog_bytes": checker.A_HARD_BYTES,
            "hard_gate_bytes": checker.A_HARD_BYTES,
            "swap_gate_bytes": 0,
        },
        "paths": {"process_samples": "parent_process.jsonl"},
        "cache": {
            "initial": cache_empty,
            "stage_snapshots": [
                {"stage": stage, "snapshot": cache_empty}
                for stage in ("A1", "A2", "A3")
            ],
        },
        "jit_groups": [],
        "expected_mpi_size": 1,
        "classification": "RAW_COMPLETE_PENDING_CHECKER",
        "children": [],
        "stages": stages,
        "process": {"sample_count": 1, "peak_rss_bytes": 100_000, "max_swap_bytes": 0, "all_status_readable": True},
        "markers": {
            "relative_path": "marker_manifest.json",
            "sha256": _sha256(marker_manifest),
            "names": list(checker.A_MARKER_ORDER),
        },
        "error": None,
    }
    parent_path = root / "parent_record.json"
    _write_json(parent_path, parent)
    return parent_path


def test_a1_fixture_canonical_manifests_are_hash_bound(tmp_path: Path) -> None:
    parent_path = _make_oracle_a_artifact(tmp_path)
    a1 = json.loads((parent_path.parent / "raw/A1_record.json").read_text())
    for label in ("r6", "r3"):
        descriptor = a1["vectors"][label]["canonical"]
        manifest_path = parent_path.parent / descriptor["manifest_relative_path"]
        assert _sha256(manifest_path) == descriptor["manifest_sha256"]
        manifest = json.loads(manifest_path.read_text())
        assert manifest["role"] == "full_fe_dual"
        assert manifest["key_inventory_sha256"] == descriptor[
            "key_inventory_sha256"
        ]
        shard = manifest["per_rank_shards"][0]
        assert _sha256(manifest_path.parent / shard["filename"]) == shard[
            "file_sha256"
        ]


def test_a2_a3_fixture_canonical_and_raw_vector_closures(
    tmp_path: Path,
) -> None:
    from benchmarks.canonical_vector_artifacts import read_canonical_packet_shard

    parent_path = _make_oracle_a_artifact(tmp_path)
    root = parent_path.parent
    a1 = json.loads((root / "raw/A1_record.json").read_text())
    a2 = json.loads((root / "raw/A2_record.json").read_text())
    a3 = json.loads((root / "raw/A3_record.json").read_text())

    def packets(descriptor: dict[str, object]) -> tuple[object, ...]:
        manifest_path = root / str(descriptor["manifest_relative_path"])
        assert _sha256(manifest_path) == descriptor["manifest_sha256"]
        manifest = json.loads(manifest_path.read_text())
        assert manifest["role"] == descriptor["role"]
        assert manifest["summed_local_duplicate_count"] == 0
        assert manifest["extractor_audit"]["numeric_allgather"] is False
        shard = manifest["per_rank_shards"][0]
        assert shard["rank"] == 0
        assert shard["packet_finite"] is True
        assert shard["local_duplicate_count"] == 0
        assert _sha256(manifest_path.parent / shard["filename"]) == shard[
            "file_sha256"
        ]
        return read_canonical_packet_shard(
            manifest_path.parent / shard["filename"], shard["file_sha256"]
        )

    a2_e3 = a2["vectors"]["e3"]["canonical"]
    a3_e3 = a3["vectors"]["e3_loaded"]["canonical"]
    assert a2_e3["role"] == a3_e3["role"] == "full_fe"
    assert a2_e3["key_inventory_sha256"] == a3_e3["key_inventory_sha256"]
    assert dict(packets(a2_e3)) == dict(packets(a3_e3))

    assert a3["vectors"]["e6_full"]["owned_slave_count"] == 1
    assert a3["vectors"]["e6_full"]["owned_slave_max"] > 0.0
    assert a3["vectors"]["e6_algebraic"]["owned_slave_count"] == 0
    assert a3["vectors"]["e6_algebraic"]["owned_slave_max"] == 0.0
    assert (
        a3["vectors"]["action"]["input_array_sha256"]
        == a3["vectors"]["e6_algebraic"]["array_sha256"]
    )

    dual_descriptors = (
        a1["vectors"]["r6"]["canonical"],
        a3["vectors"]["action"]["canonical"],
        a3["vectors"]["r6_new"]["canonical"],
    )
    assert len({item["key_inventory_sha256"] for item in dual_descriptors}) == 1
    p3_dual_descriptors = (
        a1["vectors"]["r3"]["canonical"],
        a3["vectors"]["r3_new"]["canonical"],
    )
    assert len({item["key_inventory_sha256"] for item in p3_dual_descriptors}) == 1

    r6 = np.load(root / a3["vectors"]["r6"]["relative_path"])
    action = np.load(root / a3["vectors"]["action"]["relative_path"])
    r6_new = np.load(
        root / a3["vectors"]["r6_new"]["relative_path"]
    )
    r3 = np.load(root / a3["vectors"]["r3"]["relative_path"])
    r3_new = np.load(
        root / a3["vectors"]["r3_new"]["relative_path"]
    )
    np.testing.assert_allclose(r6_new, r6 - action)
    assert r3.shape == r3_new.shape


def test_real_p3_h50_assembled_action_matches_matrix_free() -> None:
    import copy
    from mpi4py import MPI

    from benchmarks.run_task038_full3d_r3 import _current_input
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
        _build_same_mesh_levels,
    )
    from src.solvers.fullspace_v17_p3_oracle import (
        build_p3_physical_diagnostic_matrix,
    )
    from src.solvers.hcurl_canonical_vector import compare_canonical_packets
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_full_fe_dual_packets,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
    )

    comm = MPI.COMM_WORLD
    assert comm.size == 1
    input_path = runner.REPO_ROOT / "input/templates/full3d_iterative_example.dat"
    _spec, cfg10, _resolved, _input_facts = _current_input(
        runner.REPO_ROOT, input_path
    )
    cfg = copy.deepcopy(cfg10)
    cfg.mesh_target_size = 50.0
    cfg.nedelec_degree = 3
    cfg.visualization_degree = 3
    cfg.nedelec_trace_degree = None
    cfg.nedelec_interior_degree = None
    cfg.case_name = f"{cfg10.case_name}_v17_test_p3_h50"
    mode_inventory = build_dynamic_mode_inventory(cfg)

    levels = None
    bundle = None
    matrix = None
    source = matrix_free = matrix_action = repeat = None
    try:
        levels = _build_same_mesh_levels(
            cfg, comm, (3,), include_positive_coefficients=False
        )
        bundle = build_same_mesh_physical_action(
            levels, cfg, 3, mode_inventory=mode_inventory
        )
        matrix, matrix_audit = build_p3_physical_diagnostic_matrix(
            levels, cfg, comm, mode_inventory=mode_inventory
        )
        space = levels["spaces"][3]
        floquet = levels["floquets"][3]
        source = runner._space_vector(levels, 3)
        indices = np.arange(source.array.size, dtype=np.float64)
        source.array[:] = (0.125 + 0.01 * indices) + 1j * (
            -0.25 + 0.02 * indices
        )
        local_size = int(space.dofmap.index_map.size_local) * int(
            space.dofmap.index_map_bs
        )
        slaves = np.asarray(floquet.mpc.slaves, dtype=np.int64)
        owned_slaves = slaves[(slaves >= 0) & (slaves < local_size)]
        source.array[owned_slaves] = 0.0
        input_before = runner._owned_vector_facts(
            source, floquet.mpc, comm
        )

        matrix_free = runner._space_vector(levels, 3)
        matrix_action = matrix.createVecLeft()
        bundle["physical_action"].apply(source, matrix_free)
        matrix.mult(source, matrix_action)
        repeat = runner._space_vector(levels, 3)
        bundle["physical_action"].apply(source, repeat)
        input_after = runner._owned_vector_facts(source, floquet.mpc, comm)

        with np.errstate(over="raise", invalid="raise"):
            raw_difference = matrix_free.copy()
            raw_difference.axpy(-1.0, matrix_action)
        try:
            raw_relative = float(raw_difference.norm()) / max(
                float(matrix_action.norm()), np.finfo(float).tiny
            )
        finally:
            raw_difference.destroy()
        repeat_difference = repeat.copy()
        repeat_difference.axpy(-1.0, matrix_free)
        try:
            repeat_relative = float(repeat_difference.norm()) / max(
                float(matrix_free.norm()), np.finfo(float).tiny
            )
        finally:
            repeat_difference.destroy()
        matrix_free_packets, matrix_free_audit = (
            extract_canonical_full_fe_dual_packets(
                space, floquet.mpc, matrix_free
            )
        )
        matrix_packets, matrix_audit_facts = extract_canonical_full_fe_dual_packets(
            space, floquet.mpc, matrix_action
        )
        comparison = compare_canonical_packets(
            matrix_free_packets,
            matrix_packets,
            relative_tolerance=1.0e-11,
        )

        assert comparison["pass"], comparison
        assert raw_relative <= 1.0e-11
        assert repeat_relative <= 1.0e-12
        assert matrix_free_audit["role"] == matrix_audit_facts["role"] == (
            "full_fe_dual"
        )
        assert np.all(np.isfinite(matrix_free.array))
        assert np.all(np.isfinite(matrix_action.array))
        assert input_before["array_sha256"] == input_after["array_sha256"]
        assert input_before["finite"] is True
        assert input_after["finite"] is True
        assert input_after["owned_slave_max"] == 0.0
        assert input_after["owned_slave_count"] == 0
        assert bundle["mode_sha256"] == matrix_audit["mode_manifest_sha256"]
        assert bundle["dtn_quadrature_degree"] == matrix_audit[
            "dtn_quadrature_degree"
        ]
    finally:
        for vector in (repeat, matrix_action, matrix_free, source):
            if vector is not None:
                vector.destroy()
        if matrix is not None:
            matrix.destroy()
        if bundle is not None:
            destroy_same_mesh_physical_action(bundle)
        if levels is not None:
            levels.clear()


def test_oracle_a2_imports_process_snapshot_before_use() -> None:
    source = inspect.getsource(runner._run_a2)
    assert (
        "from benchmarks.task038_full3d_jit_staging import process_tree_snapshot"
        in source
    )
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "benchmarks.task038_full3d_jit_staging"
        for alias in node.names
    }
    called = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "process_tree_snapshot"
        for node in ast.walk(tree)
    )
    assert "process_tree_snapshot" in imported
    assert called


def test_parent_oracle_a_blocks_without_jit_children_and_keeps_b_schedule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    current: dict[str, object] = {"root": None, "phase": None}
    calls: list[str] = []
    jit_commands: list[list[str]] = []

    def prepare(root: Path) -> tuple[Path, Path]:
        root = Path(root)
        root.mkdir()
        cache = root / "jit_cache"
        cache.mkdir()
        current["root"] = root
        return root, cache

    def fake_child(
        _command: list[str],
        _process_path: Path,
        stage: str,
        stdout: Path,
        stderr: Path,
        **_kwargs: object,
    ) -> dict[str, object]:
        root = current["root"]
        assert isinstance(root, Path)
        calls.append(stage)
        if stage.startswith("precompile:"):
            jit_commands.append(_command)
        stdout.touch()
        stderr.touch()
        if current["phase"] == "oracle-a":
            raw = root / "raw"
            markers = root / "markers"
            raw.mkdir(exist_ok=True)
            markers.mkdir(exist_ok=True)
            if stage == "A1":
                _write_json(raw / "A1_record.json", {"stage": "A1"})
                names = ("paths_ready", "abi_ready", "A1_complete")
            elif stage == "A2":
                _write_json(
                    raw / "A2_record.json",
                    {"stage": "A2", "direct_solve": {"resource_preflight": "blocked"}},
                )
                names = ("A2_complete", "record_written", "release_complete")
            else:
                raise AssertionError(stage)
            for name in names:
                runner.authority_runner.write_marker(
                    markers,
                    name,
                    {"synthetic": True},
                    order=runner._marker_order("oracle-a"),
                    schema=runner.MARKER_SCHEMA,
                )
        return {
            "stage": stage,
            "returncode": 0,
            "stop_reason": None,
            "signals": [],
            "sample_count": 1,
            "peak_rss_bytes": 100,
            "max_swap_bytes": 0,
            "all_status_readable": True,
            "process_group_gone": True,
            "lifecycle_failure": False,
            "warning_crossed": False,
            "rss_watchdog_bytes": runner.ORACLE_A_HARD_BYTES,
        }

    monkeypatch.setattr(runner.authority_runner, "_prepare_parent_root", prepare)
    monkeypatch.setattr(runner.authority_runner, "_run_parent_child", fake_child)
    monkeypatch.setattr(
        runner.authority_runner,
        "_cache_snapshot",
        lambda _cache: {"artifact_count": 0, "manifest_sha256": "empty"},
    )
    monkeypatch.setattr(
        runner.authority_runner,
        "_child_command",
        lambda *_args: ["fake-precompile"],
    )
    monkeypatch.setattr(runner, "_worker_command", lambda *_args: ["fake-worker"])
    monkeypatch.setattr(
        runner,
        "_stage_source",
        lambda *_args: {"commit_sha": runner.SOURCE_SHA},
    )

    root_a = tmp_path / "oracle-a-run"
    current["phase"] = "oracle-a"
    assert (
        runner.run_parent(
            root_a,
            root_a / "parent_record.json",
            runner.SOURCE_SHA,
            tmp_path / "input.dat",
            "oracle-a",
            1,
        )
        == 0
    )
    parent_a = json.loads((root_a / "parent_record.json").read_text())
    assert calls == ["A1", "A2"]
    assert not (root_a / "children").exists()
    assert parent_a["classification"] == "A_ORACLE_BLOCKED_BY_RESOURCE_PREFLIGHT"
    assert parent_a["a2_resource_blocked"] is True
    assert [item["stage"] for item in parent_a["stages"]] == ["A1", "A2"]
    assert parent_a["markers"]["names"] == [
        "paths_ready",
        "abi_ready",
        "A1_complete",
        "A2_complete",
        "record_written",
        "release_complete",
    ]
    runner.authority_runner.marker_files(
        root_a / "markers", order=runner._marker_order("oracle-a")
    )

    calls.clear()
    root_b = tmp_path / "oracle-b-run"
    current["phase"] = "oracle-b"
    assert (
        runner.run_parent(
            root_b,
            root_b / "parent_record.json",
            runner.SOURCE_SHA,
            tmp_path / "input.dat",
            "oracle-b",
            1,
        )
        == 0
    )
    parent_b = json.loads((root_b / "parent_record.json").read_text())
    assert calls == [f"precompile:{group}" for group in runner.JIT_GROUPS] + ["B"]
    lexical_python = str(runner.REPO_ROOT / ".venv" / "bin" / "python")
    assert [command[0] for command in jit_commands] == [
        lexical_python
    ] * len(runner.JIT_GROUPS)
    assert (root_b / "children").is_dir()
    assert len(parent_b["children"]) == len(runner.JIT_GROUPS)


def test_a2_gate_record_is_kept_before_cleanup_and_parent_skips_a3(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    active_root: Path | None = None

    def prepare(root: Path) -> tuple[Path, Path]:
        nonlocal active_root
        root = Path(root)
        root.mkdir()
        (root / "raw").mkdir()
        (root / "markers").mkdir()
        (root / "jit_cache").mkdir()
        active_root = root
        return root, root / "jit_cache"

    def fake_child(
        _command: list[str],
        _process_path: Path,
        stage: str,
        stdout: Path,
        stderr: Path,
        **_kwargs: object,
    ) -> dict[str, object]:
        assert active_root is not None
        calls.append(stage)
        stdout.touch()
        stderr.touch()
        if stage == "A1":
            _write_json(active_root / "raw/A1_record.json", {"stage": "A1"})
        elif stage == "A2":
            _write_json(
                active_root / "raw/A2_record.json",
                {
                    "stage": "A2",
                    "direct_solve": {"resource_preflight": "passed"},
                },
            )
        else:
            raise AssertionError(stage)
        result = _process_result(stage)
        if stage == "A2":
            result.update(returncode=1, stop_reason="a2_numeric_gate")
        return result

    monkeypatch.setattr(runner.authority_runner, "_prepare_parent_root", prepare)
    monkeypatch.setattr(runner.authority_runner, "_run_parent_child", fake_child)
    monkeypatch.setattr(
        runner.authority_runner,
        "_cache_snapshot",
        lambda _cache: {"artifact_count": 0, "manifest_sha256": "empty"},
    )
    monkeypatch.setattr(runner, "_worker_command", lambda *_args: ["fake"])
    monkeypatch.setattr(
        runner,
        "_stage_source",
        lambda *_args: {"commit_sha": runner.SOURCE_SHA},
    )

    root = tmp_path / "oracle-a-gate"
    assert (
        runner.run_parent(
            root,
            root / "parent_record.json",
            runner.SOURCE_SHA,
            tmp_path / "input.dat",
            "oracle-a",
            1,
        )
        == 1
    )
    assert calls == ["A1", "A2"]
    assert (root / "raw/A2_record.json").is_file()
    assert not (root / "raw/A3_record.json").exists()
    parent = json.loads((root / "parent_record.json").read_text())
    assert parent["stages"][-1]["stage"] == "A2"
    assert parent["error"]

    source = inspect.getsource(runner._run_a2)
    write_index = source.index('_write_stage_record(raw_dir, "A2", record)')
    cleanup_index = source.index("del levels", write_index)
    raise_index = source.index("raise RuntimeError(gate_error)")
    assert write_index < cleanup_index < raise_index


@pytest.mark.parametrize("stop_stage", ("A1", "A2"))
def test_parent_preserves_explicit_numeric_stop_and_skips_later_a_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stop_stage: str
) -> None:
    active_root: Path | None = None
    calls: list[str] = []

    def prepare(root: Path) -> tuple[Path, Path]:
        nonlocal active_root
        root = Path(root)
        root.mkdir()
        (root / "raw").mkdir()
        (root / "markers").mkdir()
        cache = root / "jit_cache"
        cache.mkdir()
        active_root = root
        return root, cache

    def fake_child(
        _command: list[str],
        _process_path: Path,
        stage: str,
        stdout: Path,
        stderr: Path,
        **_kwargs: object,
    ) -> dict[str, object]:
        assert active_root is not None
        calls.append(stage)
        stdout.touch()
        stderr.touch()
        stopped = stage == stop_stage
        _write_json(
            active_root / "raw" / f"{stage}_record.json",
            {
                "stage": stage,
                "stage_outcome": "numerical_gate_failed" if stopped else "complete",
                "gate_failures": ["checkpoint_reproduction"] if stopped else [],
            },
        )
        result = _process_result(stage)
        if stopped:
            result["returncode"] = 1
        return result

    monkeypatch.setattr(runner.authority_runner, "_prepare_parent_root", prepare)
    monkeypatch.setattr(runner.authority_runner, "_run_parent_child", fake_child)
    monkeypatch.setattr(
        runner.authority_runner,
        "_cache_snapshot",
        lambda _cache: {"artifact_count": 0, "manifest_sha256": "empty"},
    )
    monkeypatch.setattr(runner, "_worker_command", lambda *_args: ["fake"])
    monkeypatch.setattr(
        runner,
        "_stage_source",
        lambda *_args: {"commit_sha": runner.SOURCE_SHA},
    )

    root = tmp_path / f"oracle-a-{stop_stage}"
    assert (
        runner.run_parent(
            root,
            root / "parent_record.json",
            runner.SOURCE_SHA,
            tmp_path / "input.dat",
            "oracle-a",
            1,
        )
        == 1
    )
    parent = json.loads((root / "parent_record.json").read_text())
    assert calls == (["A1"] if stop_stage == "A1" else ["A1", "A2"])
    assert parent["numeric_stop_stage"] == stop_stage
    assert parent["classification"] == "ORACLE_A_NUMERICAL_GATE_STOP"
    assert parent["error"] == f"{stop_stage} numerical gate stop"
    assert [item["stage"] for item in parent["stages"]] == calls


@pytest.mark.parametrize(
    "mutation",
    (
        "checkpoint_reproduction",
        "checkpoint_contract",
        "checkpoint_provenance",
        "rho_ref",
    ),
)
def test_checker_recomputes_oracle_a_and_rejects_stored_gate_mutation(
    tmp_path: Path, mutation: str
) -> None:
    parent_path = _make_oracle_a_artifact(tmp_path)
    result = checker.check_artifact(parent_path)
    assert result["status"] == "PASS", result
    assert result["classification"] == "EXACT_P3_COARSE_SPAN_PASS"
    expected_classification = "ORACLE_A_NUMERICAL_GATE_FAIL"

    if mutation == "checkpoint_reproduction":
        record_path = parent_path.parent / "raw/A1_record.json"
        record = json.loads(record_path.read_text())
        record["checkpoint_reproduction"]["actual"] += 0.1
        stage_index = 0
        expected_error = "checkpoint reproduction does not close"
    elif mutation == "checkpoint_contract":
        record_path = parent_path.parent / "raw/A1_record.json"
        record = json.loads(record_path.read_text())
        record["checkpoint_reproduction"]["expected"] += 0.1
        record["checkpoint_reproduction"]["relative_limit"] = 1.0e-7
        stage_index = 0
        expected_error = "checkpoint expected is not frozen"
    elif mutation == "checkpoint_provenance":
        record_path = parent_path.parent / "raw/A1_record.json"
        record = json.loads(record_path.read_text())
        record["checkpoint"].pop("input_identity_sha256")
        stage_index = 0
        expected_error = "checkpoint input_identity_sha256 mismatch"
        expected_classification = "INFRASTRUCTURE_FAILURE_RETRYABLE"
    else:
        record_path = parent_path.parent / "raw/A3_record.json"
        record = json.loads(record_path.read_text())
        record["rho_ref"] = 1.0
        stage_index = 2
        expected_error = "stored rho_ref does not close"
    _write_json(record_path, record)
    parent = json.loads(parent_path.read_text())
    parent["stages"][stage_index]["sha256"] = _sha256(record_path)
    _write_json(parent_path, parent)
    result = checker.check_artifact(parent_path)
    assert result["status"] == "FAIL"
    assert result["classification"] == expected_classification, result
    assert any(expected_error in error for error in result["errors"])


def test_checker_accepts_a2_resource_block_without_a3(tmp_path: Path) -> None:
    parent_path = _make_oracle_a_artifact(tmp_path)
    root = parent_path.parent
    a2_path = root / "raw/A2_record.json"
    a2 = json.loads(a2_path.read_text())
    a2["direct_solve"].update(
        {
            "resource_preflight": "blocked",
            "analysis_only": True,
            "numeric_factor_called": False,
            "solve_called": False,
            "symbolic_calls": 1,
            "raw_info": {"infog": {"16": 12000}},
            "resource_preflight_facts": {
                "formula": "post_analysis_process_tree_rss_bytes + max(INFOG(16), 0) * 1000000",
                "post_analysis_process_tree_rss_bytes": 1,
                "infog16": 12000,
                "predicted_peak_bytes": 12_000_000_001,
                "hard_limit_bytes": checker.A_HARD_BYTES,
            },
        }
    )
    a2["predicted_peak_bytes"] = 12_000_000_001
    _write_json(a2_path, a2)
    (root / "raw/A3_record.json").unlink()
    (root / "markers/004_A3_complete.json").unlink()
    parent = json.loads(parent_path.read_text())
    parent["a2_resource_blocked"] = True
    parent["classification"] = "A_ORACLE_BLOCKED_BY_RESOURCE_PREFLIGHT"
    parent["stages"][1]["sha256"] = _sha256(a2_path)
    parent["stages"] = parent["stages"][:2]
    parent["cache"]["stage_snapshots"] = parent["cache"]["stage_snapshots"][:2]
    marker_names = list(checker.A_BLOCKED_MARKER_ORDER)
    marker_rows = []
    for name in marker_names:
        marker_path = root / "markers" / f"{checker.A_MARKER_ORDER.index(name):03d}_{name}.json"
        marker_rows.append({"name": name, "sha256": _sha256(marker_path)})
    marker_manifest = root / "marker_manifest.json"
    _write_json(marker_manifest, marker_rows)
    parent["markers"] = {
        "relative_path": "marker_manifest.json",
        "sha256": _sha256(marker_manifest),
        "names": marker_names,
    }
    _write_json(parent_path, parent)

    result = checker.check_artifact(parent_path)
    assert result["status"] == "PASS", result
    assert result["evidence_valid"] is True
    assert result["classification"] == "A_ORACLE_BLOCKED_BY_RESOURCE_PREFLIGHT"


@pytest.mark.parametrize("stop_stage", ("A1", "A2"))
def test_checker_accepts_explicit_oracle_a_numeric_stop_without_a3(
    tmp_path: Path, stop_stage: str
) -> None:
    parent_path = _make_oracle_a_artifact(tmp_path)
    root = parent_path.parent
    parent = json.loads(parent_path.read_text())
    if stop_stage == "A1":
        record_path = root / "raw/A1_record.json"
        record = json.loads(record_path.read_text())
        reproduction = record["checkpoint_reproduction"]
        reproduction["actual"] += 0.1
        reproduction["absolute_difference"] = abs(
            reproduction["actual"] - reproduction["expected"]
        )
        reproduction["relative_difference"] = (
            reproduction["absolute_difference"]
            / abs(reproduction["expected"])
        )
        record["stage_outcome"] = "numerical_gate_failed"
        record["gate_failures"] = ["checkpoint_reproduction"]
        stage_count = 1
    else:
        record_path = root / "raw/A2_record.json"
        record = json.loads(record_path.read_text())
        rhs = np.asarray([1.0 + 0.5j, 2.0 - 0.25j], dtype=np.complex128)
        action = 0.5 * rhs
        residual = rhs - action
        vectors = {
            "rhs": rhs,
            "action": action,
            "residual": residual,
        }
        for name, values in vectors.items():
            record["vectors"][name] = _owned_descriptor(
                _vector_descriptor(root / "raw", f"A2/stop_{name}.npy", values)
            )
        record["rhs"] = {
            "before": record["vectors"]["rhs"],
            "after": record["vectors"]["rhs"],
            "unchanged": True,
        }
        record["explicit_true_residual"] = 0.5
        record["stage_outcome"] = "numerical_gate_failed"
        record["gate_failures"] = ["p3_explicit_residual"]
        stage_count = 2
    _write_json(record_path, record)
    parent["stages"][stage_count - 1]["returncode"] = 1
    parent["stages"][stage_count - 1]["sha256"] = _sha256(record_path)
    parent["stages"] = parent["stages"][:stage_count]
    parent["cache"]["stage_snapshots"] = parent["cache"]["stage_snapshots"][:stage_count]
    parent["a2_resource_blocked"] = False
    parent["numeric_stop_stage"] = stop_stage
    parent["classification"] = "ORACLE_A_NUMERICAL_GATE_STOP"
    parent["error"] = f"{stop_stage} numerical gate stop"
    marker_names = list(checker.A_NUMERIC_STOP_MARKER_ORDER[stop_stage])
    for marker_path in (root / "markers").glob("*.json"):
        if marker_path.stem.split("_", 1)[1] not in marker_names:
            marker_path.unlink()
    marker_rows = []
    for name in marker_names:
        marker_path = root / "markers" / f"{checker.A_MARKER_ORDER.index(name):03d}_{name}.json"
        marker_rows.append({"name": name, "sha256": _sha256(marker_path)})
    marker_manifest = root / "marker_manifest.json"
    _write_json(marker_manifest, marker_rows)
    parent["markers"] = {
        "relative_path": "marker_manifest.json",
        "sha256": _sha256(marker_manifest),
        "names": marker_names,
    }
    _write_json(parent_path, parent)

    result = checker.check_artifact(parent_path)
    assert result["status"] == "PASS", result
    assert result["evidence_valid"] is True
    assert result["classification"] == "ORACLE_A_NUMERICAL_GATE_FAIL"
    assert result["metrics"]["numeric_stop_stage"] == stop_stage
    assert result["metrics"]["gate_failures"]


@pytest.mark.parametrize(
    "tamper",
    ("canonical_shard", "a2_residual", "owned_slave", "e3_loaded_path", "action_input"),
)
def test_checker_rejects_tampered_oracle_a_raw_evidence(
    tmp_path: Path, tamper: str
) -> None:
    parent_path = _make_oracle_a_artifact(tmp_path)
    root = parent_path.parent
    parent = json.loads(parent_path.read_text())
    if tamper == "canonical_shard":
        a1 = json.loads((root / "raw/A1_record.json").read_text())
        descriptor = a1["vectors"]["r6"]["canonical"]
        manifest = json.loads((root / descriptor["manifest_relative_path"]).read_text())
        shard_path = root / descriptor["manifest_relative_path"].replace(
            Path(descriptor["manifest_relative_path"]).name,
            manifest["per_rank_shards"][0]["filename"],
        )
        item = json.loads(shard_path.read_text().splitlines()[0])
        item["value"][0] += 1.0
        shard_path.write_text(json.dumps(item, separators=(",", ":")) + "\n")
        expected_error = "shard SHA mismatch"
    elif tamper == "owned_slave":
        a3_path = root / "raw/A3_record.json"
        a3 = json.loads(a3_path.read_text())
        a3["vectors"]["e6_algebraic"]["owned_slave_max"] = 1.0
        _write_json(a3_path, a3)
        parent["stages"][2]["sha256"] = _sha256(a3_path)
        expected_error = "owned slave maximum is not zero"
    elif tamper == "e3_loaded_path":
        a3_path = root / "raw/A3_record.json"
        a3 = json.loads(a3_path.read_text())
        a3["vectors"]["e3_loaded"]["relative_path"] = "raw/A3/missing.npy"
        _write_json(a3_path, a3)
        parent["stages"][2]["sha256"] = _sha256(a3_path)
        expected_error = "A3.e3_loaded file missing"
    elif tamper == "action_input":
        a3_path = root / "raw/A3_record.json"
        a3 = json.loads(a3_path.read_text())
        a3["vectors"]["action"]["input_array_sha256"] = "0" * 64
        _write_json(a3_path, a3)
        parent["stages"][2]["sha256"] = _sha256(a3_path)
        expected_error = "action input is not e6_algebraic"
    else:
        a2_path = root / "raw/A2_record.json"
        a2 = json.loads(a2_path.read_text())
        values = np.asarray([1.0 + 0.0j, 0.0j], dtype=np.complex128)
        descriptor = _owned_descriptor(
            _vector_descriptor(root / "raw", "A2/residual.npy", values)
        )
        a2["vectors"]["residual"] = descriptor
        _write_json(a2_path, a2)
        parent["stages"][1]["sha256"] = _sha256(a2_path)
        expected_error = "residual rhs-action does not close"
    _write_json(parent_path, parent)
    result = checker.check_artifact(parent_path)
    assert result["status"] == "FAIL", result
    assert result["evidence_valid"] is False
    assert any(expected_error in error for error in result["errors"])


def test_checker_recomputes_each_b_residual_from_raw_rhs_and_ax(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "raw"
    rhs = np.asarray([2.0 + 0.0j, 0.0j], dtype=np.complex128)
    ax = np.asarray([1.0 + 0.0j, 0.0j], dtype=np.complex128)
    rhs_descriptor = _vector_descriptor(raw_dir, "rhs.npy", rhs)
    ax_descriptor = _vector_descriptor(raw_dir, "ax.npy", ax)
    history = [
        {
            "iteration": iteration,
            "true_residual_norm": 1.0,
            "true_relative_residual": 0.5,
            "finite": True,
        }
        for iteration in range(20, 501, 20)
    ]
    packets = [
        {"iteration": row["iteration"], "rhs": rhs_descriptor, "ax": ax_descriptor}
        for row in history
    ]
    errors: list[str] = []
    checker._check_residual_packets(
        {"residual_packets": packets}, raw_dir, history, errors, "synthetic"
    )
    assert errors == []


@pytest.mark.parametrize("kind", ("closure", "orthogonality"))
def test_checker_b_numeric_gates_are_valid_negative_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
) -> None:
    monkeypatch.setattr(checker, "B_STEPS", 20)
    errors: list[str] = []
    gate_failures: list[str] = []
    if kind == "closure":
        history = [
            {
                "iteration": iteration,
                "true_residual_norm": 1.0,
                "true_relative_residual": 1.0,
                "explicit_vs_arnoldi_relative": 2.0e-8,
                "finite": True,
            }
            for iteration in range(20, 21, 20)
        ]
        checker._check_history(
            history,
            errors,
            "unrestarted",
            gate_failures,
            require_arnoldi_closure=True,
        )
        expected = "numerical:unrestarted.explicit_vs_arnoldi"
    else:
        context, facts, _basis_root = _make_basis_checker_context(tmp_path)
        facts["audit"]["orthogonality_max_abs"] = 2.0e-8
        checker._check_basis(context, facts, errors, gate_failures)
        expected = "numerical:unrestarted.orthogonality"
    assert errors == []
    assert expected in gate_failures
    metrics = {"gate_failures": gate_failures}
    assert (
        checker._classification("oracle-b", errors, metrics)
        == "ORACLE_B_NUMERICAL_GATE_FAIL"
    )


def _marker_fixture(
    root: Path, names: list[str]
) -> dict[str, object]:
    marker_dir = root / "markers"
    marker_dir.mkdir(parents=True)
    for name in names:
        _write_json(
            marker_dir / f"{checker.B_MARKER_ORDER.index(name):03d}_{name}.json",
            {"name": name},
        )
    manifest_path = root / "marker_manifest.json"
    _write_json(manifest_path, [{"name": name} for name in names])
    return {
        "markers": {
            "relative_path": "marker_manifest.json",
            "sha256": _sha256(manifest_path),
            "names": names,
        }
    }


def test_checker_b_marker_order_rejects_missing_or_early_release(
    tmp_path: Path,
) -> None:
    valid = list(checker.B_MARKER_ORDER)
    cases = (
        ("valid", valid, False),
        ("missing_release", valid[:-1], True),
        (
            "early_release",
            ["paths_ready", "abi_ready", "reference_complete", "release_complete", "unrestarted_complete", "record_written"],
            True,
        ),
    )
    for name, names, should_fail in cases:
        root = tmp_path / name
        parent = _marker_fixture(root, names)
        errors: list[str] = []
        checker._check_markers(root, parent, "oracle-b", errors)
        assert bool(errors) is should_fail, (name, errors)


@pytest.mark.parametrize(
    ("ratio", "expected"),
    (
        (0.1, "UNRESTARTED_KRYLOV_STRONG_SIGNAL"),
        (0.5, "UNRESTARTED_KRYLOV_WEAK_SIGNAL"),
        (0.6, "UNRESTARTED_KRYLOV_NO_SIGNAL"),
    ),
)
def test_checker_oracle_b_thresholds_use_raw_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ratio: float,
    expected: str,
) -> None:
    history = [
        {
            "iteration": iteration,
            "true_residual_norm": ratio,
            "true_relative_residual": ratio,
            "explicit_vs_arnoldi_relative": 0.0,
            "finite": True,
        }
        for iteration in range(20, 501, 20)
    ]
    architecture = {
        "global_physical_aij": False,
        "global_schur": False,
        "dense_dtn": False,
        "factor": False,
        "numeric_allgather": False,
        "phase_once": True,
    }
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    same_rhs_values = np.asarray([1.0 + 0.0j], dtype=np.complex128)
    same_initial_values = np.asarray([0.0 + 0.0j], dtype=np.complex128)
    same_rhs_descriptor = _vector_descriptor(
        raw_dir, "same_start/rhs.npy", same_rhs_values
    )
    same_initial_descriptor = _vector_descriptor(
        raw_dir, "same_start/initial_solution.npy", same_initial_values
    )
    same_rhs_sha = same_rhs_descriptor["array_sha256"]
    same_initial_sha = same_initial_descriptor["array_sha256"]
    cycles = [
        {
            "cycle_index": (1000 + index * 20) // 20,
            "start_iteration": 1000 + index * 20,
            "end_iteration": 1020 + index * 20,
            "iterations": 20,
            "matvec_count": 21,
            "pc_apply_count": 20,
            "ksp_destroyed": True,
        }
        for index in range(25)
    ]
    worker = {
        "source": _source(),
        "input": {
            "template_sha256": checker.INPUT_SHA256,
            "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
            "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
        },
        "disk_preflight": {
            "required_free_bytes": checker.B_DISK_FREE_BYTES,
            "free_bytes": checker.B_DISK_FREE_BYTES,
        },
        "checkpoint": {
            "iteration": 1000,
            "explicit_true_residual": checker.CHECKPOINT_EXPLICIT_RESIDUAL,
            "input_identity_sha256": checker.CHECKPOINT_INPUT_IDENTITY_SHA256,
            "operator_identity_sha256": checker.CHECKPOINT_OPERATOR_IDENTITY_SHA256,
            "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
            "source_sha": checker.CHECKPOINT_SOURCE_SHA,
            "mpi_size": 1,
            "manifest_sha256": checker.CHECKPOINT_MANIFEST_SHA256,
            "solution_sha256": checker.CHECKPOINT_SOLUTION_SHA256,
        },
        "architecture": architecture,
        "same_start": {
            "rhs": {
                "descriptor": same_rhs_descriptor,
                "sha256": same_rhs_sha,
                "finite": True,
            },
            "initial_solution": {
                "descriptor": same_initial_descriptor,
                "sha256": same_initial_sha,
                "finite": True,
            },
            "reference": {
                "rhs_before_sha256": same_rhs_sha,
                "rhs_after_sha256": same_rhs_sha,
                "initial_solution_before_sha256": same_initial_sha,
                "initial_solution_after_sha256": same_initial_sha,
                "input_unchanged": True,
                "initial_true_residual": 1.0,
                "finite": True,
            },
            "unrestarted": {
                "rhs_before_sha256": same_rhs_sha,
                "rhs_after_sha256": same_rhs_sha,
                "initial_solution_before_sha256": same_initial_sha,
                "initial_solution_after_sha256": same_initial_sha,
                "input_unchanged": True,
                "initial_true_residual": 1.0,
                "finite": True,
            },
        },
        "reference": {
            "algorithm": "right_gmres_restart20",
            "history": [{**row, "true_residual_norm": 1.0, "true_relative_residual": 1.0} for row in history],
            "final_true_residual": 1.0,
            "iterations": 500,
            "matvec_count": 525,
            "pc_apply_count": 500,
            "explicit_action_count": 26,
            "ksp_destroy_count": 25,
            "residual_packet_action_count": 25,
            "observer_action_count": 25,
            "cycles": cycles,
            "finite": True,
            "initial_true_residual": 1.0,
            "settings": {
                "ksp_type": "gmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 20,
                "cycle_max_it": 20,
                "max_it": 1500,
                "start_iteration": 1000,
                "residual_limit": 0.0,
                "residual_replacement": True,
                "initial_guess_nonzero": True,
                "first_checkpoint_iteration": None,
                "checkpoint_interval": 20,
            },
        },
        "unrestarted": {
            "algorithm": "right_fgmres_unrestarted_disk_backed",
            "history": history,
            "final_true_residual": ratio,
            "iterations": 500,
            "action_count": 526,
            "pc_count": 500,
            "explicit_action_count": 25,
            "residual_packet_action_count": 25,
            "finite": True,
            "initial_true_residual": 1.0,
            "settings": {
                "ksp_type": "fgmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": None,
                "max_steps": 500,
                "checkpoint_interval": 20,
                "initial_guess_nonzero": True,
                "residual_replacement": False,
            },
            "audit": {
                "algorithm": "right_flexible_gmres_unrestarted",
                "max_steps": 500,
                "checkpoint_interval": 20,
                "iterations": 500,
                "action_count": 526,
                "pc_count": 500,
                "explicit_action_count": 25,
                "checkpoint_iterations": list(range(20, 501, 20)),
                "input_unchanged": True,
                "final_solution_finite": True,
            },
        },
    }
    context = {"worker": worker, "raw_dir": raw_dir, "stage_results": []}
    monkeypatch.setattr(checker, "_check_basis", lambda *_args: None)
    monkeypatch.setattr(checker, "_check_residual_packets", lambda *_args: None)
    errors: list[str] = []
    metrics = checker._check_b(context, checker.SOURCE_SHA, errors)
    assert not errors
    assert metrics["classification"] == expected
    assert checker._classification("oracle-b", errors, metrics) == expected
    record_path = tmp_path / "parent.json"
    _write_json(record_path, {})
    monkeypatch.setattr(
        checker, "_check_common", lambda *_args: context
    )
    glued = checker.check_artifact(record_path, checker.SOURCE_SHA)
    assert glued["status"] == "PASS"
    assert glued["evidence_valid"] is True
    assert glued["classification"] == expected
    if ratio == 0.1:
        for label in ("rhs", "initial_solution"):
            original = worker["same_start"][label]["sha256"]
            worker["same_start"][label]["sha256"] = "0" * 64
            tamper_errors: list[str] = []
            checker._check_b(context, checker.SOURCE_SHA, tamper_errors)
            expected_label = "RHS" if label == "rhs" else "initial"
            assert any(
                f"same-start {expected_label} array SHA does not close" in error
                for error in tamper_errors
            ), tamper_errors
            worker["same_start"][label]["sha256"] = original


def test_m0_json_and_runner_checker_import_boundaries() -> None:
    m0 = Path("docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/v17_mechanism_preflight.json")
    data = checker._load_json(m0)
    assert data["formal_status"] == "not_run"
    banned = {"mpi4py", "petsc4py", "dolfinx", "basix", "slepc4py"}
    for path in (Path(runner.__file__), Path(checker.__file__)):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        top_level = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                top_level.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level.append(node.module.split(".")[0])
        assert not banned.intersection(top_level), (path, top_level)
    assert runner.parse_args(
        [
            "--phase",
            "oracle-b",
            "--mode",
            "worker",
            "--stage",
            "B",
            "--artifact-root",
            "/tmp/root",
            "--record",
            "/tmp/root/raw/B_record.json",
            "--source-sha",
            runner.SOURCE_SHA,
            "--input",
            "/tmp/input.dat",
            "--mpi-size",
            "1",
        ]
    ).phase == "oracle-b"
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert "run_disk_backed_right_fgmres" in source
    assert "cycle_observer" in source
    assert "--phase" in source


def test_strict_json_rejects_duplicate_keys_and_nonfinite_constants() -> None:
    with pytest.raises(ValueError):
        checker._load_json_from_text('{"a":1,"a":2}')
    with pytest.raises(ValueError):
        checker._load_json_from_text('{"a":NaN}')
