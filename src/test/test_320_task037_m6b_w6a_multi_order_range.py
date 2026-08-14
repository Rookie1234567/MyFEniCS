from __future__ import annotations

import json
from pathlib import Path
import shutil

import numpy as np
import pytest

import benchmarks.run_task037_extra_m6b as runner
import src.solvers.hcurl_m6b_w6a_multi_order_range as w6a


def _synthetic_inputs() -> tuple[tuple[w6a.W6ASparseColumn, ...], dict, np.ndarray]:
    rows = w6a.W6A_TOTAL_COLUMNS
    columns = tuple(
        w6a.W6ASparseColumn(
            np.asarray([index], dtype=np.int32),
            np.asarray([1.0 + 0.01j * (index + 1)], dtype=np.complex128),
        )
        for index in range(rows)
    )
    legacy = {
        "basis_manifest_sha256": w6a.W6A_LEGACY_BASIS_MANIFEST_SHA256,
        "manifest_file_sha256": "d" * 64,
        "z_data": np.asarray(
            [1.0 + 0.01j * (index + 1) for index in range(75)],
            dtype=np.complex128,
        ),
        "z_indices": np.arange(75, dtype=np.int32),
        "z_indptr": np.arange(76, dtype=np.int32),
    }
    identity = {
        "legacy_basis_manifest_sha256": w6a.W6A_LEGACY_BASIS_MANIFEST_SHA256,
        "legacy_column_count": 75,
        "source_sha": "a" * 40,
        "operator_identity": "A=synthetic-diagonal",
    }
    rhs = np.asarray(
        [1.0 + 0.002j * (index + 1) for index in range(rows)],
        dtype=np.complex128,
    )
    return columns, {"legacy": legacy, "identity": identity}, rhs


def _build(tmp_path: Path, name: str, monkeypatch, progress_events=None):
    columns, metadata, rhs = _synthetic_inputs()
    diagonal = np.asarray(
        [1.0 + 0.003j * (index + 1) for index in range(w6a.W6A_TOTAL_COLUMNS)],
        dtype=np.complex128,
    )
    first_hashes = [
        w6a._array_sha256(
            np.asarray(
                diagonal
                * np.eye(1, w6a.W6A_TOTAL_COLUMNS, index, dtype=np.complex128).ravel()
                * (1.0 + 0.01j * (index + 1)),
                dtype=np.complex128,
            )
        )
        for index in range(75)
    ]
    legacy_az_sha = w6a._json_sha256(first_hashes)
    monkeypatch.setattr(w6a, "W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE", legacy_az_sha)
    metadata["legacy"]["az_column_sha256_aggregate"] = legacy_az_sha
    diagnostic = w6a.W6AMultiOrderRangeDiagnostic.from_columns(
        columns,
        lambda values: diagonal * values,
        global_rows=w6a.W6A_TOTAL_COLUMNS,
        ownership_range=(0, w6a.W6A_TOTAL_COLUMNS),
        scratch_dir=tmp_path / f"{name}_az",
        identity=metadata["identity"],
        legacy_basis=metadata["legacy"],
        progress=(
            None
            if progress_events is None
            else lambda event, _first, _second: progress_events.append(event)
        ),
    )
    return diagnostic, rhs, metadata


def test_w6a_fixed_spec_phase_and_serial_range_projection(tmp_path: Path, monkeypatch):
    specs = w6a.fixed_w6a_column_specs()
    assert len(specs) == 390
    assert [(item.order_m, item.z_plane, item.component) for item in specs[75:]][:6] == [
        (-7, 0, 0), (-7, 0, 1), (-7, 0, 2), (-7, 1, 0), (-7, 1, 1), (-7, 1, 2)
    ]
    assert specs[-1].order_m == -1 and specs[-1].z_plane == 14 and specs[-1].component == 2
    phase = w6a.w6a_phase(
        np.asarray([0.2]), np.asarray([-0.4]), kx=0.7, ky=-0.3j, period_x=2.0, order_m=-7
    )
    expected = np.exp(1j * ((0.7 - 7.0 * np.pi) * 0.2 - 0.3j * -0.4))
    assert np.allclose(phase, np.asarray([expected]), rtol=0.0, atol=1.0e-15)
    with pytest.raises(ValueError):
        w6a.w6a_phase(0.0, 0.0, kx=0.0, ky=0.0, period_x=0.0, order_m=0)

    progress_events = []
    diagnostic, rhs, metadata = _build(
        tmp_path, "first", monkeypatch, progress_events=progress_events
    )
    assert progress_events[-6:-2] == ["repeat_ready"] * 4
    assert progress_events[-2:] == ["az_ready", "gram_ready"]
    first_gram = np.array(diagnostic.gram, copy=True)
    try:
        result = diagnostic.compare_range_orders(rhs)
        matrix = np.diag(
            np.asarray(
                [1.0 + 0.003j * (index + 1) for index in range(390)],
                dtype=np.complex128,
            )
        )
        rho75 = np.linalg.norm(rhs - matrix[:, :75] @ np.linalg.lstsq(matrix[:, :75], rhs, rcond=None)[0]) / np.linalg.norm(rhs)
        rho390 = np.linalg.norm(rhs - matrix @ np.linalg.lstsq(matrix, rhs, rcond=None)[0]) / np.linalg.norm(rhs)
        assert abs(result["rho75"] - rho75) <= 1.0e-11
        assert abs(result["rho390"] - rho390) <= 1.0e-11
        assert result["rho390"] <= result["rho75"] + 1.0e-12
        assert diagnostic.audit["columns"] == 390
        assert diagnostic.audit["phase_full_vector_buffers"] == {"construction": 2, "projection": 5}
        assert diagnostic.audit["max_full_vector_buffers"] == 5
        assert diagnostic.audit["az_builder_only"] is True
        assert diagnostic.audit["az_production_retained"] is False
        assert diagnostic.action_counts == {"base": 390, "selected_repeat": 4, "total": 394}
        assert set(diagnostic.repeat_column_sha256) == {"0", "74", "75", "389"}
        assert diagnostic.repeat_exact is True
    finally:
        diagnostic.close()

    repeat, rhs_repeat, _ = _build(tmp_path, "repeat", monkeypatch)
    try:
        assert np.array_equal(repeat.gram, first_gram)
        assert repeat.compare_range_orders(rhs_repeat) == result
    finally:
        repeat.close()

    bad_columns = list(_synthetic_inputs()[0])
    bad_columns[0] = w6a.W6ASparseColumn(
        np.asarray([1], dtype=np.int32), np.asarray([1.0 + 0.01j], dtype=np.complex128)
    )
    with pytest.raises(ValueError, match="first 75"):
        w6a.W6AMultiOrderRangeDiagnostic.from_columns(
            bad_columns,
            lambda values: values,
            global_rows=390,
            ownership_range=(0, 390),
            scratch_dir=tmp_path / "bad_authority_az",
            identity=metadata["identity"],
            legacy_basis=metadata["legacy"],
        )


def test_w6a_rank_deficient_range_fails_closed(tmp_path: Path, monkeypatch):
    columns, metadata, _rhs = _synthetic_inputs()
    zero = np.zeros(w6a.W6A_TOTAL_COLUMNS, dtype=np.complex128)
    zero_hash = w6a._array_sha256(zero)
    zero_aggregate = w6a._json_sha256([zero_hash] * w6a.W6A_LEGACY_COLUMNS)
    monkeypatch.setattr(w6a, "W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE", zero_aggregate)
    metadata["legacy"]["az_column_sha256_aggregate"] = zero_aggregate
    with pytest.raises(np.linalg.LinAlgError):
        w6a.W6AMultiOrderRangeDiagnostic.from_columns(
            columns,
            lambda _values: zero.copy(),
            global_rows=w6a.W6A_TOTAL_COLUMNS,
            ownership_range=(0, w6a.W6A_TOTAL_COLUMNS),
            scratch_dir=tmp_path / "rank_deficient_az",
            identity=metadata["identity"],
            legacy_basis=metadata["legacy"],
        )


def test_w6a_self_consistent_first75_az_tamper_rejected(tmp_path: Path, monkeypatch):
    diagnostic, _rhs, metadata = _build(tmp_path, "authority_tamper", monkeypatch)
    store = diagnostic.save(tmp_path / "authority_tamper_store")
    monkeypatch.setattr(w6a, "load_w1a_legacy_basis", lambda _path: metadata["legacy"])
    manifest = json.loads(store.read_text())
    scratch = Path(manifest["az_scratch"]["path"])
    with scratch.open("r+b") as stream:
        stream.seek(0)
        stream.write(np.asarray([2.0 + 0.5j], dtype=np.complex128).tobytes())
    raw = w6a.RawPositionalColumnStore.open_readonly(scratch, 390, 390)
    try:
        left = np.empty(390, dtype=np.complex128)
        right = np.empty(390, dtype=np.complex128)
        gram = np.zeros((390, 390), dtype=np.complex128)
        column_hashes = []
        for column in range(390):
            raw.read_column(column, left)
            column_hashes.append(w6a._array_sha256(left))
            for previous in range(column + 1):
                raw.read_column(previous, right)
                value = np.vdot(left, right)
                if column == previous:
                    value = complex(value.real, 0.0)
                gram[column, previous] = value
                gram[previous, column] = np.conjugate(value)
    finally:
        raw.close()
    factor = np.asarray(np.linalg.cholesky(gram).conjugate().T, dtype=np.complex128)
    np.save(store.parent / "gram.npy", gram, allow_pickle=False)
    np.save(store.parent / "r_factor.npy", factor, allow_pickle=False)
    manifest["arrays"]["gram"] = w6a._array_meta(store.parent / "gram.npy", gram)
    manifest["arrays"]["r_factor"] = w6a._array_meta(store.parent / "r_factor.npy", factor)
    manifest["column_sha256"] = column_hashes
    manifest["az_column_sha256_aggregate"] = w6a._json_sha256(column_hashes)
    manifest["legacy_z_identity"]["az_column_sha256_aggregate"] = w6a._json_sha256(
        column_hashes[:75]
    )
    for column in w6a.W6A_REPEAT_COLUMNS:
        manifest["repeat_column_sha256"][str(column)] = column_hashes[column]
    singular = np.linalg.svd(factor, compute_uv=False)
    threshold = 128.0 * np.finfo(float).eps * max(1.0, singular[0])
    manifest["factor_audit"].update(
        {
            "rank": int(np.count_nonzero(singular > threshold)),
            "rank_threshold": float(threshold),
            "gram_hermitian_defect": 0.0,
            "normal_closure": float(
                np.linalg.norm(factor.conjugate().T @ factor - gram)
                / np.linalg.norm(gram)
            ),
            "r_singular_max": float(singular[0]),
            "r_singular_min": float(singular[-1]),
            "condition_estimate": float(singular[0] / singular[-1]),
        }
    )
    manifest["az_scratch"]["sha256"] = w6a._file_sha256(scratch)
    manifest["evidence_sha256"] = w6a._json_sha256(
        {key: value for key, value in manifest.items() if key != "evidence_sha256"}
    )
    store.write_bytes(w6a._json_bytes(manifest) + b"\n")
    try:
        assert w6a.validate_w6a_store(store, legacy_store_dir=tmp_path / "legacy")["pass"] is False
    finally:
        diagnostic.close()


def test_w6a_store_hashes_readonly_and_tamper_fail_closed(tmp_path: Path, monkeypatch):
    diagnostic, _rhs, metadata = _build(tmp_path, "store", monkeypatch)
    store = diagnostic.save(tmp_path / "store")
    monkeypatch.setattr(w6a, "load_w1a_legacy_basis", lambda _path: metadata["legacy"])
    try:
        valid = w6a.validate_w6a_store(store, legacy_store_dir=tmp_path / "legacy")
        assert valid["pass"] is True
        loaded = w6a.W6AMultiOrderRangeDiagnostic.load(
            store, legacy_store_dir=tmp_path / "legacy"
        )
        loaded.close()
        manifest = json.loads(store.read_text())
        assert Path(manifest["az_scratch"]["path"]).is_absolute()
        short_path = store.parent / "z_indptr.npy"
        short_bytes = short_path.read_bytes()
        np.save(short_path, np.zeros(3, dtype=np.int32), allow_pickle=False)
        try:
            assert w6a.validate_w6a_store(store, legacy_store_dir=tmp_path / "legacy")["pass"] is False
            with pytest.raises(ValueError, match="validation failed"):
                w6a.W6AMultiOrderRangeDiagnostic.load(
                    store, legacy_store_dir=tmp_path / "legacy"
                )
        finally:
            short_path.write_bytes(short_bytes)
        scratch = Path(manifest["az_scratch"]["path"])
        original = scratch.read_bytes()
        scratch.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        try:
            assert w6a.validate_w6a_store(store, legacy_store_dir=tmp_path / "legacy")["pass"] is False
            with pytest.raises(ValueError, match="validation failed"):
                w6a.W6AMultiOrderRangeDiagnostic.load(
                    store, legacy_store_dir=tmp_path / "legacy"
                )
        finally:
            scratch.write_bytes(original)
        tampered = dict(metadata["legacy"])
        tampered["z_data"] = np.array(metadata["legacy"]["z_data"], copy=True)
        tampered["z_data"][0] += 1.0
        monkeypatch.setattr(w6a, "load_w1a_legacy_basis", lambda _path: tampered)
        assert w6a.validate_w6a_store(store, legacy_store_dir=tmp_path / "legacy")["pass"] is False
    finally:
        diagnostic.close()
    assert not hasattr(__import__("src.solvers.disk_backed_flexible_gmres", fromlist=["x"]), "_RawBasisFile")

    monkeypatch.undo()
    authority = Path(
        "benchmarks/artifacts/task037_extra_development/"
        "m6b_w1a_e2f99a3_builder_run1/sparse_range_store"
    )
    copied = tmp_path / "legacy_copy"
    shutil.copytree(authority, copied)
    data_path = copied / "z_data.npy"
    data = bytearray(data_path.read_bytes())
    data[-1] ^= 1
    data_path.write_bytes(data)
    with pytest.raises(ValueError):
        w6a.load_w1a_legacy_basis(copied)


def test_w6a_runner_progress_prediction_numeric_and_parser(tmp_path: Path):
    prediction = runner._m6b_w6a_predicted_live_set(
        old_retained_bytes=100,
        new_retained_bytes=200,
        old_work_bytes=300,
        new_work_bytes=500,
    )
    assert prediction["predicted_live_set_bytes"] == runner.M6B_W5_EXPECTED_PROCESS_PEAK_BYTES + 300
    assert prediction["gate"] is True
    assert prediction["derived_not_measured"] is True
    scope = runner._m6b_w6a_scope(prediction=prediction)
    assert scope["columns"] == 390
    assert scope["factor_count"] == runner.M6B_FACTOR_COUNT
    assert scope["factor_reuse_count"] == runner.M6B_FACTOR_REUSE
    progress = tmp_path / "w6a_progress.jsonl"
    for event in runner.M6B_W6A_EVENTS:
        runner._m6b_w6a_progress_emit(progress, event, elapsed_wall_seconds=0.1)
    for completed in range(1, 391):
        runner._m6b_w6a_progress_emit(
            progress,
            "column_progress",
            elapsed_wall_seconds=0.2,
            completed_columns=completed,
            total_columns=390,
        )
    for completed, column in enumerate(runner.M6B_W6A_REPEAT_COLUMNS, 1):
        runner._m6b_w6a_progress_emit(
            progress,
            "repeat_ready",
            elapsed_wall_seconds=0.25,
            column_index=column,
            completed_repeats=completed,
            total_repeats=4,
        )
    for event in runner.M6B_W6A_TRAILING_EVENTS:
        runner._m6b_w6a_progress_emit(progress, event, elapsed_wall_seconds=0.3)
    assert runner._m6b_w6a_progress_valid(progress)["pass"] is True
    lines = progress.read_text().splitlines()
    progress.write_text("\n".join(lines[:-1]) + "\n")
    assert runner._m6b_w6a_progress_valid(progress)["pass"] is False
    assert runner._m6b_w6a_numeric_gate(
        {str(item): {"rho75": 0.8, "rho390": 0.5} for item in (20, 100, 150, 200)}
    )["pass"] is True
    assert runner._m6b_w6a_numeric_gate(
        {str(item): {"rho75": 0.8, "rho390": 0.75} for item in (20, 100, 150, 200)}
    )["pass"] is False
    args = runner._parser().parse_args(
        [
            "m6b-w6a-check",
            "--raw-dir", str(tmp_path / "raw"),
            "--legacy-store-dir", str(tmp_path / "legacy"),
            "--output", str(tmp_path / "out.json"),
            "--expected-source-sha", "a" * 40,
        ]
    )
    assert args.command == "m6b-w6a-check"


def test_w6a_checker_synthetic_preformal_pass(tmp_path: Path, monkeypatch):
    diagnostic, rhs, metadata = _build(tmp_path, "checker", monkeypatch)
    raw = tmp_path / "raw"
    raw.mkdir()
    store = diagnostic.save(raw / "sparse_range_store")
    monkeypatch.setattr(w6a, "load_w1a_legacy_basis", lambda _path: metadata["legacy"])
    monkeypatch.setattr(runner, "M6B_GLOBAL_ROWS", w6a.W6A_TOTAL_COLUMNS)
    progress = raw / "w6a_progress.jsonl"
    for event in runner.M6B_W6A_EVENTS:
        runner._m6b_w6a_progress_emit(progress, event, elapsed_wall_seconds=0.1)
    for completed in range(1, 391):
        runner._m6b_w6a_progress_emit(
            progress,
            "column_progress",
            elapsed_wall_seconds=0.2,
            completed_columns=completed,
            total_columns=390,
        )
    for completed, column in enumerate(runner.M6B_W6A_REPEAT_COLUMNS, 1):
        runner._m6b_w6a_progress_emit(
            progress,
            "repeat_ready",
            elapsed_wall_seconds=0.25,
            column_index=column,
            completed_repeats=completed,
            total_repeats=4,
        )
    for event in runner.M6B_W6A_TRAILING_EVENTS:
        runner._m6b_w6a_progress_emit(progress, event, elapsed_wall_seconds=0.3)
    residual_artifacts = {}
    for iteration in (20, 100, 150, 200):
        name = f"m6b_w6a_residual_iter{iteration}.npy"
        np.save(raw / name, rhs, allow_pickle=False)
        residual_artifacts[str(iteration)] = {
            **runner._artifact(raw, name),
            "array_sha256": runner._m6b_w2_array_sha256(rhs),
        }
    prediction = runner._m6b_w6a_predicted_live_set(
        old_retained_bytes=100,
        new_retained_bytes=200,
        old_work_bytes=300,
        new_work_bytes=500,
    )
    source = {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
        "worktree_status_porcelain": [],
    }
    summary = {
        "schema": runner.M6B_W6A_SCHEMA,
        "status": "diagnostic_complete",
        "scope": runner._m6b_w6a_scope(prediction=prediction),
        "prediction": prediction,
        "source_at_start": source,
        "source_at_end": source,
        "formal_pass": False,
        "pde_pass": False,
        "progress_artifact": runner._artifact(raw, "w6a_progress.jsonl"),
        "store_manifest_artifact": runner._artifact(
            raw, "sparse_range_store/manifest.json"
        ),
        "residual_artifacts": residual_artifacts,
    }
    runner._write_json(raw / "w6a_summary.json", runner._attach_evidence(summary))
    output = tmp_path / "w6a_check.json"
    try:
        assert (
            runner._m6b_w6a_check_command(
                raw, tmp_path / "legacy", output, "a" * 40
            )
            == 0
        )
        checked = json.loads(output.read_text())
        assert checked["classification"] == "PRE_FORMAL_PASS"
        assert checked["formal_pass"] is False
    finally:
        diagnostic.close()
