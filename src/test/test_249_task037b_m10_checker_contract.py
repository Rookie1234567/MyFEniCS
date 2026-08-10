"""Synthetic, read-only contracts for the frozen M10 checker."""

from __future__ import annotations

import ast
import hashlib
import json
from argparse import Namespace
from pathlib import Path

import numpy as np
import pytest

from benchmarks import task037b_hybrid_iterative_checker as checker
from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)

SOURCE_SHA = "a" * 40


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _descriptor(value: np.ndarray) -> dict[str, object]:
    value = np.ascontiguousarray(value)
    return {
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "bytes": int(value.nbytes),
        "sha256": checker._array_digest(value),
    }


def _write_grid(
    path: Path, *, h1: bool = False
) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    arrays = {
        name: np.zeros(shape, dtype=dtype)
        for name, (shape, dtype) in checker.ARRAY_SPEC.items()
    }
    arrays["x_nm"] = np.arange(40, dtype=np.float64)
    arrays["y_nm"] = np.arange(20, dtype=np.float64)
    arrays["z_nm"] = np.arange(5, dtype=np.float64)
    np.savez(path, **arrays)
    numeric = ("E_V_per_m", "H_A_per_m", "modal_amplitudes", "bottom_q", "top_q")
    metadata: dict[str, object] = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha(path),
        "keys": list(arrays),
        "arrays": {
            name: _descriptor(arrays[name]) for name in (numeric if h1 else arrays)
        },
    }
    metadata.update(
        {"schema": "task037b.h1-authority-grid-EH-modal-q.v1", "rank0_only": True}
        if h1
        else {"schema_version": "task037b.m10-own-grid-EH-modal-q.v1"}
    )
    return metadata, arrays


def _write_canonical(root: Path, tag: str) -> dict[str, object]:
    directory = root / tag
    directory.mkdir()
    result: dict[str, object] = {}
    for side in ("bottom", "top"):
        roles: dict[str, object] = {}
        for role in ("active_trace", "full_fe"):
            shard_path = directory / f"{side}_{role}_rank0000.jsonl"
            shard = write_canonical_packet_shard(
                shard_path, [((side, role, 0, 0, "s"), 0j)], audit_packets=True
            )
            shard["rank"] = 0
            manifest = canonical_shard_manifest(
                role=f"{side}_{role}",
                mpi_size=8,
                shard_metadata=[shard],
                extractor_audit={"by_rank": [{"local_packet_count": 1}]},
            )
            manifest_path = directory / f"{side}_{role}_manifest.json"
            roles[role] = {
                "manifest": str(manifest_path),
                "manifest_sha256": write_canonical_manifest(manifest_path, manifest),
                "schema_version": checker.MANIFEST_SCHEMA,
                "dtype": "complex128",
                "pass": True,
            }
        result[side] = {"roles": roles}
    return result


def _orders() -> list[dict[str, object]]:
    rows = []
    for side in ("bottom", "top"):
        for index in range(20):
            for polarization in ("s", "p"):
                rows.append(
                    {
                        "side": side,
                        "m": index,
                        "n": 0,
                        "polarization": polarization,
                        "beta_per_nm": [1.0, 0.0],
                        "total_projection": [0.0, 0.0],
                        "incident_projection": [0.0, 0.0],
                        "outgoing_amplitude": [0.0, 0.0],
                        "outgoing_amplitude_at_boundary": [0.0, 0.0],
                        "power_ratio": 0.1,
                        "R": 0.1,
                        "T": 0.2,
                    }
                )
    return rows


def _absorption() -> dict[str, object]:
    return {
        "local_regions": {
            "bottom": {"total_absorbed_power_code_units": 0.1},
            "top": {"total_absorbed_power_code_units": 0.2},
        },
        "middle_modal_region": {"absorbed_power_code_units": 0.4},
    }


def _online(
    grid: dict[str, object],
    canonical: dict[str, object],
    h1_path: str,
    h1_sha: str,
    full3d_path: str,
    full3d_sha: str,
) -> dict[str, object]:
    true_residuals = {name: 1.0e-10 for name in checker.RESIDUAL_FIELDS}
    pinned = {
        "schema_version": "task037b.h1-pinned-full3d-reference-gate.v1",
        "pass": True,
        "expected_sha256": full3d_sha,
        "observed_sha256": full3d_sha,
        "current_hybrid_source_sha": SOURCE_SHA,
        "failures": [],
        "checks": {"record_hash_matches_expected": True},
    }
    lifecycle = {
        "schema_version": "task037b.m10-lifecycle.v1",
        "order": list(checker.LIFECYCLE),
        "observed": list(checker.LIFECYCLE),
        "timestamps": [{"stage": name} for name in checker.LIFECYCLE],
        "pass": True,
    }
    physics = {
        "traction": {
            "role": "exact_variational_conormal_dual",
            "bottom": {"relative_dual": 1.0e-10},
            "top": {"relative_dual": 1.0e-10},
        },
        "energy": {"R": 0.1, "T": 0.2, "A": 0.7, "A_volume": 0.7, "closure": 0.0},
        "absorption": _absorption(),
        "external_orders": _orders(),
        "order_audit": {
            "pass": True,
            "count": 80,
            "unique_key_count": 80,
            "keys_unique": True,
            "identity_valid": True,
            "all_finite": True,
        },
        "own_grid": grid,
        "canonical": canonical,
        "own_physics_pass": True,
        "canonical_pass": True,
        "physics_pass": True,
    }
    return {
        "record_schema": checker.RECORD_SCHEMA,
        "qualification_schema": checker.QUALIFICATION_SCHEMA,
        "case_label": "synthetic_m10",
        "profile": dict(checker.PROFILE),
        "ordinary_default_changed": False,
        "explicit_opt_in": True,
        "source": {
            "before": {
                "commit_sha": SOURCE_SHA,
                "verified_clean_sha": SOURCE_SHA,
                "tracked_source_dirty": False,
                "stable_and_clean_before": True,
            },
            "after": {
                "head": SOURCE_SHA,
                "verified_clean_sha": SOURCE_SHA,
                "clean": True,
                "matches_verified_clean_sha": True,
            },
        },
        "authority_bindings": {
            "h1_direct_hybrid": {"path": h1_path, "sha256": h1_sha},
            "full3d": {"path": full3d_path, "sha256": full3d_sha},
            "pinned_full3d": pinned,
        },
        "linear": {
            "reason": 2,
            "iterations": 792,
            "linear_pass": True,
            "postsolve_residuals": true_residuals,
            "postsolve_audit": {"pass": True},
        },
        "recovery": {"recovery_pass": True},
        "physics": physics,
        "lifecycle": lifecycle,
        "final_release": {
            "order": list(checker.FINAL_RELEASE_ORDER),
            "checks": {name: True for name in checker.FINAL_RELEASE_CHECKS},
            "pass": True,
        },
        "offline_comparisons": {"Full3D": "not_run_offline_checker"},
        "qualification": {
            name: True
            for name in (
                "numerical_pass",
                "release_pass",
                "recovery_pass",
                "physics_pass",
                "lifecycle_pass",
                "source_after_pass",
                "final_release_pass",
                "integration_performance_pass",
                "error_free",
            )
        },
        "online_pass": True,
        "status": "online_candidate_pass_awaiting_offline_checker",
    }


def _watchdog(root: Path, online_path: Path, source: str) -> tuple[Path, str]:
    stage, timeline, stdout = (
        root / name
        for name in ("memory_stages.jsonl", "memory_timeline.csv", "worker_stdout.txt")
    )
    stage.write_text("{}\n")
    timeline.write_text("timestamp_utc\n")
    stdout.write_text("worker\n")
    artifacts = [
        {
            "path": str(path),
            "exists": True,
            "bytes": path.stat().st_size,
            "sha256": _sha(path),
        }
        for path in (online_path, stage, timeline, stdout)
    ]
    summary = {
        "schema": checker.WATCHDOG_SCHEMA,
        "frozen": True,
        "explicit_opt_in": True,
        "ordinary_default_changed": False,
        "source_preflight": {
            "head": source,
            "verified_clean_sha": source,
            "clean": True,
            "match": True,
            "dirty": "",
        },
        "worker": {"return_code": 0},
        "termination": {
            "classification": "natural_exit",
            "termination_calls": 1,
            "process_control": {"worker_exited": True, "process_group_exited": True},
        },
        "resource": {
            "sample_count": 1,
            "process_tree_peak_rss_mib": 6144.0,
            "process_tree_peak_swap_mib": 0.0,
            "rss_pass": True,
            "swap_pass": True,
            "pass": True,
            "timeline_authority": "simultaneous mpi_process_tree_rss_mb",
        },
        "qualification": {
            "checks": {
                "worker_exit0": True,
                "online_pass": True,
                "resource_pass": True,
                "swap_zero": True,
                "no_timeout": True,
                "process_group_clean": True,
            },
            "pass": True,
            "status": "watchdog_pass_awaiting_offline_checker",
        },
        "artifacts": artifacts,
        "failures": [],
        "status": "watchdog_pass_awaiting_offline_checker",
        "online_record": {
            "path": str(online_path),
            "sha256": _sha(online_path),
            "json_valid": True,
            "online_pass": True,
        },
    }
    path = root / "watchdog_summary.json"
    path.write_text(json.dumps(summary, indent=2) + "\n")
    return path, _sha(path)


def _fixture(tmp_path: Path) -> tuple[Namespace, dict[str, object]]:
    candidate_dir, h1_dir = tmp_path / "candidate", tmp_path / "h1"
    candidate_dir.mkdir()
    h1_dir.mkdir()
    candidate_grid, candidate_arrays = _write_grid(candidate_dir / "candidate.npz")
    h1_grid, h1_arrays = _write_grid(h1_dir / "h1.npz", h1=True)
    candidate_canonical, h1_canonical = (
        _write_canonical(candidate_dir, "canonical"),
        _write_canonical(h1_dir, "canonical"),
    )
    full3d = tmp_path / "full3d.json"
    full3d.write_text("{}\n")
    h1_solver = tmp_path / "h1_solver.json"
    h1_solver.write_text(
        json.dumps(
            {
                "h1_telemetry": {"own_grid": h1_grid, "canonical_export": h1_canonical},
                "validation": {
                    "external_diffraction_orders": _orders(),
                    "port_power": {"R_total": 0.1, "T_total": 0.2, "A_balance": 0.7},
                },
                "physical_field_reconstruction": {
                    "volume_absorption": {
                        "A_volume_total": 0.7,
                        "energy_closure_error": 0.0,
                        **_absorption(),
                    },
                },
            }
        )
        + "\n"
    )
    h1_summary = tmp_path / "h1_summary.json"
    h1_summary.write_text(
        json.dumps(
            {
                "solver_record_sha256": _sha(h1_solver),
                "solver_record_ignored_path": str(h1_solver),
            }
        )
        + "\n"
    )
    online = candidate_dir / "online.json"
    online.write_text(
        json.dumps(
            _online(
                candidate_grid,
                candidate_canonical,
                str(h1_summary),
                _sha(h1_summary),
                str(full3d),
                _sha(full3d),
            )
        )
    )
    watchdog_path, watchdog_sha = _watchdog(tmp_path, online, SOURCE_SHA)
    significant = tmp_path / "significant.json"
    significant.write_text("{}\n")
    values = {
        "--watchdog-summary": watchdog_path,
        "--watchdog-summary-sha256": watchdog_sha,
        "--expected-source-sha": SOURCE_SHA,
        "--h1-summary": h1_summary,
        "--h1-summary-sha256": _sha(h1_summary),
        "--h1-solver-record": h1_solver,
        "--h1-solver-record-sha256": _sha(h1_solver),
        "--full3d-reference": full3d,
        "--full3d-reference-sha256": _sha(full3d),
        "--significant-reference": significant,
        "--significant-reference-sha256": _sha(significant),
        "--output": tmp_path / "checker.json",
    }
    argv = [item for pair in values.items() for item in (pair[0], str(pair[1]))]
    return checker.parse_args(argv), {
        "online": online,
        "watchdog": watchdog_path,
        "candidate_arrays": candidate_arrays,
        "h1_arrays": h1_arrays,
    }


def _argv(args: Namespace, output: Path | None = None) -> list[str]:
    fields = (
        "watchdog_summary",
        "watchdog_summary_sha256",
        "expected_source_sha",
        "h1_summary",
        "h1_summary_sha256",
        "h1_solver_record",
        "h1_solver_record_sha256",
        "full3d_reference",
        "full3d_reference_sha256",
        "significant_reference",
        "significant_reference_sha256",
    )
    flags = tuple(f"--{field.replace('_', '-')}" for field in fields)
    result = [
        item
        for flag, field in zip(flags, fields)
        for item in (flag, str(getattr(args, field)))
    ]
    return [*result, "--output", str(args.output if output is None else output)]


def test_synthetic_complete_positive_top_level(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    args, _payload = _fixture(tmp_path)
    h1_solver = json.loads(Path(args.h1_solver_record).read_text())
    assert "volume_absorption" not in h1_solver["validation"]
    assert checker._h1_volume_absorption(h1_solver)["A_volume_total"] == pytest.approx(
        0.7
    )
    monkeypatch.setattr(checker, "_compare_full_hybrid", lambda *_args: {"pass": True})
    monkeypatch.setattr(
        checker, "_compare_to_significant_reference", lambda *_args: {"pass": True}
    )
    monkeypatch.setattr(checker, "_load_significant_reference", lambda *_args: {})
    monkeypatch.setattr(checker, "_significant_reference_order_map", lambda *_args: {})
    result = checker.check_evidence(args)
    assert result["pass"] is True and result["failures"] == []
    assert all(
        result[name] is True
        for name in (
            "h1_grid_pass",
            "h1_canonical_pass",
            "payload_comparison_pass",
            "canonical_comparison_pass",
            "observables_pass",
        )
    )


def test_h1_absorption_wrong_validation_layer_fails(tmp_path: Path) -> None:
    args, _payload = _fixture(tmp_path)
    solver = json.loads(Path(args.h1_solver_record).read_text())
    wrong = json.loads(json.dumps(solver))
    wrong["validation"]["volume_absorption"] = wrong[
        "physical_field_reconstruction"
    ].pop("volume_absorption")
    with pytest.raises(checker.EvidenceError):
        checker._h1_volume_absorption(wrong)


def test_significant_reference_order_map_uses_frozen_authority() -> None:
    reference_path = (
        checker.ROOT
        / "benchmarks/cases/095_high_order_local_hp_resource_envelope/records/"
        "significant_channel_reference_v1.json"
    )
    reference = checker._load_significant_reference(
        reference_path,
        "83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3",
    )
    frozen_orders = checker._significant_reference_order_map(reference)
    assert len(frozen_orders) == 12
    result = checker._compare_to_significant_reference(
        frozen_orders,
        frozen_orders,
        reference,
    )
    assert result["analytic_identity_pass_count"] == 12
    assert result["full3d_power_pass_count"] == 12
    assert result["full3d_complex_amplitude_pass_count"] == 12
    assert result["hybrid_power_pass_count"] == 12
    assert result["hybrid_complex_amplitude_pass_count"] == 12
    assert result["pass"] is True


def test_hash_tamper_and_output_collision_fail_closed(tmp_path: Path) -> None:
    args, _payload = _fixture(tmp_path)
    bad = Namespace(**{**vars(args), "watchdog_summary_sha256": "0" * 64})
    bad_output = tmp_path / "bad.json"
    assert checker.main(_argv(bad, bad_output)) == 1
    assert not json.loads(bad_output.read_text())["pass"]
    bad_authority = Namespace(**{**vars(args), "full3d_reference_sha256": "0" * 64})
    assert checker.main(_argv(bad_authority, tmp_path / "bad_authority.json")) == 1
    bad_json = tmp_path / "bad_json_full3d.json"
    bad_json.write_text("{not-json\n")
    bad_json_args = Namespace(
        **{
            **vars(args),
            "full3d_reference": bad_json,
            "full3d_reference_sha256": _sha(bad_json),
        }
    )
    bad_json_output = tmp_path / "bad_json.json"
    assert checker.main(_argv(bad_json_args, bad_json_output)) == 1
    bad_json_result = json.loads(bad_json_output.read_text())
    assert not bad_json_result["pass"] and bad_json_result["failures"]
    args.output.write_text("existing")
    assert checker.main(_argv(args)) == 2


def test_watchdog_recomputed_boundaries(tmp_path: Path) -> None:
    _args, payload = _fixture(tmp_path)
    summary = json.loads(payload["watchdog"].read_text())
    passed, _gate, failures, _path, _record = checker._check_watchdog(
        payload["watchdog"], summary, SOURCE_SHA, (tmp_path,)
    )
    assert passed and not failures
    mutations = (
        lambda d: d["resource"].update(sample_count=0),
        lambda d: d["resource"].update(process_tree_peak_rss_mib=6144.1),
        lambda d: d["resource"].update(process_tree_peak_swap_mib=1.0),
        lambda d: d["termination"]["process_control"].update(
            process_group_exited=False
        ),
        lambda d: d["source_preflight"].update(head="b" * 40),
    )
    for mutate in mutations:
        broken = json.loads(json.dumps(summary))
        mutate(broken)
        passed, _gate, failures, _path, _record = checker._check_watchdog(
            payload["watchdog"], broken, SOURCE_SHA, (tmp_path,)
        )
        assert not passed and failures


def test_npz_canonical_and_numeric_thresholds(tmp_path: Path) -> None:
    _args, payload = _fixture(tmp_path)
    online = json.loads(payload["online"].read_text())
    metadata = online["physics"]["own_grid"]
    broken = {
        **metadata,
        "arrays": {
            **metadata["arrays"],
            "bottom_q": {**metadata["arrays"]["bottom_q"], "sha256": "0" * 64},
        },
    }
    assert not checker._load_candidate_grid(broken, (payload["online"].parent,))[0]
    assert not checker._load_candidate_grid(
        {**metadata, "keys": ["x_nm"]}, (payload["online"].parent,)
    )[0]
    for name, array in (
        ("x_nm", np.arange(39, dtype=np.float64)),
        ("E_V_per_m", np.zeros((5, 20, 40, 3), dtype=np.float64)),
    ):
        path = tmp_path / f"bad_{name}.npz"
        arrays = dict(payload["candidate_arrays"])
        arrays[name] = array
        np.savez(path, **arrays)
        bad = {
            **metadata,
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _sha(path),
        }
        assert not checker._load_candidate_grid(bad, (tmp_path,))[0]
    canonical = online["physics"]["canonical"]["bottom"]["roles"]["active_trace"]
    assert not checker._canonical_role(
        {**canonical, "manifest_sha256": "0" * 64},
        "bottom",
        "active_trace",
        (payload["online"].parent,),
    )[0]
    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    shard_path = duplicate / "duplicate.jsonl"
    shard = write_canonical_packet_shard(
        shard_path,
        [("duplicate", 1.0 + 0j), ("duplicate", 2.0 + 0j)],
        audit_packets=False,
    )
    shard["rank"] = 0
    manifest = canonical_shard_manifest(
        role="bottom_active_trace",
        mpi_size=8,
        shard_metadata=[shard],
        extractor_audit={"by_rank": [{"local_packet_count": 2}]},
    )
    manifest_path = duplicate / "manifest.json"
    manifest_sha = write_canonical_manifest(manifest_path, manifest)
    assert not checker._canonical_role(
        {"manifest": str(manifest_path), "manifest_sha256": manifest_sha, "pass": True},
        "bottom",
        "active_trace",
        (tmp_path,),
    )[0]
    candidate, authority = payload["candidate_arrays"], payload["h1_arrays"]
    for name, index in (
        ("bottom_q", (0,)),
        ("E_V_per_m", (0, 0, 0, 0)),
        ("modal_amplitudes", (0,)),
    ):
        bad_arrays = {key: value.copy() for key, value in candidate.items()}
        bad_arrays[name][index] = 1.0
        assert not checker._payload_comparison(bad_arrays, authority)[0]
    roles = {
        role: {("key",): 0j}
        for role in (
            "bottom_active_trace",
            "bottom_full_fe",
            "top_active_trace",
            "top_full_fe",
        )
    }
    changed = {role: dict(values) for role, values in roles.items()}
    changed["top_full_fe"][("key",)] = 1.0 + 0j
    assert not checker._canonical_comparison(changed, roles)[0]


def test_orders_and_source_safety() -> None:
    rows = _orders()
    assert len(checker._orders_map(rows, "synthetic")) == 80
    with pytest.raises(checker.EvidenceError):
        checker._orders_map(rows[:-1], "short")
    scalar = [dict(row) for row in rows]
    scalar[0]["outgoing_amplitude"] = 0j
    with pytest.raises(checker.EvidenceError):
        checker._orders_map(scalar, "scalar")
    source = Path(checker.__file__).read_text()
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    )
    imported.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not any(
        name.startswith("benchmarks.run_task037b_hybrid_iterative") for name in imported
    )
    assert not {"subprocess", "mpi4py", "solver"} & imported
    for token in (
        "controlled_negative",
        "disposition",
        "campaign",
        "legacy",
        "retry",
        "registry",
        "fallback",
    ):
        assert token not in source.lower()
