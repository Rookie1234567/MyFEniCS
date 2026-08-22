"""Pure contracts for the N2 setup runner and independent checker."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task038_full3d_n2 as runner
from benchmarks import task038_full3d_n2_checker as checker


ROOT = Path(__file__).parents[2]
RUNNER_PATH = ROOT / "benchmarks" / "run_task038_full3d_n2.py"
CHECKER_PATH = ROOT / "benchmarks" / "task038_full3d_n2_checker.py"


def _array_descriptor(path: Path, array: np.ndarray) -> dict[str, object]:
    np.save(path, np.asarray(array, dtype=np.complex128), allow_pickle=False)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "shape": list(array.shape),
        "dtype": "complex128",
    }


def test_n2_cli_freezes_only_setup_cases() -> None:
    args = runner._parse_worker(
        [
            "--stage",
            "n2",
            "--case",
            "p6-h10-mpi2",
            "--input",
            "input.dat",
            "--raw-dir",
            "raw",
            "--record",
            "record.json",
            "--marker-dir",
            "markers",
            "--expected-source-sha",
            "a" * 40,
            "--expected-mpi-size",
            "2",
        ]
    )
    assert args.expected_mpi_size == 2
    with pytest.raises(SystemExit):
        runner._parse_worker(
            [
                "--stage",
                "n2",
                "--case",
                "p6-h10-mpi1",
                "--input",
                "input.dat",
                "--raw-dir",
                "raw",
                "--record",
                "record.json",
                "--marker-dir",
                "markers",
                "--expected-source-sha",
                "a" * 40,
                "--expected-mpi-size",
                "2",
            ]
        )


def test_n2_marker_order_and_runner_does_not_use_closed_trace_or_candidate() -> None:
    assert runner.N2_MARKERS[:-1] == (
        "preflight",
        "mesh_space_mpc",
        "JIT",
        "subdomain_inventory",
        "local_factor_build",
        "local_mode_build",
        "regional_coarse_build",
        "top_level_build",
        "identity_apply",
        "post_setup_release",
        "canonical_evidence",
        "cleanup",
    )
    source = RUNNER_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "DistributedTraceHarmonicBasis",
        "TraceHarmonicDefinition",
        "build_candidate_a",
        "build_candidate_c",
        "FixedSecondOrderLocalImpedance",
    ):
        assert forbidden not in source
    assert "allgather(" not in source


def test_checker_is_read_only_and_does_not_import_numeric_runtime() -> None:
    tree = ast.parse(CHECKER_PATH.read_text(encoding="utf-8"))
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not imported.intersection({"dolfinx", "petsc4py", "mpi4py", "slepc4py"})
    assert "run_task038_full3d_n2" not in CHECKER_PATH.read_text(encoding="utf-8")
    assert "allgather(" not in CHECKER_PATH.read_text(encoding="utf-8")


def test_watchdog_compact_recomputes_warning_and_swap_facts() -> None:
    sample = {
        "stage": "post_setup_release",
        "authority": {
            "memory_authority_bytes": 1_900_000_000,
            "process_tree": {
                "rss_bytes": 1_000,
                "pss_bytes": 800,
                "uss_bytes": 600,
                "swap_bytes": 0,
                "pss_uss_readable": True,
            },
            "dedicated_cgroup_swap_bytes": 0,
        },
    }
    compact = runner._watchdog_compact(
        "b" * 64,
        ("python", "worker", "--record", "/tmp/record.json"),
        "natural_exit",
        0,
        {"process_group_exited": True},
        (sample,),
    )
    assert compact["warning_crossed"] is True
    assert compact["post_setup_warning_crossed"] is True
    assert compact["process_tree_swap_gate"] is True
    assert compact["stage_peak_process_tree_pss_bytes"] == {
        "post_setup_release": 800
    }


@pytest.mark.parametrize(
    ("termination", "expected_natural"),
    [
        ({"method": "already_exited", "process_group_exited": True}, True),
        ({"method": "already_exited", "process_group_exited": False}, False),
    ],
)
def test_watchdog_natural_exit_requires_verified_group(
    termination: dict[str, object], expected_natural: bool
) -> None:
    sample = {
        "stage": "cleanup",
        "authority": {
            "memory_authority_bytes": 100,
            "process_tree": {
                "rss_bytes": 100,
                "pss_bytes": 80,
                "uss_bytes": 60,
                "swap_bytes": 0,
            },
        },
    }
    compact = runner._watchdog_compact(
        "d" * 64,
        ("python", "worker"),
        "natural_exit",
        0,
        termination,
        (sample,),
    )
    assert compact["natural_exit"] is True
    assert compact["no_orphan_claim"] is expected_natural


def test_watchdog_controlled_orphan_cleanup_is_not_natural_no_orphan() -> None:
    sample = {
        "stage": "cleanup",
        "authority": {
            "memory_authority_bytes": 100,
            "process_tree": {"rss_bytes": 100, "pss_bytes": 80, "uss_bytes": 60, "swap_bytes": 0},
        },
    }
    compact = runner._watchdog_compact(
        "e" * 64,
        ("python", "worker"),
        "orphan_cleanup_required",
        0,
        {"method": "POSIX process group SIGTERM then SIGKILL", "process_group_exited": True},
        (sample,),
    )
    assert compact["natural_exit"] is False
    assert compact["no_orphan_claim"] is False


def test_checker_fails_closed_on_missing_identity_and_resource(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    record.write_text(json.dumps({"schema": runner.N2_SCHEMA}) + "\n", encoding="utf-8")
    result = checker.check_worker_record(
        record,
        expected_sha="c" * 40,
        expected_mpi_size=1,
        raw_dir=tmp_path,
    )
    assert result["passed"] is False
    assert any("source identity" in item or "resource_contract" in item for item in result["errors"])


def test_checker_sums_owner_shards_without_numeric_gather(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checker, "N2_RANK", 2)
    monkeypatch.setattr(checker, "N2_REGIONAL_RANK", 1)
    monkeypatch.setattr(checker, "N2_EXPECTED_GLOBAL_ROWS", 4)
    z0 = np.asarray([[1.0 + 0j, 0j], [0j, 1.0 + 0j]])
    z1 = np.asarray([[0.0 + 0j, 0j], [0j, 0.0 + 0j]])
    az0 = z0.copy()
    az1 = z1.copy()
    z160 = z0[:, :1]
    z161 = z1[:, :1]
    shards = []
    for rank, values in enumerate(((z0, z160, az0), (z1, z161, az1))):
        z, z16, az = values
        descriptors = {
            "Z16": _array_descriptor(tmp_path / f"z16_{rank}.npy", z16),
            "Z32": _array_descriptor(tmp_path / f"z32_{rank}.npy", z),
            "AZ32": _array_descriptor(tmp_path / f"az32_{rank}.npy", az),
            "ownership_range": [rank * 2, (rank + 1) * 2],
            "local_owned_rows": 2,
        }
        shards.append({"rank": rank, **descriptors})
    e = z0.conj().T @ az0 + z1.conj().T @ az1
    e_descriptor = _array_descriptor(tmp_path / "e.npy", e)
    record = {
        "artifacts": {
            "arrays": {"owner_shards": shards, "global_owned_rows": 4},
            "E32": e_descriptor,
        },
    }
    errors: list[str] = []
    arrays = checker._check_matrix_artifacts(record, tmp_path, errors)
    metrics = checker._check_coarse_arrays(record, arrays, tmp_path, 4, errors)
    assert errors == []
    assert metrics["z_orthogonality_relative"] == 0.0
    assert metrics["e_recomputed_relative"] == 0.0


def test_pair_checker_compares_template_and_top_mixing_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mpi1_path = tmp_path / "mpi1.json"
    mpi2_path = tmp_path / "mpi2.json"

    def make_record(mpi_size: int, owner: int) -> dict[str, object]:
        return {
            "mpi": {"size": mpi_size},
            "basis": {
                "class_template_identity": {
                    "class_digests": ["class-digest"],
                    "class_template_mode_digests": [["class-digest", "mode-digest"]],
                    "class_owners": {"class-digest": owner},
                },
                "top_mixing_identity": {
                    "schema": "task038.n2.top-mixing.v1",
                    "seed": "fixed-seed",
                    "rank": 32,
                    "levels": 2,
                },
            },
            "artifacts": {
                "canonical_matrices": {
                    "Z32": {"manifest_path": str(tmp_path / f"z{mpi_size}.json")},
                    "AZ32": {"manifest_path": str(tmp_path / f"az{mpi_size}.json")},
                }
            },
        }

    records = {
        mpi1_path: make_record(1, 0),
        mpi2_path: make_record(2, 1),
    }
    monkeypatch.setattr(
        checker,
        "check_worker_record",
        lambda record_path, **kwargs: {"passed": True, "errors": []},
    )
    monkeypatch.setattr(checker, "_load", lambda path: records[Path(path)])
    monkeypatch.setattr(
        checker,
        "compare_canonical_matrices",
        lambda *args, **kwargs: {"passed": True},
    )

    baseline = checker.check_pair(mpi1_path, mpi2_path, expected_sha="f" * 40)
    assert baseline["passed"] is True

    records[mpi2_path]["basis"]["class_template_identity"]["class_template_mode_digests"] = [
        ["class-digest", "different-mode-digest"]
    ]
    mode_mismatch = checker.check_pair(mpi1_path, mpi2_path, expected_sha="f" * 40)
    assert mode_mismatch["passed"] is False
    assert any("template mode" in error for error in mode_mismatch["errors"])

    records[mpi2_path] = make_record(2, 1)
    records[mpi2_path]["basis"]["class_template_identity"]["class_digests"] = [
        "different-class-digest"
    ]
    class_mismatch = checker.check_pair(mpi1_path, mpi2_path, expected_sha="f" * 40)
    assert class_mismatch["passed"] is False
    assert any("class digest" in error for error in class_mismatch["errors"])

    records[mpi2_path] = make_record(2, 1)
    records[mpi2_path]["basis"]["top_mixing_identity"]["seed"] = "different-seed"
    mixing_mismatch = checker.check_pair(mpi1_path, mpi2_path, expected_sha="f" * 40)
    assert mixing_mismatch["passed"] is False
    assert any("top mixing" in error for error in mixing_mismatch["errors"])
