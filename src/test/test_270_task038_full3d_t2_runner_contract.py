"""Pure T2 runner/checker contracts; no mesh, MPI job, or PDE is launched."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path
import textwrap
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks import run_task038_full3d_t2 as runner
from benchmarks import task038_full3d_t2_checker as checker
from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)


def _key(index: int):
    return (
        "full_fe",
        1,
        ((int(index), 0, 0),),
        0,
        "synthetic",
        None,
        (1.0, 0.0),
    )


def _write_artifact(
    raw_dir: Path,
    name: str,
    values: np.ndarray,
    *,
    mpi_size: int,
    canonical_values: np.ndarray | None = None,
    write_canonical: bool = True,
) -> dict:
    path = raw_dir / f"vectors/{name}.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    values = np.asarray(values, dtype=np.complex128)
    values.tofile(path)
    canonical_values = (
        values if canonical_values is None else np.asarray(canonical_values, dtype=np.complex128)
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    descriptor = {
        "relative_path": f"vectors/{name}.bin",
        "bytes": int(path.stat().st_size),
        "file_sha256": digest,
        "array_sha256": digest,
        "dtype": "complex128",
        "shape": [int(values.size)],
        "finite": True,
        "canonical_order": "global_petsc_row_order",
        "ownership_ranges": [[0, int(values.size)]],
    }
    if not write_canonical:
        return descriptor
    packets = tuple((_key(index), value) for index, value in enumerate(canonical_values))
    shard_metadata = []
    for rank in range(mpi_size):
        shard_path = raw_dir / f"canonical/{name}.rank{rank:04d}.jsonl"
        shard_path.parent.mkdir(parents=True, exist_ok=True)
        shard_metadata.append(
            write_canonical_packet_shard(
                shard_path,
                packets[rank::mpi_size],
                audit_packets=True,
            )
        )
    manifest = canonical_shard_manifest(
        role=name,
        mpi_size=mpi_size,
        shard_metadata=shard_metadata,
        extractor_audit={"role": name, "synthetic": True},
    )
    manifest_path = raw_dir / f"canonical/{name}.manifest.json"
    manifest_sha = write_canonical_manifest(manifest_path, manifest)
    descriptor.update(
        {
        "canonical_order": "physical_hcurl_packet_key",
        "canonical_manifest_relative_path": f"canonical/{name}.manifest.json",
        "canonical_manifest_bytes": int(manifest_path.stat().st_size),
        "canonical_manifest_sha256": manifest_sha,
        "canonical_packet_count": int(len(packets)),
        }
    )
    return descriptor


def _record(
    root: Path,
    *,
    case: str = "p6-h5",
    mpi_size: int = 2,
    raw_transform=None,
    canonical_delta: dict[str, np.ndarray] | None = None,
) -> Path:
    raw_dir = root / f"raw-{case}-{mpi_size}"
    raw_dir.mkdir()
    base = np.asarray([1.0 + 0.2j, 2.0 - 0.5j, -0.25 + 1.5j, 0.75 - 0.1j])
    if case == "p6-h10":
        base = base[:2]
    transform = np.arange(base.size - 1, -1, -1) if raw_transform else np.arange(base.size)
    values = base[transform]
    canonical_delta = {} if canonical_delta is None else canonical_delta
    artifacts = {}
    for name in ("source", "source_after", "action"):
        artifact_values = values
        if name == "source_after":
            artifact_values = values.copy()
        artifacts[name] = _write_artifact(
            raw_dir,
            name,
            artifact_values,
            mpi_size=mpi_size,
            canonical_values=canonical_delta.get(
                name, base if raw_transform else artifact_values
            ),
            write_canonical=case == "p6-h10",
        )
    reference_kind = "scaling_only" if case == "p6-h5" else "assembled"
    if case == "p6-h10":
        reference_kind = "independent"
    if reference_kind != "scaling_only":
        artifacts["reference_action"] = _write_artifact(
            raw_dir,
            "reference_action",
            values,
            mpi_size=mpi_size,
            write_canonical=False,
        )
    retained = 4 if case == "p6-h5" else 2
    components = {"owned": retained, "metadata": retained}
    record = {
        "schema": checker.T2_SCHEMA,
        "case": case,
        "profile": checker.T2_PROFILE,
        "raw_dir": str(raw_dir),
        "source": {
            "expected_sha": "a" * 40,
            "commit_sha_start": "a" * 40,
            "commit_sha_end": "a" * 40,
            "tracked_status_start": "",
            "tracked_status_end": "",
        },
        "mpi": {
            "size": mpi_size,
            "expected_size": mpi_size,
        },
        "model": {
            "config_sha256": "b" * 64,
            "wavelength_nm": checker.T2_WAVELENGTH_NM,
            "global_rows": 4 if case == "p6-h5" else 2,
            "floquet_phases": {"x_nontrivial": True, "y_nontrivial": True},
            "edge_constraints": 2,
            "face_constraints": 2,
        },
        "artifacts": artifacts,
        "reference": {
            "kind": reference_kind,
            "relative_error": 0.0,
            "matrix_destroyed_before_repeats": True,
            "setup_seconds": 0.01,
            "setup_self_rss_bytes": 100,
            "setup_rss_semantics": "mpi_rank_max_current_self_rss",
        },
        "repeats": {
            "count": checker.T2_REPEATS,
            "elapsed_seconds": [0.01] * checker.T2_REPEATS,
            "rss_bytes": [100] * checker.T2_REPEATS,
            "swap_used_bytes": [0] * checker.T2_REPEATS,
            "output_sha256": [artifacts["action"]["file_sha256"]] * checker.T2_REPEATS,
            "relative_differences": [0.0] * checker.T2_REPEATS,
        },
        "candidate_audit": {
                "matrix_type": "python",
                "apply_count": checker.T2_REPEATS,
                "mpc_enabled": True,
                "phase_application": "finalized_floquet_mpc_once",
                "orientation": "dolfinx_n1curl_form_kernel",
                "owner_local": True,
                "constraint_nnz_closes": True,
                "fresh_packed_arrays_released": True,
                "numeric_allgather": False,
                "replicated_global_numeric_vector": False,
                "ordinary_default_changed": False,
                "factor_count": 0,
                "retained_dense_cell_tensor_count": 0,
                "cell_schur_matrix_nnz": 0,
                "slab_matrix_nnz": 0,
                "global_matrix_materialized": False,
                "global_constraint_matrix_materialized": False,
                "global_condensed_schur_materialized": False,
                "cell_schur_matrix_materialized": False,
                "slab_matrix_materialized": False,
                "dense_cell_tensor_materialized_per_apply": False,
                "ksp_created": False,
                "dtn_used": False,
                "retained_numeric_payload_components": components,
                "retained_numeric_payload_local_bytes": sum(components.values()),
                "retained_numeric_payload_global_max_bytes": retained,
        },
        "resource": {
            "rss_semantics": "mpi_rank_max_current_self_rss",
            "process_tree_evidence": "not_measured_t2",
        },
    }
    path = root / f"{case}-{mpi_size}.json"
    path.write_bytes(runner._canonical_json(record) + b"\n")
    return path


def _five_records(root: Path, *, action_canonical_delta=None) -> tuple[Path, ...]:
    return (
        _record(root, case="p2-h50", mpi_size=1),
        _record(root, case="p3-h50", mpi_size=1),
        _record(root, case="p6-h10", mpi_size=1),
        _record(
            root,
            case="p6-h10",
            mpi_size=2,
            raw_transform=True,
            canonical_delta=action_canonical_delta,
        ),
        _record(root, case="p6-h5", mpi_size=1),
    )


def _aggregate(root: Path, *, action_canonical_delta=None) -> dict:
    p2, p3, h10_mpi1, h10_mpi2, h5 = _five_records(
        root, action_canonical_delta=action_canonical_delta
    )
    return checker.check_t2_aggregate(
        p2_record_path=p2,
        p3_record_path=p3,
        p6_h10_mpi1_record_path=h10_mpi1,
        p6_h10_mpi2_record_path=h10_mpi2,
        p6_h5_record_path=h5,
    )


def test_mpi_telemetry_is_rank_max_and_rss_fails_closed(monkeypatch) -> None:
    tree = ast.parse(textwrap.dedent(inspect.getsource(runner._run_case)))
    rank_max_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and any(
            keyword.arg == "op"
            and isinstance(keyword.value, ast.Attribute)
            and keyword.value.attr == "MAX"
            and isinstance(keyword.value.value, ast.Name)
            and keyword.value.value.id == "MPI"
            for keyword in node.keywords
        )
    ]
    assert len(rank_max_calls) >= 3

    def missing_status(self, *args, **kwargs):
        raise OSError("missing VmRSS")

    monkeypatch.setattr(runner.Path, "open", missing_status)
    with pytest.raises(RuntimeError, match="VmRSS"):
        runner._rss_bytes()
    assert "ru_maxrss" not in inspect.getsource(runner._rss_bytes)


def test_offset_aware_global_relative_difference(tmp_path: Path) -> None:
    path = tmp_path / "values.bin"
    np.asarray([1, 2, 3, 4], dtype=np.complex128).tofile(path)

    class Comm:
        def allreduce(self, value, op=None):
            return value

        def tompi4py(self):
            return self

    vector = SimpleNamespace(
        getArray=lambda readonly=True: np.asarray([3, 4], dtype=np.complex128),
        getComm=lambda: Comm(),
    )
    assert runner._relative_difference_to_file(vector, path, 2, 4) == 0.0


def test_aggregate_uses_exact_five_records_and_mandatory_scaling(
    tmp_path: Path,
) -> None:
    assert checker.T2_MPI_CANONICAL_LIMIT == 1.0e-12
    result = _aggregate(tmp_path)
    assert result["passed"] is True
    assert result["checks"]["mpi_canonical_identity"] is True
    assert result["checks"]["mandatory_h10_to_h5_scaling"] is True
    assert result["scaling"]["retained_exponent_h10_to_h5"] == pytest.approx(1.0)


def test_raw_offset_does_not_replace_canonical_peer_identity(tmp_path: Path) -> None:
    result = _aggregate(
        tmp_path,
        action_canonical_delta={"action": np.asarray([9, 8], dtype=np.complex128)},
    )
    assert result["passed"] is False
    assert any("canonical packet mismatch: action" in item for item in result["problems"])


def test_aggregate_rejects_wrong_case_or_mpi_identity(tmp_path: Path) -> None:
    p2, p3, h10_mpi1, h10_mpi2, h5 = _five_records(tmp_path)
    payload = json.loads(h5.read_text())
    payload["mpi"]["size"] = 2
    h5.write_bytes(runner._canonical_json(payload) + b"\n")
    result = checker.check_t2_aggregate(
        p2_record_path=p2,
        p3_record_path=p3,
        p6_h10_mpi1_record_path=h10_mpi1,
        p6_h10_mpi2_record_path=h10_mpi2,
        p6_h5_record_path=h5,
    )
    assert result["passed"] is False
    assert result["checks"]["exact_five_record_set"] is False


def test_repeat_hash_is_measured_not_fabricated(tmp_path: Path) -> None:
    path = _record(tmp_path)
    payload = json.loads(path.read_text())
    payload["repeats"]["output_sha256"][3] = "f" * 64
    path.write_bytes(runner._canonical_json(payload) + b"\n")
    result = checker.check_t2_record(path)
    assert result["classification"] == "T2_NUMERIC_FAIL"


def test_source_mutation_and_oracle_lifetime_fail_closed(tmp_path: Path) -> None:
    path = _record(tmp_path)
    payload = json.loads(path.read_text())
    source_after = Path(payload["raw_dir"]) / payload["artifacts"]["source_after"]["relative_path"]
    np.asarray([4, 3, 2, 1], dtype=np.complex128).tofile(source_after)
    digest = hashlib.sha256(source_after.read_bytes()).hexdigest()
    payload["artifacts"]["source_after"]["file_sha256"] = digest
    payload["artifacts"]["source_after"]["array_sha256"] = digest
    path.write_bytes(runner._canonical_json(payload) + b"\n")
    result = checker.check_t2_record(path)
    assert result["passed"] is False

    oracle_path = _record(tmp_path, case="p2-h50", mpi_size=1)
    oracle_payload = json.loads(oracle_path.read_text())
    oracle_payload["reference"]["matrix_destroyed_before_repeats"] = False
    oracle_path.write_bytes(runner._canonical_json(oracle_payload) + b"\n")
    oracle_result = checker.check_t2_record(oracle_path)
    assert oracle_result["passed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["repeats"]["relative_differences"].__setitem__(
            0, None
        ),
        lambda payload: payload["repeats"]["swap_used_bytes"].__setitem__(0, None),
        lambda payload: payload["candidate_audit"].update(
            retained_numeric_payload_global_max_bytes=None
        ),
        lambda payload: payload["resource"].update(
            process_tree_evidence="measured_process_tree"
        ),
    ],
)
def test_malformed_numeric_fields_are_evidence_failures(tmp_path: Path, mutation) -> None:
    path = _record(tmp_path)
    payload = json.loads(path.read_text())
    mutation(payload)
    path.write_bytes(runner._canonical_json(payload) + b"\n")
    result = checker.check_t2_record(path)
    assert result["passed"] is False
    assert result["classification"] == "T2_EXECUTION_OR_EVIDENCE_FAIL"


def test_missing_required_aggregate_peers_fail_without_crash(tmp_path: Path) -> None:
    p2 = _record(tmp_path, case="p2-h50", mpi_size=1)
    p3 = _record(tmp_path, case="p3-h50", mpi_size=1)
    h5 = _record(tmp_path, case="p6-h5", mpi_size=1)
    missing = tmp_path / "missing.json"
    result = checker.check_t2_aggregate(
        p2_record_path=p2,
        p3_record_path=p3,
        p6_h10_mpi1_record_path=missing,
        p6_h10_mpi2_record_path=missing,
        p6_h5_record_path=h5,
    )
    assert result["passed"] is False
    assert result["classification"] == "T2_EXECUTION_OR_EVIDENCE_FAIL"


def test_parser_exposes_separate_aggregate_check() -> None:
    args = runner._parser().parse_args(
        [
            "aggregate",
            "--p2-mpi1-record",
            "p2.json",
            "--p3-mpi1-record",
            "p3.json",
            "--p6-h10-mpi1-record",
            "h10-mpi1.json",
            "--p6-h10-mpi2-record",
            "h10-mpi2.json",
            "--p6-h5-mpi1-record",
            "h5.json",
        ]
    )
    assert args.command == "aggregate"
