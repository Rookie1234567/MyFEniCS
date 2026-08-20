"""Read-only checker for compact dynamic DtN action facts."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


T3_SCHEMA = "task038.full3d.iterative.t3.action-record.v1"
T3_CHECK_SCHEMA = "task038.full3d.iterative.t3.action-check.v1"
T3_PROFILE = "full3d_scalable_v1"
T3_FORMAL_CASE = "p6-h10"
T3_TEMPLATE_RELATIVE_PATH = "input/templates/full3d_iterative_example.dat"
T3_EXPECTED_MODE_COUNT = 80
T3_EXPECTED_INPUT_BYTES = 2119
T3_EXPECTED_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
T3_EXPECTED_RESOLVED_CONFIG_BYTES = 4076
T3_EXPECTED_RESOLVED_CONFIG_SHA256 = "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
T3_EXPECTED_PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
T3_ACTION_LIMIT = 1.0e-11
T3_RECOVERY_LIMIT = 1.0e-11
T3_REPEAT_LIMIT = 1.0e-13
T3_APPLY_COUNT = 12
T3_CANONICAL_LIMIT = 1.0e-12
T3_RSS_STABILITY_LIMIT_BYTES = 64 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _safe_path(raw_dir: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("artifact relative path is invalid")
    path = (raw_dir / relative).resolve()
    path.relative_to(raw_dir.resolve())
    return path


def _artifact_errors(raw_dir: Path, descriptor: Mapping[str, Any]) -> list[str]:
    relative = descriptor.get("relative_path")
    try:
        path = _safe_path(raw_dir, relative)
    except ValueError as exc:
        return [str(exc)]
    if not path.is_file():
        return [f"artifact is missing: {relative}"]
    errors = []
    if descriptor.get("sha256") != _sha256(path):
        errors.append(f"artifact SHA mismatch: {relative}")
    if descriptor.get("bytes") != path.stat().st_size:
        errors.append(f"artifact byte-size mismatch: {relative}")
    if descriptor.get("dtype") != "complex128":
        errors.append(f"artifact dtype mismatch: {relative}")
    shape = descriptor.get("shape")
    if (
        not isinstance(shape, list)
        or len(shape) != 1
        or not isinstance(shape[0], int)
        or isinstance(shape[0], bool)
        or shape[0] <= 0
    ):
        errors.append(f"artifact shape mismatch: {relative}")
    elif descriptor.get("bytes") != int(shape[0]) * 16:
        errors.append(f"artifact declared shape/bytes mismatch: {relative}")
    return errors


def _canonical_manifest_path(raw_dir: Path, descriptor: Mapping[str, Any]) -> Path:
    return _safe_path(raw_dir, descriptor.get("canonical_manifest_relative_path"))


def _canonical_manifest_errors(
    raw_dir: Path, descriptor: Mapping[str, Any]
) -> list[str]:
    from benchmarks.canonical_vector_artifacts import read_canonical_manifest

    try:
        path = _canonical_manifest_path(raw_dir, descriptor)
        if not path.is_file():
            return ["canonical manifest is missing"]
        digest = _sha256(path)
        errors = []
        if descriptor.get("canonical_manifest_bytes") != path.stat().st_size:
            errors.append("canonical manifest byte-size mismatch")
        if descriptor.get("canonical_manifest_sha256") != digest:
            errors.append("canonical manifest SHA mismatch")
        manifest = read_canonical_manifest(path, digest)
        if descriptor.get("canonical_packet_count") != manifest.get(
            "global_summed_packet_count"
        ):
            errors.append("canonical packet count mismatch")
        return errors
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [f"canonical manifest is invalid: {exc}"]


def _mode_manifest_errors(
    raw_dir: Path,
    descriptor: Mapping[str, Any],
    model: Mapping[str, Any],
    audit: Mapping[str, Any],
) -> tuple[list[str], dict[str, int]]:
    try:
        path = _safe_path(raw_dir, descriptor.get("relative_path"))
    except ValueError as exc:
        return [str(exc)], {}
    if not path.is_file():
        return ["ordered mode manifest is missing"], {}
    errors: list[str] = []
    digest = _sha256(path)
    if descriptor.get("bytes") != path.stat().st_size:
        errors.append("ordered mode manifest byte-size mismatch")
    if descriptor.get("sha256") != digest:
        errors.append("ordered mode manifest SHA mismatch")
    if digest != model.get("mode_manifest_sha256"):
        errors.append("ordered mode manifest does not match model SHA")
    if digest != audit.get("mode_manifest_sha256"):
        errors.append("ordered mode manifest does not match carrier audit SHA")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return errors + [f"ordered mode manifest is unreadable: {exc}"], {}
    modes = payload.get("modes") if isinstance(payload, Mapping) else None
    if not isinstance(payload, Mapping) or payload.get("schema") != "fullspace-dtn.mode-manifest.v1":
        errors.append("ordered mode manifest schema mismatch")
    if not isinstance(payload, Mapping) or payload.get("profile") != T3_PROFILE:
        errors.append("ordered mode manifest profile mismatch")
    if not isinstance(modes, list) or payload.get("mode_count") != len(modes):
        errors.append("ordered mode manifest count does not close")
        return errors, {}
    if payload.get("mode_count") != model.get("mode_count"):
        errors.append("ordered mode manifest count differs from model")
    counts = {name: 0 for name in ("propagating", "near-cutoff", "evanescent")}
    for index, mode in enumerate(modes):
        if not isinstance(mode, Mapping) or mode.get("mode_index") != index:
            errors.append("ordered mode manifest indices are not contiguous")
            continue
        classification = mode.get("classification")
        if classification not in counts:
            errors.append("ordered mode manifest classification is invalid")
        else:
            counts[classification] += 1
    if counts != dict(model.get("mode_classification_counts", {})):
        errors.append("mode classification counts do not match manifest")
    if counts != dict(audit.get("mode_classification_counts", {})):
        errors.append("mode classification counts do not match carrier audit")
    return errors, counts


def _evidence_artifact_errors(
    raw_dir: Path, descriptor: Mapping[str, Any], expected_kind: str
) -> list[str]:
    relative = descriptor.get("relative_path")
    try:
        path = _safe_path(raw_dir, relative)
    except ValueError as exc:
        return [str(exc)]
    errors = []
    if descriptor.get("kind") != expected_kind:
        errors.append(f"benchmark artifact kind mismatch: {expected_kind}")
    if not path.is_file():
        return errors + [f"benchmark artifact is missing: {relative}"]
    if descriptor.get("bytes") != path.stat().st_size:
        errors.append(f"benchmark artifact byte-size mismatch: {relative}")
    if descriptor.get("sha256") != _sha256(path):
        errors.append(f"benchmark artifact SHA mismatch: {relative}")
    return errors


def _benchmark_identity_errors(record: Mapping[str, Any], raw_dir: Path) -> list[str]:
    """Verify the frozen adapter-derived p6/h10 identity without defaults."""

    expected = {
        "case": T3_FORMAL_CASE,
        "model_id": "euv_grazing1_phi0",
        "run_id": "euv_grazing1_phi0_full3d_iterative_mpi1",
        "comparison_group": "euv_grazing1_phi0",
        "method": "full3d_iterative",
        "profile": T3_PROFILE,
        "preconditioner": "full3d_scalable_v1",
        "wavelength_nm": 13.5,
        "nedelec_degree": 6,
        "mesh_target_nm": 10.0,
        "boundary_model": "dtn_port",
        "vertical_boundary": "dtn_port",
        "dtn_order_policy": "auto_propagating",
        "dtn_assembly": "auxiliary",
        "expected_mode_count": T3_EXPECTED_MODE_COUNT,
        "discovered_mode_count": T3_EXPECTED_MODE_COUNT,
        "input_adapter": "src.io.load_and_resolve",
        "resolved_config_encoder": "src.io.resolved_config.resolved_config_bytes",
        "input_template_relative_path": T3_TEMPLATE_RELATIVE_PATH,
        "input_template_bytes": T3_EXPECTED_INPUT_BYTES,
        "input_template_sha256": T3_EXPECTED_INPUT_SHA256,
        "physical_model_sha256": T3_EXPECTED_PHYSICAL_MODEL_SHA256,
        "resolved_config_bytes": T3_EXPECTED_RESOLVED_CONFIG_BYTES,
        "resolved_config_sha256": T3_EXPECTED_RESOLVED_CONFIG_SHA256,
    }
    errors: list[str] = []
    benchmark = record.get("benchmark")
    if not isinstance(benchmark, Mapping):
        return ["benchmark identity is missing"]
    for key, value in expected.items():
        if key not in benchmark:
            errors.append(f"benchmark identity field is missing: {key}")
        elif benchmark[key] != value:
            errors.append(f"benchmark identity mismatch: {key}")
    if record.get("case") != T3_FORMAL_CASE:
        errors.append("record case is not frozen p6-h10")
    if record.get("profile") != T3_PROFILE:
        errors.append("record profile is not frozen full3d_scalable_v1")
    if record.get("resolved_config_sha256") != T3_EXPECTED_RESOLVED_CONFIG_SHA256:
        errors.append("record resolved-config SHA is not frozen")
    if record.get("resolved_config_bytes") != T3_EXPECTED_RESOLVED_CONFIG_BYTES:
        errors.append("record resolved-config byte count is not frozen")
    source = record.get("source")
    if not isinstance(source, Mapping):
        errors.append("source benchmark identity is missing")
    else:
        for key in (
            "input_template_relative_path",
            "input_template_bytes",
            "input_template_sha256",
            "physical_model_sha256",
            "resolved_config_bytes",
            "resolved_config_sha256",
        ):
            if key not in source:
                errors.append(f"source benchmark identity field is missing: {key}")
            elif source[key] != expected[key]:
                errors.append(f"source benchmark identity mismatch: {key}")

    artifacts = record.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return errors + ["benchmark artifacts are missing"]
    input_descriptor = artifacts.get("input_template")
    resolved_descriptor = artifacts.get("resolved_config")
    if not isinstance(input_descriptor, Mapping):
        errors.append("input-template artifact descriptor is missing")
    else:
        errors.extend(_evidence_artifact_errors(raw_dir, input_descriptor, "input_template"))
        if input_descriptor.get("relative_path") != "benchmark_input/full3d_iterative_example.dat":
            errors.append("input-template artifact path is not frozen")
        if input_descriptor.get("bytes") != T3_EXPECTED_INPUT_BYTES:
            errors.append("input-template artifact bytes are not frozen")
        if input_descriptor.get("sha256") != T3_EXPECTED_INPUT_SHA256:
            errors.append("input-template artifact SHA is not frozen")
    if not isinstance(resolved_descriptor, Mapping):
        errors.append("resolved-config artifact descriptor is missing")
        return errors
    errors.extend(_evidence_artifact_errors(raw_dir, resolved_descriptor, "resolved_config"))
    if resolved_descriptor.get("relative_path") != "benchmark_input/resolved_config.json":
        errors.append("resolved-config artifact path is not frozen")
    if resolved_descriptor.get("bytes") != T3_EXPECTED_RESOLVED_CONFIG_BYTES:
        errors.append("resolved-config artifact bytes are not frozen")
    if resolved_descriptor.get("sha256") != T3_EXPECTED_RESOLVED_CONFIG_SHA256:
        errors.append("resolved-config artifact SHA is not frozen")
    try:
        resolved_path = _safe_path(raw_dir, resolved_descriptor.get("relative_path"))
        resolved_payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return errors + [f"resolved-config artifact is not valid JSON: {exc}"]

    def require(mapping: Any, key: str, value: Any, label: str) -> None:
        if not isinstance(mapping, Mapping) or key not in mapping:
            errors.append(f"resolved-config field is missing: {label}")
        elif mapping[key] != value:
            errors.append(f"resolved-config field mismatch: {label}")

    require(resolved_payload, "model_id", expected["model_id"], "model_id")
    require(resolved_payload, "run_id", expected["run_id"], "run_id")
    require(resolved_payload, "comparison_group", expected["comparison_group"], "comparison_group")
    require(resolved_payload.get("method"), "kind", expected["method"], "method.kind")
    require(resolved_payload.get("incidence"), "wavelength_nm", expected["wavelength_nm"], "incidence.wavelength_nm")
    require(resolved_payload.get("discretization"), "nedelec_degree", expected["nedelec_degree"], "discretization.nedelec_degree")
    require(resolved_payload.get("discretization"), "mesh_target_nm", expected["mesh_target_nm"], "discretization.mesh_target_nm")
    require(resolved_payload.get("boundary"), "vertical_boundary", expected["vertical_boundary"], "boundary.vertical_boundary")
    require(resolved_payload.get("boundary"), "dtn_order_policy", expected["dtn_order_policy"], "boundary.dtn_order_policy")
    require(resolved_payload.get("boundary"), "dtn_assembly", expected["dtn_assembly"], "boundary.dtn_assembly")
    require(resolved_payload.get("solver"), "preconditioner", expected["preconditioner"], "solver.preconditioner")
    provenance = resolved_payload.get("provenance")
    require(provenance, "input_sha256", expected["input_template_sha256"], "provenance.input_sha256")
    require(provenance, "physical_model_sha256", expected["physical_model_sha256"], "provenance.physical_model_sha256")
    return errors


def check_t3_record(path: str | Path) -> dict[str, Any]:
    """Derive T3 gates from raw worker facts without importing execution code."""

    record_path = Path(path)
    problems: list[str] = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "schema": T3_CHECK_SCHEMA,
            "passed": False,
            "classification": "T3_EXECUTION_OR_EVIDENCE_FAIL",
            "problems": [f"record is unreadable: {exc}"],
        }
    if not isinstance(record, Mapping):
        return {
            "schema": T3_CHECK_SCHEMA,
            "passed": False,
            "classification": "T3_EXECUTION_OR_EVIDENCE_FAIL",
            "problems": ["record must be a JSON object"],
        }

    required = (
        "schema",
        "profile",
        "case",
        "resolved_config_sha256",
        "resolved_config_bytes",
        "benchmark",
        "source",
        "mpi",
        "model",
        "artifacts",
        "observations",
        "carrier_audit",
        "resource",
    )
    problems.extend(f"missing required field: {key}" for key in required if key not in record)
    problems.extend(
        message
        for ok, message in (
            (record.get("schema") == T3_SCHEMA, "record schema mismatch"),
            (record.get("profile") == T3_PROFILE, "profile mismatch"),
            (isinstance(record.get("case"), str), "case identity is missing"),
        )
        if not ok
    )
    source = record.get("source")
    if not isinstance(source, Mapping):
        problems.append("source identity is missing")
    else:
        if source.get("commit_sha_start") != source.get("commit_sha_end"):
            problems.append("source SHA changed")
        if source.get("expected_sha") != source.get("commit_sha_start"):
            problems.append("source SHA does not match expected SHA")
        if source.get("tracked_status_start") or source.get("tracked_status_end"):
            problems.append("source worktree was dirty")

    mpi = record.get("mpi")
    if not isinstance(mpi, Mapping) or mpi.get("size") not in {1, 2}:
        problems.append("MPI size must be one or two")
    model = record.get("model")
    if not isinstance(model, Mapping):
        problems.append("model identity is missing")
    else:
        if not isinstance(model.get("mode_count"), int) or model["mode_count"] <= 0:
            problems.append("dynamic mode count is invalid")
        manifest_sha = model.get("mode_manifest_sha256")
        if not isinstance(manifest_sha, str) or len(manifest_sha) != 64:
            problems.append("mode manifest hash is invalid")
        classes = model.get("mode_classification_counts")
        if not isinstance(classes, Mapping) or set(classes) != {
            "propagating",
            "near-cutoff",
            "evanescent",
        }:
            problems.append("mode classification counts are incomplete")
        elif not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in classes.values()
        ) or sum(classes.values()) != model["mode_count"]:
            problems.append("mode classification counts do not close")

    audit = record.get("carrier_audit")
    if not isinstance(audit, Mapping):
        problems.append("carrier audit is missing")
        audit = {}
    raw_dir_value = record.get("raw_dir")
    raw_dir = Path(raw_dir_value) if isinstance(raw_dir_value, str) else record_path.parent
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, Mapping):
        problems.append("artifact descriptors are missing")
    else:
        for name in ("source", "action", "reference_action", "recovery"):
            descriptor = artifacts.get(name)
            if not isinstance(descriptor, Mapping):
                problems.append(f"artifact descriptor is missing: {name}")
            else:
                problems.extend(_artifact_errors(raw_dir, descriptor))
                if name in {"source", "action", "reference_action"}:
                    problems.extend(_canonical_manifest_errors(raw_dir, descriptor))
        mode_descriptor = artifacts.get("mode_manifest")
        if not isinstance(mode_descriptor, Mapping):
            problems.append("artifact descriptor is missing: mode_manifest")
        elif isinstance(model, Mapping):
            manifest_problems, _manifest_counts = _mode_manifest_errors(
                raw_dir, mode_descriptor, model, audit
            )
            problems.extend(manifest_problems)
    problems.extend(_benchmark_identity_errors(record, raw_dir))

    observations = record.get("observations")
    if not isinstance(observations, Mapping):
        problems.append("observations are missing")
        observations = {}
    action_error = observations.get("action_relative_error")
    recovery_error = observations.get("recovery_relative_error")
    repeats = observations.get("repeat_relative_differences")
    checks = {
        "action_identity": _finite_nonnegative(action_error)
        and float(action_error) <= T3_ACTION_LIMIT,
        "recovery_identity": _finite_nonnegative(recovery_error)
        and float(recovery_error) <= T3_RECOVERY_LIMIT,
        "repeat_count": observations.get("repeat_count") == T3_APPLY_COUNT
        and isinstance(repeats, list)
        and len(repeats) == T3_APPLY_COUNT - 1,
        "repeat_determinism": isinstance(repeats, list)
        and all(_finite_nonnegative(value) and value <= T3_REPEAT_LIMIT for value in repeats),
        "apply_telemetry_count": all(
            isinstance(observations.get(name), list)
            and len(observations[name]) == T3_APPLY_COUNT
            and all(_finite_nonnegative(value) for value in observations[name])
            for name in ("elapsed_seconds", "rss_bytes", "swap_used_bytes")
        ),
        "swap_zero": isinstance(observations.get("swap_used_bytes"), list)
        and all(value == 0 for value in observations["swap_used_bytes"]),
    }
    rss = observations.get("rss_bytes")
    warm_span = None
    if (
        isinstance(rss, list)
        and len(rss) == T3_APPLY_COUNT
        and all(_finite_nonnegative(value) for value in rss[4:])
    ):
        warm_span = max(rss[4:]) - min(rss[4:])
        checks["warm_rss_stability"] = warm_span <= T3_RSS_STABILITY_LIMIT_BYTES
    else:
        checks["warm_rss_stability"] = False

    resource = record.get("resource")
    if not isinstance(resource, Mapping):
        problems.append("resource evidence is missing")
        resource = {}
    mode_count = audit.get("mode_count")
    batch_size = audit.get("batch_size")
    batch_count = audit.get("batch_count")
    apply_count = audit.get("apply_count")
    checks.update(
        {
            "apply_count": apply_count == T3_APPLY_COUNT,
            "batch_closure": (
                isinstance(mode_count, int)
                and isinstance(batch_size, int)
                and isinstance(batch_count, int)
                and batch_size > 0
                and batch_count == (mode_count + batch_size - 1) // batch_size
            ),
            "fixed_production_batch": batch_size == 8,
            "allreduce_closure": (
                isinstance(batch_count, int)
                and audit.get("apply_modal_allreduce_count")
                == T3_APPLY_COUNT * batch_count
                and audit.get("recovery_modal_allreduce_count") == batch_count
                and audit.get("modal_allreduce_count")
                == audit.get("apply_modal_allreduce_count", -1)
                + audit.get("recovery_modal_allreduce_count", -1)
                and audit.get("modal_allreduce_count_per_apply") == batch_count
            ),
            "explicit_h_normalization": (
                audit.get("normalization")
                == "explicit_diagonal_projection_denominator_H"
                and audit.get("normalization_nonidentity") is True
                and _finite_nonnegative(audit.get("normalization_h_min"))
                and _finite_nonnegative(audit.get("normalization_h_max"))
                and float(audit.get("normalization_h_min")) > 0.0
                and float(audit.get("normalization_h_max"))
                >= float(audit.get("normalization_h_min"))
            ),
            "retained_numeric_bytes_reported": all(
                _finite_nonnegative(audit.get(name))
                for name in (
                    "retained_numeric_bytes_local",
                    "retained_numeric_bytes_global_sum",
                    "retained_numeric_bytes_global_max",
                )
            ),
            "bounded_work_reported": all(
                _finite_nonnegative(audit.get(name))
                for name in (
                    "bounded_work_bytes_local",
                    "bounded_work_bytes_global_sum",
                    "bounded_work_bytes_global_max",
                    "recovery_output_bytes",
                )
            ),
            "slave_functional_closure": (
                isinstance(audit.get("slave_rows_local"), int)
                and audit.get("slave_rows_local") >= 0
                and audit.get("slave_functional_rows_local") == 0
                and audit.get("slave_functional_rows_global") == 0
            ),
        }
    )
    checks.update(
        {
            "no_materialization": (
                audit.get("matrix_type") == "python"
                and audit.get("numeric_allgather") is False
                and audit.get("explicit_c_matrix_count") == 0
                and audit.get("explicit_d_matrix_count") == 0
                and audit.get("global_aij_materialized") is False
                and audit.get("global_schur_materialized") is False
                and audit.get("trace_matrix_materialized") is False
                and audit.get("ksp_created") is False
                and audit.get("pde_solved") is False
            ),
            "bounded_work_is_reported": (
                _finite_nonnegative(audit.get("bounded_work_bytes_local"))
                and audit.get("bounded_work_scales_with") == "fixed_modal_batch_size"
            ),
            "process_tree_not_overclaimed": resource.get("process_tree_evidence")
            == "not_measured_t3",
        }
    )
    failed_checks = [name for name, passed in checks.items() if not passed]
    problems.extend(f"failed gate: {name}" for name in failed_checks)
    passed = not problems
    return {
        "schema": T3_CHECK_SCHEMA,
        "record": str(record_path),
        "passed": passed,
        "classification": "T3_PASS" if passed else "T3_NUMERIC_OR_EVIDENCE_FAIL",
        "checks": checks,
        "problems": problems,
        "derived": {
            "mode_count": model.get("mode_count") if isinstance(model, Mapping) else None,
            "mode_manifest_sha256": model.get("mode_manifest_sha256")
            if isinstance(model, Mapping)
            else None,
            "warm_rss_span_bytes": warm_span,
            "warm_rss_limit_bytes": T3_RSS_STABILITY_LIMIT_BYTES,
        },
    }


def check_t3_aggregate(
    mpi1_record_path: str | Path,
    mpi2_record_path: str | Path,
) -> dict[str, Any]:
    """Check MPI peers through physical packets and ordered modal recovery."""

    paths = (Path(mpi1_record_path), Path(mpi2_record_path))
    results = tuple(check_t3_record(path) for path in paths)
    problems = [
        problem
        for result in results
        for problem in result.get("problems", ())
    ]
    payloads = []
    for path in paths:
        try:
            payloads.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            payloads.append(None)
    identities_match = False
    mode_manifest_identity = False
    mpi_pair = False
    if all(isinstance(payload, Mapping) for payload in payloads):
        mpi_values = [payload.get("mpi") for payload in payloads]
        model_values = [payload.get("model") for payload in payloads]
        benchmark_values = [payload.get("benchmark") for payload in payloads]
        mpi_pair = (
            all(isinstance(value, Mapping) for value in mpi_values)
            and set(value.get("size") for value in mpi_values) == {1, 2}
        )
        identities_match = (
            all(isinstance(value, Mapping) for value in model_values)
            and all(isinstance(value, Mapping) for value in benchmark_values)
            and len(
                {
                    (
                        payload.get("case"),
                        payload.get("resolved_config_sha256"),
                        model.get("mode_manifest_sha256"),
                        benchmark.get("resolved_config_sha256"),
                        benchmark.get("discovered_mode_count"),
                    )
                    for payload, model, benchmark in zip(
                        payloads, model_values, benchmark_values, strict=True
                    )
                }
            )
            == 1
        )
        artifact_values = [payload.get("artifacts") for payload in payloads]
        mode_descriptors = [
            value.get("mode_manifest") if isinstance(value, Mapping) else None
            for value in artifact_values
        ]
        if all(isinstance(value, Mapping) for value in mode_descriptors) and all(
            isinstance(value, Mapping) for value in model_values
        ):
            mode_manifest_identity = (
                mode_descriptors[0].get("sha256")
                == mode_descriptors[1].get("sha256")
                == model_values[0].get("mode_manifest_sha256")
                == model_values[1].get("mode_manifest_sha256")
            )
    canonical_comparisons: dict[str, Any] = {}
    recovery_relative = None
    if all(isinstance(payload, Mapping) for payload in payloads):
        from benchmarks.canonical_vector_artifacts import compare_canonical_manifests

        for name in ("source", "action", "reference_action"):
            try:
                left_descriptor = payloads[0]["artifacts"][name]
                right_descriptor = payloads[1]["artifacts"][name]
                left_raw = Path(payloads[0]["raw_dir"])
                right_raw = Path(payloads[1]["raw_dir"])
                canonical_comparisons[name] = compare_canonical_manifests(
                    _canonical_manifest_path(left_raw, left_descriptor),
                    _canonical_manifest_path(right_raw, right_descriptor),
                    left_sha256=left_descriptor["canonical_manifest_sha256"],
                    right_sha256=right_descriptor["canonical_manifest_sha256"],
                    relative_tolerance=T3_CANONICAL_LIMIT,
                )
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                canonical_comparisons[name] = {"pass": False, "error": str(exc)}
        try:
            import struct

            left_descriptor = payloads[0]["artifacts"]["recovery"]
            right_descriptor = payloads[1]["artifacts"]["recovery"]
            left_path = _safe_path(Path(payloads[0]["raw_dir"]), left_descriptor["relative_path"])
            right_path = _safe_path(Path(payloads[1]["raw_dir"]), right_descriptor["relative_path"])
            left_bytes = left_path.read_bytes()
            right_bytes = right_path.read_bytes()
            left_shape = left_descriptor["shape"]
            right_shape = right_descriptor["shape"]
            if left_shape != right_shape or len(left_bytes) != len(right_bytes):
                raise ValueError("recovery mode-ordered shapes differ")
            if payloads[0]["model"]["mode_manifest_sha256"] != payloads[1]["model"]["mode_manifest_sha256"]:
                raise ValueError("recovery mode manifest identities differ")
            left_values = [
                complex(*struct.unpack_from("<dd", left_bytes, offset))
                for offset in range(0, len(left_bytes), 16)
            ]
            right_values = [
                complex(*struct.unpack_from("<dd", right_bytes, offset))
                for offset in range(0, len(right_bytes), 16)
            ]
            numerator = math.sqrt(
                sum(abs(left - right) ** 2 for left, right in zip(left_values, right_values, strict=True))
            )
            denominator = max(
                math.sqrt(sum(abs(value) ** 2 for value in right_values)),
                1.0e-300,
            )
            recovery_relative = numerator / denominator
        except (KeyError, OSError, TypeError, ValueError, struct.error, json.JSONDecodeError) as exc:
            recovery_relative = None
            problems.append(f"recovery cross-MPI comparison failed: {exc}")
    canonical_pass = all(
        comparison.get("pass") is True for comparison in canonical_comparisons.values()
    ) and len(canonical_comparisons) == 3
    checks = {
        "both_records_pass": all(result.get("passed") is True for result in results),
        "mpi1_mpi2_pair": mpi_pair,
        "same_physical_identity": identities_match,
        "ordered_mode_manifest_identity": mode_manifest_identity,
        "canonical_source_action_reference_l2": canonical_pass,
        "recovery_mode_ordered_l2": (
            recovery_relative is not None and recovery_relative <= T3_CANONICAL_LIMIT
        ),
    }
    problems.extend(f"failed aggregate gate: {name}" for name, ok in checks.items() if not ok)
    return {
        "schema": T3_CHECK_SCHEMA,
        "aggregate": True,
        "passed": not problems,
        "classification": "T3_PASS" if not problems else "T3_NUMERIC_OR_EVIDENCE_FAIL",
        "checks": checks,
        "problems": problems,
        "records": [result.get("record") for result in results],
        "derived": {
            "canonical_comparisons": canonical_comparisons,
            "recovery_relative_l2": recovery_relative,
        },
    }


def _parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description="check T3 action records")
    parser.add_argument("record", type=Path)
    parser.add_argument("peer", type=Path, nargs="?")
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = (
        check_t3_record(args.record)
        if args.peer is None
        else check_t3_aggregate(args.record, args.peer)
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
