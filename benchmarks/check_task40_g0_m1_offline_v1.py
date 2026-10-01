"""Offline recheck of the preserved Task40 G0/M1 saved result.

This checker does not build a mesh, assemble an operator, create a factor, or
solve a PDE. It reuses the production authority-limited output checks against
the frozen mode manifest and saved mode files, then audits saved field and
residual packets by hash and direct array arithmetic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from src.runners.physical_p4_schur_v14 import _v21_authority_limited_checks


EXPECTED_RUN_ID = "task40extra_0p7nm_nonseparable_g0_manual_m1_f2_v1"
EXPECTED_SOURCE_SHA = "37635226002787beb26a24baba3a8da333027239"
EXPECTED_INPUT_SHA256 = "d9a53689fbeee530ad7d72954d4665498a3994c3717535a11cd2fc335920322b"
EXPECTED_PHYSICAL_MODEL_SHA256 = "98b38bfca9f2af50b75682320fc20ec8560ee6401e1b6e7dfa5ffbc201060b4b"
EXPECTED_MODE_COUNT = 180
RESIDUAL_LIMIT = 1.0e-6

DEFAULT_RUN_ROOT = Path(
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g0_manual_m1_f2_v1__full3d_iterative__mpi1__Mna/"
    "20261001T135923.003185Z"
)
DEFAULT_RECORD = Path(
    "docs/task40extra_0p7nm_engineering/outcomes/records/"
    "g0_m1_offline_recheck_v1.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _artifact(root: Path, relative: str) -> tuple[Path, dict[str, Any]]:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    return path, {"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path)}


def _complex(value: Any) -> complex:
    if isinstance(value, dict):
        return complex(float(value["real"]), float(value["imag"]))
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return complex(float(value[0]), float(value[1]))
    return complex(value)


def _load_packet_arrays(
    root: Path, packet: dict[str, Any], relative_archive: str
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    metadata = packet["arrays"]
    path, artifact = _artifact(root, relative_archive)
    declared_path = Path(str(metadata["path"]))
    if declared_path.is_absolute():
        declared_path = declared_path.resolve()
    else:
        declared_path = (root / declared_path).resolve()
    if declared_path != path.resolve():
        raise ValueError(f"packet archive path differs from {relative_archive}")
    digest_match = artifact["sha256"] == metadata["sha256"]
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: np.asarray(archive[name]).copy() for name in archive.files}
    finite = all(np.isfinite(value).all() for value in arrays.values())
    descriptors_match = True
    for name in ("rhs", "applied", "residual", "solution"):
        descriptor = packet.get(name)
        if not isinstance(descriptor, dict) or "array_key" not in descriptor:
            continue
        array = arrays[descriptor["array_key"]]
        descriptors_match = descriptors_match and list(array.shape) == descriptor.get("shape")
        descriptors_match = descriptors_match and str(array.dtype) == descriptor.get("dtype")
    return arrays, {
        **artifact,
        "declared_sha256": metadata["sha256"],
        "sha256_matches_packet": digest_match,
        "array_count": len(arrays),
        "arrays_finite": bool(finite),
        "packet_descriptors_match": bool(descriptors_match),
        "array_shapes": {name: list(value.shape) for name, value in arrays.items()},
    }


def _residual_audit(
    packet: dict[str, Any], arrays: dict[str, np.ndarray]
) -> dict[str, Any]:
    rhs = arrays[packet["rhs"]["array_key"]]
    applied = arrays[packet["applied"]["array_key"]]
    residual = arrays[packet["residual"]["array_key"]]
    shapes_match = rhs.shape == applied.shape == residual.shape
    finite = bool(
        np.isfinite(rhs).all() and np.isfinite(applied).all() and np.isfinite(residual).all()
    )
    if not shapes_match or not finite:
        return {
            "finite_rhs_applied_residual": finite,
            "shapes_match": bool(shapes_match),
            "rhs_norm": None,
            "recomputed_norm_b_minus_Ax_over_b": None,
            "stored_residual_vector_norm_over_b": None,
            "packet_explicit_relative_residual": packet.get("explicit_relative_residual"),
            "relative_residual_vector_disagreement": None,
            "residual_vector_consistent": False,
            "recomputed_matches_packet": False,
            "residual_gate": False,
            "limit": RESIDUAL_LIMIT,
        }
    rhs_norm = float(np.linalg.norm(rhs))
    computed = rhs - applied
    recomputed_relative = float(np.linalg.norm(computed) / rhs_norm) if rhs_norm > 0 else float("inf")
    residual_disagreement = float(
        np.linalg.norm(computed - residual)
        / max(rhs_norm, float(np.linalg.norm(applied)), 1.0)
    )
    stored_relative = float(packet["explicit_relative_residual"])
    stored_residual_norm = float(np.linalg.norm(residual) / rhs_norm) if rhs_norm > 0 else float("inf")
    return {
        "finite_rhs_applied_residual": finite,
        "shapes_match": bool(shapes_match),
        "rhs_norm": rhs_norm,
        "recomputed_norm_b_minus_Ax_over_b": recomputed_relative,
        "stored_residual_vector_norm_over_b": stored_residual_norm,
        "packet_explicit_relative_residual": stored_relative,
        "relative_residual_vector_disagreement": residual_disagreement,
        "residual_vector_consistent": bool(residual_disagreement <= 1.0e-12),
        "recomputed_matches_packet": bool(
            np.isclose(recomputed_relative, stored_relative, rtol=1.0e-10, atol=1.0e-14)
            and np.isclose(stored_residual_norm, stored_relative, rtol=1.0e-10, atol=1.0e-14)
        ),
        "residual_gate": bool(
            np.isfinite(recomputed_relative) and recomputed_relative <= RESIDUAL_LIMIT
        ),
        "limit": RESIDUAL_LIMIT,
    }


def _saved_channel_checks(
    mode_rows: list[dict[str, Any]],
    output_dir: Path,
    port_metrics: dict[str, Any],
    volume_metrics: dict[str, Any],
    *,
    electric_finite: bool,
    auxiliary_finite: bool,
    field_export: dict[str, Any],
    solver_facts: dict[str, Any],
    post_release_relative: float,
) -> tuple[dict[str, bool], dict[str, Any]]:
    modes = [
        SimpleNamespace(
            side=str(row["side"]),
            m=int(row["m"]),
            n=int(row["n"]),
            polarization=str(row["polarization"]),
        )
        for row in mode_rows
    ]
    amplitudes_path = output_dir / "dtn_auxiliary_amplitudes_3d.json"
    amplitudes = _read_json(amplitudes_path)
    auxiliary = np.asarray(
        [_complex(row["outgoing_amplitude"]) for row in amplitudes], dtype=np.complex128
    )
    output = {
        "port_metrics": port_metrics,
        "volume_metrics": volume_metrics,
        "electric_finite": bool(electric_finite),
        "auxiliary_finite": bool(auxiliary_finite),
        "auxiliary": auxiliary,
        "field_export": field_export,
    }
    common = {"fine": {"modes": modes}}
    return _v21_authority_limited_checks(
        solver_facts,
        output,
        post_release_relative=post_release_relative,
        common=common,
        output_dir=output_dir,
    )


def _resource_cleanup_pass(watchdog: dict[str, Any], swap_qualification: dict[str, Any]) -> bool:
    return bool(
        watchdog.get("sampled_process_tree_swap_peak_bytes") == 0
        and watchdog.get("descendants_cleared") is True
        and watchdog.get("remaining_child_pids") == []
        and swap_qualification.get("status") == "qualified_zero"
        and swap_qualification.get("process_tree_peak_swap_bytes") == 0
        and swap_qualification.get("process_tree_all_status_readable") is True
        and swap_qualification.get("process_tree_identity_coverage") == "complete"
    )


def audit_saved_m1(run_root: Path, repository_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    repository_root = repository_root.resolve()
    worker_path, worker_file = _artifact(
        run_root, "task40extra_nonseparable_0p7nm_p6q4_summary.json"
    )
    manifest_path, manifest_file = _artifact(run_root, "run_manifest.json")
    run_summary_path, run_summary_file = _artifact(run_root, "run_summary.json")
    worker = _read_json(worker_path)
    manifest = _read_json(manifest_path)
    run_summary = _read_json(run_summary_path)

    mode_path, mode_file = _artifact(run_root, "task40q4_ordered_mode_manifest.json")
    mode_manifest = _read_json(mode_path)
    declared_mode_hash = worker.get("mode_manifest", {}).get("sha256")
    output_dir = run_root / "numerical_output"
    relative_outputs = (
        "numerical_output/dtn_port_diffraction_orders_3d.json",
        "numerical_output/dtn_auxiliary_amplitudes_3d.json",
        "numerical_output/dtn_port_power_metrics_3d.json",
        "numerical_output/port_power.json",
        "numerical_output/volume_absorption.json",
        "numerical_output/full3d_reference_samples.json",
        "numerical_output/full3d_reference_samples.npz",
    )
    artifacts = {"worker_summary": worker_file, "run_manifest": manifest_file, "run_summary": run_summary_file, "mode_manifest": mode_file}
    _, input_file = _artifact(run_root, "input_original.dat")
    artifacts["input_original.dat"] = input_file
    for relative in relative_outputs:
        _, artifacts[relative] = _artifact(run_root, relative)

    port_metrics = _read_json(output_dir / "dtn_port_power_metrics_3d.json")
    port_power = _read_json(output_dir / "port_power.json")
    volume_power = _read_json(output_dir / "volume_absorption.json")
    ordered_modes = mode_manifest["modes"]
    mode_count = int(mode_manifest["mode_count"])
    keys = [
        (str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"]))
        for row in ordered_modes
    ]
    unique_manifest_keys = len(set(keys)) == len(keys)
    top_count = port_metrics.get("dtn_port_top_mode_count")
    bottom_count = port_metrics.get("dtn_port_bottom_mode_count")
    counts_match = bool(
        mode_count == len(ordered_modes) == EXPECTED_MODE_COUNT
        and port_metrics.get("dtn_port_mode_count") == mode_count
        and isinstance(top_count, int)
        and isinstance(bottom_count, int)
        and top_count + bottom_count == mode_count
    )

    x2_path, x2_file = _artifact(run_root, "x2_retained_final.json")
    x2 = _read_json(x2_path)
    field_arrays, field_archive_file = _load_packet_arrays(
        run_root, x2, "x2_retained_final.npz"
    )
    artifacts["x2_retained_final.json"] = x2_file
    artifacts["x2_retained_final.npz"] = field_archive_file
    full_descriptor = x2["full_solution"]
    full_field = field_arrays[full_descriptor["array_key"]]
    field_descriptor_matches = bool(
        list(full_field.shape) == full_descriptor["shape"]
        and full_field.dtype == np.dtype(full_descriptor["dtype"])
        and full_field.dtype == np.dtype(np.complex128)
        and np.isfinite(full_field).all()
        and x2.get("complete_field_saved") is True
    )

    residual_results = {}
    residual_relatives = {}
    for name, json_relative, npz_relative in (
        ("final", "final_residual/q4_final.json", "final_residual/q4_final.npz"),
        (
            "post_release",
            "post_release_final_residual/q4_post_release_final.json",
            "post_release_final_residual/q4_post_release_final.npz",
        ),
    ):
        packet_path, packet_file = _artifact(run_root, json_relative)
        packet = _read_json(packet_path)
        arrays, archive_file = _load_packet_arrays(run_root, packet, npz_relative)
        audit = _residual_audit(packet, arrays)
        audit["packet_sha256"] = packet_file["sha256"]
        audit["archive_sha256"] = archive_file["sha256"]
        audit["archive_sha256_matches_packet"] = archive_file["sha256_matches_packet"]
        audit["archive_arrays_finite"] = archive_file["arrays_finite"]
        audit["packet_descriptors_match"] = archive_file["packet_descriptors_match"]
        residual_results[name] = audit
        residual_relatives[name] = audit["recomputed_norm_b_minus_Ax_over_b"]
        artifacts[json_relative] = packet_file
        artifacts[npz_relative] = archive_file

    field_export = worker["output_facts"]["field_export"]
    sample_path = output_dir / "full3d_reference_samples.npz"
    with np.load(sample_path, allow_pickle=False) as sample_archive:
        sample_finite = all(
            np.isfinite(np.asarray(sample_archive[name])).all()
            for name in ("E_V_per_m", "H_A_per_m")
        )
    solver = worker["solver"]
    facts = x2["facts"]
    solver_facts = {
        "status": solver.get("status"),
        "final_true_residual": solver.get("final_true_residual"),
        "final_evaluation": {
            name: facts.get(name)
            for name in (
                "port_closure_relative",
                "internal_residual_relative",
                "native_identity_relative",
                "schur_port_identity_relative",
            )
        },
    }
    checks, check_facts = _saved_channel_checks(
        ordered_modes,
        output_dir,
        port_power,
        {"A_volume_total": volume_power.get("A_volume_total")},
        electric_finite=bool(sample_finite and field_descriptor_matches),
        auxiliary_finite=bool(
            all(
                np.isfinite(_complex(row[name]))
                for row in _read_json(output_dir / "dtn_auxiliary_amplitudes_3d.json")
                for name in (
                    "auxiliary_amplitude_total_projection",
                    "incident_projection",
                    "outgoing_amplitude",
                    "outgoing_amplitude_at_boundary",
                )
            )
        ),
        field_export=field_export,
        solver_facts=solver_facts,
        post_release_relative=residual_relatives["post_release"],
    )
    check_facts["saved_output_finite_oracle"] = {
        "sample_E_H_finite": bool(sample_finite),
        "complete_field_descriptor_matches": field_descriptor_matches,
    }

    raw_false_physical_checks = sorted(
        key for key, value in worker.get("physical_checks", {}).items() if value is False
    )
    expected_old_failures = [
        "channel_amplitudes_finite",
        "channel_files",
        "channel_powers_finite",
    ]
    old_bug_signature = bool(
        raw_false_physical_checks == expected_old_failures
        and worker.get("status") == "Q4_ORIGINAL_CONSISTENCY_GATE_FAIL"
        and worker.get("official_result") is False
        and worker.get("authority_limited_checks", {}).get("channel_facts", {}).get(
            "expected_count"
        ) == 80
        and worker.get("authority_limited_checks", {}).get("channel_facts", {}).get(
            "checked_count"
        ) == mode_count
    )
    manifest_identity = bool(
        manifest.get("run_id") == EXPECTED_RUN_ID
        and manifest.get("source_sha") == EXPECTED_SOURCE_SHA
        and manifest.get("input_sha256") == EXPECTED_INPUT_SHA256
        and input_file["sha256"] == manifest.get("input_sha256")
        and manifest.get("physical_model_sha256") == EXPECTED_PHYSICAL_MODEL_SHA256
        and worker.get("source_sha") == manifest.get("source_sha")
        and mode_manifest.get("mode_count") == mode_count
        and declared_mode_hash == mode_file["sha256"]
    )
    residual_pass = all(
        item["finite_rhs_applied_residual"]
        and item["archive_sha256_matches_packet"]
        and item["archive_arrays_finite"]
        and item["packet_descriptors_match"]
        and item["shapes_match"]
        and item["residual_vector_consistent"]
        and item["recomputed_matches_packet"]
        and item["residual_gate"]
        for item in residual_results.values()
    )
    release = worker.get("release_facts", {})
    release_pass = bool(
        release.get("h6_and_bal_h") == "RELEASED"
        and release.get("p6", {}).get("owner_refs_cleared") is True
        and release.get("p6", {}).get("released_after_final_residual") is True
    )
    watch_path, watch_file = _artifact(run_root, "watchdog/summary.json")
    watch = _read_json(watch_path)
    artifacts["watchdog/summary.json"] = watch_file
    swap_qualification = run_summary.get("task40_swap_qualification", {})
    resource_cleanup_pass = _resource_cleanup_pass(watch, swap_qualification)
    all_new_checks = bool(
        manifest_identity
        and counts_match
        and unique_manifest_keys
        and field_archive_file["sha256_matches_packet"]
        and field_archive_file["arrays_finite"]
        and field_descriptor_matches
        and residual_pass
        and release_pass
        and resource_cleanup_pass
        and all(checks.values())
        and sample_finite
    )
    recovered = bool(old_bug_signature and all_new_checks)

    current_source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository_root, text=True
    ).strip()
    checker_path = Path(__file__).resolve()
    record = {
        "schema": "task40extra.g0-m1-offline-recheck.v1",
        "offline_recheck_status": (
            "CHECKER_BUG_RECOVERED_OFFLINE" if recovered else "OFFLINE_RECHECK_NOT_QUALIFIED"
        ),
        "official_result": "not_reissued_offline",
        "run_identity": {
            "run_id": manifest.get("run_id"),
            "run_root": str(run_root.relative_to(repository_root)),
            "run_source_sha": manifest.get("source_sha"),
            "checker_source_sha": current_source,
            "checker_sha256": _sha256(checker_path),
            "input_sha256": manifest.get("input_sha256"),
            "physical_model_sha256": manifest.get("physical_model_sha256"),
        },
        "original_worker_record_unchanged": {
            "status": worker.get("status"),
            "classification": worker.get("result_classification"),
            "official_result": worker.get("official_result"),
            "output_role": worker.get("output_role"),
            "run_summary_status": run_summary.get("status"),
            "run_summary_classification": run_summary.get("result_classification"),
            "run_summary_exit_status": run_summary.get("exit_status"),
            "physical_checks_false": raw_false_physical_checks,
            "old_expected_channel_count": worker.get("authority_limited_checks", {}).get(
                "channel_facts", {}
            ).get("expected_count"),
            "old_checked_channel_count": worker.get("authority_limited_checks", {}).get(
                "channel_facts", {}
            ).get("checked_count"),
        },
        "offline_findings": {
            "bug_signature_matches_fixed_count_gate": old_bug_signature,
            "manifest_identity_matches_frozen_run": manifest_identity,
            "mode_count": mode_count,
            "mode_keys_unique": unique_manifest_keys,
            "mode_file_counts_match_manifest": counts_match,
            "authority_limited_checks": checks,
            "authority_limited_facts": check_facts,
            "field_packet": {
                "complete_field_saved": x2.get("complete_field_saved"),
                "full_solution_shape": list(full_field.shape),
                "full_solution_dtype": str(full_field.dtype),
                "complete_field_descriptor_matches": field_descriptor_matches,
                "sample_E_H_finite": bool(sample_finite),
                "archive_sha256": field_archive_file["sha256"],
            },
            "residual_packets": residual_results,
            "released_state": {
                "status": release.get("h6_and_bal_h"),
                "p6_status": release.get("p6", {}).get("status"),
                "owner_refs_cleared": release.get("p6", {}).get("owner_refs_cleared"),
                "released_after_final_residual": release.get("p6", {}).get(
                    "released_after_final_residual"
                ),
            },
            "strict_identity_preserved_as_measured": {
                "source_packet": "x2_retained_final.json",
                "source_packet_sha256": x2_file["sha256"],
                "source_archive_sha256": field_archive_file["sha256"],
                "values": {
                    name: facts.get(name)
                    for name in (
                        "native_identity_relative",
                        "internal_residual_relative",
                        "schur_port_identity_relative",
                        "port_closure_relative",
                    )
                },
                "limits": worker.get("authority_limited_checks", {}).get("identity_limits"),
                "recomputed_by_checker": False,
            },
            "resources": {
                "watchdog_classification": watch.get("classification"),
                "leader_exit_code": watch.get("leader_exit_code"),
                "elapsed_seconds": watch.get("elapsed_seconds"),
                "sampled_process_tree_rss_peak_bytes": watch.get(
                    "sampled_process_tree_rss_peak_bytes"
                ),
                "sampled_process_tree_pss_peak_bytes": watch.get(
                    "sampled_process_tree_pss_peak_bytes"
                ),
                "sampled_process_tree_swap_peak_bytes": watch.get(
                    "sampled_process_tree_swap_peak_bytes"
                ),
                "descendants_cleared": watch.get("descendants_cleared"),
                "remaining_child_pids": watch.get("remaining_child_pids"),
            },
            "all_required_offline_checks_pass": all_new_checks,
            "resource_cleanup_pass": resource_cleanup_pass,
        },
        "evidence_files": artifacts,
    }
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = audit_saved_m1(args.run_root, args.repository_root)
    _write_json(args.record.resolve(), result)
    print(
        json.dumps(
            {
                "status": result["offline_recheck_status"],
                "run_id": result["run_identity"]["run_id"],
                "record": str(args.record.resolve()),
                "channel_checks": result["offline_findings"]["authority_limited_checks"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["offline_recheck_status"] == "CHECKER_BUG_RECOVERED_OFFLINE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
