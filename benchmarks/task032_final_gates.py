from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Callable


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _canonical_text_sha256(path: Path) -> str:
    """Hash generated text with checkout-independent LF line endings.

    Task032 funnel records were generated and signed with LF bytes.  Git may
    materialize the same text with CRLF when ``core.autocrlf=true`` on Windows,
    which must not turn an otherwise identical tracked record into a failed
    provenance gate.  Semantic or formatting changes other than line endings
    still change this digest.
    """

    payload = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(payload).hexdigest()


def _all_true(values: dict[str, Any]) -> bool:
    return bool(values) and all(value is True for value in values.values())


def _all_formal_true(values: dict[str, Any]) -> bool:
    formal = {
        key: value
        for key, value in values.items()
        if not str(key).startswith("diagnostic_")
    }
    return bool(formal) and all(value is True for value in formal.values())


def _finite_le(value: Any, limit: float) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and abs(number) <= limit


_LEGACY_TASK032_MISSING_EXACT_TRACTION_COMMITS = frozenset(
    {"735774473e54415ab5393f2d2cbc9c8d7d2a24e6"}
)


def _exact_traction_gate(
    record: dict[str, Any],
    values: list[Any],
    limit: float,
) -> tuple[bool, str]:
    """Fail closed on missing exact duals except for frozen Task032 evidence."""

    if all(value is not None for value in values):
        return (
            all(_finite_le(value, limit) for value in values),
            "exact_variational_conormal_dual",
        )
    metadata = record.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    legacy_sha_bound = bool(
        record.get("schema_version") == 1
        and metadata.get("commit_sha")
        in _LEGACY_TASK032_MISSING_EXACT_TRACTION_COMMITS
    )
    return (
        legacy_sha_bound,
        (
            "legacy_sha_bound_record_predating_exact_dual"
            if legacy_sha_bound
            else "missing_exact_variational_conormal_dual"
        ),
    )


def evaluate_task032_final(
    case_root: Path,
    config: dict[str, Any],
    gate_factory: Callable[..., Any],
) -> list[Any]:
    """Validate Task32 final field, Schur, funnel, memory, and h2 evidence."""

    evidence_root = "cases/080_hybrid_fem_modal_direct_baseline"
    records = case_root / "records"
    gates: list[Any] = []
    mode_counts = [int(value) for value in config["required_mode_counts"]]
    main_records: dict[tuple[str, int], dict[str, Any]] = {}
    main_observed: dict[str, Any] = {}
    main_ok = True
    for level, h_nm in (("h5", 5.0), ("h3", 3.0)):
        for mode_count in mode_counts:
            name = f"hybrid_{level}_m{mode_count}.json"
            record = _load(records / name)
            main_records[(level, mode_count)] = record
            metadata = record.get("metadata", {})
            case = record.get("case", {})
            qualification = record.get("qualification", {})
            residual = record.get("solve", {}).get("true_relative_residual")
            record_ok = (
                record.get("schema_version") == 1
                and metadata.get("commit_sha") == config["required_commit"]
                and metadata.get("verified_clean_sha") == config["required_commit"]
                and metadata.get("container_digest")
                == config["required_container_digest"]
                and metadata.get("mpi_size") == config["required_mpi_size"]
                and metadata.get("scalar_dtype") == config["required_dtype"]
                and metadata.get("git_dirty") is False
                and metadata.get("tracked_source_dirty") is False
                and float(case.get("h_nm", float("nan"))) == h_nm
                and int(case.get("requested_modes_per_direction", -1)) == mode_count
                and _finite_le(residual, config["max_true_relative_residual"])
                and _all_formal_true(record.get("gates", {}))
                and qualification.get("integration_pass") is True
                and qualification.get("clean_source_integration_record") is True
                and qualification.get("physical_field_gates_pass") is True
                and qualification.get("pointwise_h_jump_checked") is True
                and qualification.get("volume_absorption_reconstructed") is True
                and qualification.get("selected_middle_planes_reconstructed") is True
            )
            main_ok = main_ok and record_ok
            main_observed[name] = {
                "commit_sha": metadata.get("commit_sha"),
                "container_digest": metadata.get("container_digest"),
                "mpi_size": metadata.get("mpi_size"),
                "residual": residual,
                "all_runner_formal_gates": _all_formal_true(
                    record.get("gates", {})
                ),
                "diagnostic_gates": {
                    key: value
                    for key, value in record.get("gates", {}).items()
                    if str(key).startswith("diagnostic_")
                },
                "physical_field_gates_pass": qualification.get(
                    "physical_field_gates_pass"
                ),
            }
    gates.append(
        gate_factory(
            "task032_final_clean_main_records",
            main_ok,
            main_observed,
            {
                "levels": ["h5", "h3"],
                "mode_counts": mode_counts,
                "commit": config["required_commit"],
                "mpi_size": config["required_mpi_size"],
                "all_runner_and_physical_field_gates": True,
            },
            evidence_root + "/records/hybrid_h{5,3}_m{120,160}.json",
        )
    )

    funnel_observed: dict[str, Any] = {}
    funnel_ok = True
    for level in ("h5", "h3"):
        funnel = _load(records / f"hybrid_{level}_funnel.json")
        comparisons = funnel.get("comparisons", [])
        latest = comparisons[-1] if comparisons else {}
        diffraction = latest.get("diffraction_orders", {})
        qualification = funnel.get("qualification", {})
        sources = funnel.get("sources", [])
        source_counts = [int(source.get("mode_count_per_direction", -1)) for source in sources]
        expected_source_hashes = [
            _canonical_text_sha256(
                records / f"hybrid_{level}_m{mode_count}.json"
            )
            for mode_count in mode_counts
        ]
        level_ok = (
            funnel.get("status") == "mode_truncation_converged"
            and source_counts == mode_counts
            and all(
                source.get("commit_sha") == config["required_commit"]
                and source.get("tracked_source_dirty") is False
                for source in sources
            )
            and [source.get("sha256") for source in sources]
            == expected_source_hashes
            and qualification.get("mode_count_converged") is True
            and qualification.get("selected_mode_count_per_direction") == mode_counts[-1]
            and qualification.get("latest_pair_mandatory_total_gate_pass") is True
            and qualification.get("latest_pair_strong_total_gate_pass") is True
            and qualification.get("latest_pair_order_gate_pass") is True
            and qualification.get("all_sources_clean") is True
            and _finite_le(
                latest.get("max_absolute_total_delta"),
                config["max_total_delta_strong"],
            )
            and _finite_le(
                latest.get("interface_projection_residual"),
                config["max_interface_projection_residual"],
            )
            and diffraction.get("all_order_gates_pass") is True
            and _finite_le(
                diffraction.get("max_significant_power_relative_delta"),
                config["max_significant_order_relative_delta"],
            )
            and _finite_le(
                diffraction.get("max_significant_complex_amplitude_relative_delta"),
                config["max_significant_order_relative_delta"],
            )
        )
        funnel_ok = funnel_ok and level_ok
        funnel_observed[level] = {
            "mode_counts": source_counts,
            "max_absolute_total_delta": latest.get("max_absolute_total_delta"),
            "interface_projection_residual": latest.get(
                "interface_projection_residual"
            ),
            "max_significant_power_relative_delta": diffraction.get(
                "max_significant_power_relative_delta"
            ),
            "max_significant_complex_amplitude_relative_delta": diffraction.get(
                "max_significant_complex_amplitude_relative_delta"
            ),
            "qualified": qualification.get("mode_count_converged"),
        }
    gates.append(
        gate_factory(
            "task032_final_mode_funnels",
            funnel_ok,
            funnel_observed,
            {
                "max_total_delta": config["max_total_delta_strong"],
                "max_significant_order_relative_delta": config[
                    "max_significant_order_relative_delta"
                ],
                "all_sources_clean": True,
            },
            evidence_root + "/records/hybrid_h{5,3}_funnel.json",
        )
    )

    physical_observed: dict[str, Any] = {}
    physical_ok = True
    for level in ("h5", "h3"):
        record = main_records[(level, mode_counts[-1])]
        field = record.get("physical_field_reconstruction", {})
        volume = field.get("volume_absorption", {})
        interfaces = field.get("interface_continuity", {})
        planes = field.get("selected_plane_full3d_comparison", {}).get("planes", [])
        rta_delta = record.get("full3d_reference_comparison", {}).get(
            "hybrid_minus_full3d", {}
        )
        electric_jumps = [
            interfaces.get(side, {})
            .get("electric_tangential", {})
            .get("relative_l2")
            for side in ("bottom", "top")
        ]
        magnetic_jumps = [
            (
                interfaces.get(side, {}).get(
                    "traction_density_l2_proxy"
                )
                or interfaces.get(side, {}).get(
                    "magnetic_tangential", {}
                )
            ).get("relative_l2")
            for side in ("bottom", "top")
        ]
        exact_traction_duals = [
            interfaces.get(side, {})
            .get("traction_hcurl_dual", {})
            .get("relative_dual")
            for side in ("bottom", "top")
        ]
        exact_traction_limit = float(
            config.get("max_exact_traction_hcurl_dual_relative", 1.0e-8)
        )
        exact_traction_ok, exact_traction_gate_role = _exact_traction_gate(
            record,
            exact_traction_duals,
            exact_traction_limit,
        )
        plane_errors = [
            plane.get(field_name, {}).get("relative_l2")
            for plane in planes
            for field_name in ("electric", "magnetic")
        ]
        level_ok = (
            len(planes) == 5
            and all(
                _finite_le(value, config["max_hybrid_full3d_rta_delta"])
                for value in rta_delta.values()
            )
            and set(rta_delta) == {"R_total", "T_total", "A_balance"}
            and _finite_le(
                volume.get("energy_closure_error"),
                config["max_abs_volume_closure"],
            )
            and _finite_le(
                volume.get("hybrid_minus_full3d_A_volume_total"),
                config["max_hybrid_full3d_rta_delta"],
            )
            and all(
                _finite_le(value, config["max_sampled_interface_e_relative_l2"])
                for value in electric_jumps
            )
            and exact_traction_ok
            and all(
                _finite_le(value, config["max_middle_plane_relative_l2"])
                for value in plane_errors
            )
        )
        physical_ok = physical_ok and level_ok
        physical_observed[level] = {
            "rta_delta": rta_delta,
            "volume_energy_closure_error": volume.get("energy_closure_error"),
            "volume_absorption_delta": volume.get(
                "hybrid_minus_full3d_A_volume_total"
            ),
            "interface_e_relative_l2": electric_jumps,
            "interface_h_relative_l2": magnetic_jumps,
            "interface_h_sampled_proxy_role": "diagnostic_only",
            "traction_hcurl_dual_relative": exact_traction_duals,
            "traction_hcurl_dual_gate": exact_traction_gate_role,
            "max_plane_relative_l2": max(float(value) for value in plane_errors),
        }
    gates.append(
        gate_factory(
            "task032_final_physical_full3d_comparison",
            physical_ok,
            physical_observed,
            {
                "rta_and_volume_delta_max": config[
                    "max_hybrid_full3d_rta_delta"
                ],
                "middle_plane_relative_l2_max": config[
                    "max_middle_plane_relative_l2"
                ],
                "interface_e_relative_l2_max": config[
                    "max_sampled_interface_e_relative_l2"
                ],
                "interface_h_sampled_proxy_role": "diagnostic_only",
                "exact_traction_hcurl_dual_relative_max": float(
                    config.get(
                        "max_exact_traction_hcurl_dual_relative",
                        1.0e-8,
                    )
                ),
            },
            evidence_root + "/records/hybrid_h{5,3}_m160.json",
        )
    )

    schur_observed: dict[str, Any] = {}
    schur_ok = True
    for level in ("h5", "h3"):
        comparison = main_records[(level, mode_counts[-1])].get(
            "modal_schur_comparison", {}
        )
        residuals = comparison.get("residuals", {})
        differences = comparison.get("augmented_vs_schur", {})
        rta_delta = differences.get("RTA_delta", {})
        level_ok = (
            comparison.get("status") == "pass"
            and comparison.get("modal_schur_shape")
            == [2 * mode_counts[-1], 2 * mode_counts[-1]]
            and comparison.get("dense_interface_square_formed") is False
            and comparison.get("full_field_or_mode_gathered") is False
            and _all_true(comparison.get("gates", {}))
            and all(
                _finite_le(value, config["max_true_relative_residual"])
                for value in residuals.values()
            )
            and all(
                _finite_le(differences.get(key), config["max_true_relative_residual"])
                for key in (
                    "modal_coefficients_relative_error",
                    "bottom_solution_relative_error",
                    "top_solution_relative_error",
                )
            )
            and all(_finite_le(value, 1.0e-10) for value in rta_delta.values())
        )
        schur_ok = schur_ok and level_ok
        schur_observed[level] = {
            "shape": comparison.get("modal_schur_shape"),
            "residuals": residuals,
            "augmented_vs_schur": differences,
            "dense_interface_square_formed": comparison.get(
                "dense_interface_square_formed"
            ),
            "full_field_or_mode_gathered": comparison.get(
                "full_field_or_mode_gathered"
            ),
        }
    gates.append(
        gate_factory(
            "task032_final_modal_schur_equivalence",
            schur_ok,
            schur_observed,
            {
                "relative_error_max": config["max_true_relative_residual"],
                "rta_absolute_delta_max": 1.0e-10,
                "dense_interface_square_formed": False,
                "full_field_or_mode_gathered": False,
            },
            evidence_root + "/records/hybrid_h{5,3}_m160.json",
        )
    )

    memory_records: dict[tuple[str, str], dict[str, Any]] = {}
    memory_observed: dict[str, Any] = {}
    memory_ok = True
    memory_names = (
        ("augmented", "augmented"),
        ("modal-schur-fast", "schur_fast"),
        ("modal-schur-memory-minimal", "schur_minimal"),
    )
    for level, h_nm in (("h5", 5.0), ("h3", 3.0)):
        for solver_path, suffix in memory_names:
            name = f"memory_{level}_{suffix}.json"
            record = _load(records / name)
            memory_records[(level, solver_path)] = record
            source = record.get("source", {}) or {}
            ledger = record.get("object_payload_ledger", {}) or {}
            inventory = ledger.get("local_or_augmented_factor_inventory", {}) or {}
            peak = record.get("memory", {}).get("max_simultaneous_worker_rss_gib")
            cgroup = record.get("memory", {}).get("max_container_cgroup_current_gib")
            source_sha = source.get("commit_sha")
            record_ok = (
                record.get("schema_version") == 1
                and record.get("solver_path") == solver_path
                and float(record.get("h_nm", float("nan"))) == h_nm
                and record.get("requested_modes_per_direction") == mode_counts[-1]
                and record.get("mpi_size") == config["required_mpi_size"]
                and record.get("return_code") == 0
                and record.get("numeric_pass") is True
                and record.get("no_swap") is True
                and record.get("warning_triggered") is False
                and record.get("terminated_for_memory") is False
                and isinstance(source_sha, str)
                and re.fullmatch(r"[0-9a-f]{40}", source_sha) is not None
                and source_sha == config["required_memory_commit"]
                and source.get("verified_clean_sha") == source_sha
                and source.get("git_dirty") is False
                and source.get("tracked_source_dirty") is False
                and source.get("container_digest")
                == config["required_container_digest"]
                and source.get("mpi_size") == config["required_mpi_size"]
                and source.get("scalar_dtype") == config["required_dtype"]
                and float(peak or 0.0) > 0.0
                and float(cgroup or 0.0) > 0.0
                and ledger.get("dense_interface_square_formed") is False
                and ledger.get("storage_complexity_contract")
                == "O(N_interface*M)+O(M^2)"
                and bool(inventory)
                and all((item or {}).get("available") is True for item in inventory.values())
            )
            memory_ok = memory_ok and record_ok
            memory_observed[f"{level}_{suffix}"] = {
                "source_commit": source_sha,
                "container_digest": source.get("container_digest"),
                "worker_rss_gib": peak,
                "cgroup_current_gib": cgroup,
                "peak_stage": record.get("memory", {}).get(
                    "max_simultaneous_worker_rss_stage"
                ),
                "numeric_pass": record.get("numeric_pass"),
                "no_swap": record.get("no_swap"),
                "dense_interface_square_formed": ledger.get(
                    "dense_interface_square_formed"
                ),
            }
    h3_augmented = float(
        memory_records[("h3", "augmented")]["memory"][
            "max_simultaneous_worker_rss_gib"
        ]
    )
    h3_fast = float(
        memory_records[("h3", "modal-schur-fast")]["memory"][
            "max_simultaneous_worker_rss_gib"
        ]
    )
    h3_minimal = float(
        memory_records[("h3", "modal-schur-memory-minimal")]["memory"][
            "max_simultaneous_worker_rss_gib"
        ]
    )
    h3_reduction = (h3_augmented - h3_minimal) / h3_augmented
    memory_ok = (
        memory_ok
        and h3_minimal <= float(config["h3_memory_minimal_max_gib"])
        and h3_reduction
        >= float(config["required_h3_memory_reduction_fraction"])
        and h3_fast > h3_augmented
    )
    memory_observed["h3_comparison"] = {
        "augmented_gib": h3_augmented,
        "schur_fast_gib": h3_fast,
        "schur_memory_minimal_gib": h3_minimal,
        "minimal_reduction_fraction": h3_reduction,
        "fast_negative_result_retained": h3_fast > h3_augmented,
    }
    gates.append(
        gate_factory(
            "task032_final_memory_paths",
            memory_ok,
            memory_observed,
            {
                "six_clean_zero_swap_numeric_runs": True,
                "h3_memory_minimal_max_gib": config[
                    "h3_memory_minimal_max_gib"
                ],
                "h3_minimal_reduction_fraction_min": config[
                    "required_h3_memory_reduction_fraction"
                ],
                "h3_fast_negative_result_retained": True,
            },
            evidence_root + "/records/memory_h{5,3}_{augmented,schur_fast,schur_minimal}.json",
        )
    )

    prediction = _load(records / "h2_prediction.json")
    predictions = prediction.get("predictions", [])
    selected_path = prediction.get("selected_solver_path")
    selected = next(
        (item for item in predictions if item.get("solver_path") == selected_path),
        {},
    )
    methods = selected.get("h2_predictions", {})
    prediction_inputs_match = all(
        float(item.get("observations", {}).get(f"{level}_worker_rss_gib", -1.0))
        == float(
            memory_records[(level, item.get("solver_path"))]["memory"][
                "max_simultaneous_worker_rss_gib"
            ]
        )
        and item.get("observations", {}).get(f"{level}_no_swap")
        is memory_records[(level, item.get("solver_path"))].get("no_swap")
        and item.get("observations", {}).get(f"{level}_numeric_pass")
        is memory_records[(level, item.get("solver_path"))].get("numeric_pass")
        for item in predictions
        for level in ("h5", "h3")
    )
    h2_ok = (
        prediction.get("status") == "h2_remains_locked"
        and prediction.get("h2_unlock") is False
        and selected_path == "modal-schur-memory-minimal"
        and len(predictions) == 3
        and prediction_inputs_match
        and all(
            item.get("observations", {}).get(key) is True
            for item in predictions
            for key in (
                "h5_no_swap",
                "h3_no_swap",
                "h5_numeric_pass",
                "h3_numeric_pass",
            )
        )
        and len(methods) >= 2
        and all(
            float(method.get("center_gib", 0.0))
            > float(config["h2_center_limit_gib"])
            and float(method.get("conservative_upper_gib", 0.0))
            > float(config["h2_upper_limit_gib"])
            for method in methods.values()
        )
        and selected.get("two_method_center_le_4_gib") is False
        and selected.get("two_method_upper_le_5_gib") is False
    )
    gates.append(
        gate_factory(
            "task032_final_h2_locked_by_mandatory_prediction_gate",
            h2_ok,
            {
                "status": prediction.get("status"),
                "selected_solver_path": selected_path,
                "methods": methods,
                "decision": prediction.get("decision"),
            },
            {
                "h2_unlock": False,
                "center_limit_gib": config["h2_center_limit_gib"],
                "upper_limit_gib": config["h2_upper_limit_gib"],
                "independent_prediction_methods": 2,
            },
            evidence_root + "/records/h2_prediction.json",
        )
    )

    smoke = _load(records / "parameter_smoke.json")
    smoke_runs = smoke.get("runs", [])
    scope = smoke.get("scope", {})
    smoke_source = smoke.get("source", {})
    smoke_ok = (
        smoke.get("status") == "parameter_smoke_pass"
        and smoke.get("run_count") == config["required_parameter_smoke_count"]
        and smoke.get("pass_count") == config["required_parameter_smoke_count"]
        and len(smoke_runs) == config["required_parameter_smoke_count"]
        and smoke_source.get("commit_sha") == config["required_commit"]
        and smoke_source.get("verified_clean_sha") == config["required_commit"]
        and smoke_source.get("tracked_source_dirty") is False
        and smoke_source.get("git_dirty") is False
        and smoke_source.get("container_digest")
        == config["required_container_digest"]
        and smoke_source.get("mpi_size") == config["required_mpi_size"]
        and smoke_source.get("scalar_dtype") == config["required_dtype"]
        and smoke_source.get("full_field_or_mode_vector_gather") is False
        and smoke_source.get("run_metadata_count")
        == config["required_parameter_smoke_count"]
        and smoke_source.get("all_run_metadata_consistent") is True
        and scope.get("h5_angles_deg") == list(range(1, 11))
        and scope.get("h3_angles_deg") == [1, 3, 5, 7, 10]
        and scope.get("polarizations") == ["s", "p"]
        and all(
            run.get("algebraic_smoke_pass") is True
            and _all_true(run.get("gates", {}))
            and all(
                math.isfinite(float(run.get(key, float("nan"))))
                for key in ("R_total", "T_total", "A_balance")
            )
            for run in smoke_runs
        )
    )
    gates.append(
        gate_factory(
            "task032_final_parameter_entry_smoke",
            smoke_ok,
            {
                "status": smoke.get("status"),
                "run_count": smoke.get("run_count"),
                "pass_count": smoke.get("pass_count"),
                "scope": scope,
                "source": smoke_source,
            },
            {
                "run_count": config["required_parameter_smoke_count"],
                "h5_angles_deg": list(range(1, 11)),
                "h3_angles_deg": [1, 3, 5, 7, 10],
                "polarizations": ["s", "p"],
                "claim": "parameter entry and algebra smoke only",
            },
            evidence_root + "/records/parameter_smoke.json",
        )
    )

    gates.append(
        gate_factory(
            "task032_final_ordinary_default_unchanged",
            config.get("ordinary_default_changed") is False,
            config.get("ordinary_default_changed"),
            False,
            evidence_root + "/expected/gates.json",
        )
    )
    return gates
