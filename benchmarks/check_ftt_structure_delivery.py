"""Check frozen FTT delivery identities and decisions; never run a model or PDE."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text())


def numerical_decision(record):
    """Recompute all finite ratio/physical gates, including permanent label limits."""
    errors = record["field_errors"]
    required = (
        {
            f"{field}_{kind}"
            for field in ("total", "scattered")
            for kind in ("E", "H_code", "curl")
        }
        | {
            f"selected_{field}_{kind}_{i}"
            for field in ("total", "scattered")
            for kind in ("E", "H_code")
            for i in range(6)
        }
        | {
            f"complex_{kind}_channels"
            for kind in ("total", "scattered", "outgoing", "boundary_outgoing")
        }
    )
    if set(errors) != required:
        raise ValueError("COMPLETE_PHYSICAL_METRIC_COVERAGE_FAILED")
    for ratio in list(errors.values()) + [record["independent_total_native"]]:
        a, d, r = (ratio[k] for k in ("absolute", "denominator", "relative"))
        if not all(math.isfinite(x) for x in (a, d, r)) or a < 0 or d <= 0:
            raise ValueError("INVALID_PHYSICAL_RATIO")
        if not math.isclose(a / d, r, rel_tol=1e-12, abs_tol=1e-16):
            raise ValueError("NUMERATOR_DENOMINATOR_MISMATCH")
    equation = (
        all(
            math.isfinite(record["equation_audit"][k])
            and 0 <= record["equation_audit"][k] <= 1e-6
            for k in ("native_relative", "augmented_relative")
        )
        and record["independent_total_native"]["relative"] <= 1e-6
    )
    fields = all(r["relative"] <= 1e-4 for r in errors.values())
    power = (
        all(
            math.isfinite(x) and 0 <= x <= 1e-5
            for x in [
                *record["power_absolute_differences"].values(),
                record["energy_closure"],
            ]
        )
        and 0 <= record["max_per_mode_power_absolute"] <= 1e-6
    )
    reconstruction = record["reconstruction"]
    model = all(
        0 <= x <= 1e-10
        for x in (
            reconstruction["complete_model_mapping_relative"],
            record["MPC_relative"],
            record["port_recovery_relative"],
        )
    )
    quadrature = all(
        0 <= reconstruction[k] <= 1e-8
        for k in (
            "coefficient_q30_q60_relative",
            "original_action_q30_q60_load_relative",
            "FE_norm_q15_q30_relative",
        )
    )
    gram = record["Gram_integral_pairing"]
    gram_pair = all(
        0 <= gram[k] <= 1e-8
        for k in ("error_energy_pairing_relative", "reference_energy_pairing_relative")
    )
    if not math.isclose(
        math.sqrt(gram["G_error_energy"] / gram["G_reference_energy"]),
        gram["E_G"],
        rel_tol=1e-12,
    ):
        raise ValueError("GRAM_ERROR_DENOMINATOR_MISMATCH")
    expected = dict(
        original_equation_pass=equation,
        field_pass=fields,
        power_pass=power,
        model_rebuild_pass=model,
        quadrature_pass=quadrature,
        m5_full_discrete_numerical_gate=equation
        and fields
        and power
        and model
        and quadrature
        and gram_pair,
    )
    for key, value in expected.items():
        if record[key] is not value:
            raise ValueError("CLAIMED_GATE_DIFFERS_FROM_RAW:" + key)
    labelled = record["reference_used_for_training"]
    if (
        record["features_reference_exposed"] is not labelled
        or record["pde_only_solve"] is not (not labelled)
        or record["production_initialization_allowed"] is not False
        or record["official_candidate_results"] is not False
        or record["pde_only_solver_qualified"]
        is not (expected["m5_full_discrete_numerical_gate"] and not labelled)
    ):
        raise ValueError("LABEL_OR_PRODUCTION_BOUNDARY_FAILED")
    return expected


def check(records):
    index = read(records / "run_index_v39.json")
    verified = set()
    source_pairs = set()
    for row in index["runs"]:
        for binding in row["bindings"]:
            pair = binding["path"], binding["sha256"]
            if pair in verified:
                continue
            path = ROOT / binding["path"]
            if path.stat().st_size != binding["bytes"] or digest(path) != pair[1]:
                raise ValueError("FROZEN_BINDING_FAILED:" + pair[0])
            verified.add(pair)
        for path, sha in row.get("historical_binding_source_files", {}).items():
            pair = row["source_sha"], path
            if pair in source_pairs:
                continue
            raw = subprocess.check_output(
                ["git", "show", f"{pair[0]}:{path}"], cwd=ROOT
            )
            if hashlib.sha256(raw).hexdigest() != sha:
                raise ValueError("HISTORICAL_GIT_SOURCE_FAILED:" + path)
            source_pairs.add(pair)
    fields = read(records / "full_numerical_gates_v39.json")["records"]
    decisions = {name: numerical_decision(row) for name, row in fields.items()}
    if len(decisions) != 8:
        raise ValueError("ACTUAL_AND_PRODUCER_COVERAGE_INCOMPLETE")
    routes = read(records / "resume_and_training_v39.json")["routes"]
    for name, row in routes.items():
        fit = "_fit_" in name
        total = row["cumulative_counts"]
        if (
            total["complete_loss_gradient_calls"] != (500 if fit else 1000)
            or total["Adam_updates"] != (100 if fit else 500)
            or total["LBFGS_outer_steps"] <= 0
            or any(
                row[k] != 0
                for k in ("Gsolve", "global_Gram_factor", "global_Maxwell_factor")
            )
            or row["reference_used_for_training"] is not fit
        ):
            raise ValueError("RESUME_SCHEDULE_OR_FACTOR_BOUNDARY_FAILED")
        for key in total:
            if total[key] != row["inherited_counts"][key] + row["new_counts"][key]:
                raise ValueError("INHERITED_NEW_CUMULATIVE_COUNT_MISMATCH")
    channel_rows = 0
    for fit, stage in (
        (False, "v39_ftt_independent_compare"),
        (True, "v39_ftt_fit_compare"),
    ):
        raw = read(
            ROOT / f"benchmarks/artifacts/task42extra/v39/{stage}/verifier_result.json"
        )
        with (
            records / f"complex_channels_{'fit' if fit else 'native'}_v39.csv"
        ).open() as stream:
            rows = list(csv.DictReader(stream))
        kinds = ("total", "scattered", "outgoing", "boundary_outgoing")
        expected_routes = {"REFERENCE"} | set(raw["reconstruction"])
        if set(raw["physics"]["records"]) != expected_routes:
            raise ValueError("UNEXPECTED_FROZEN_PHYSICS_ROUTES")
        for route in expected_routes:
            route_rows = [r for r in rows if r["route"] == route]
            if len(route_rows) != 40 or {
                int(r["mode_index"]) for r in route_rows
            } != set(range(40)):
                raise ValueError("COMPLETE_CHANNEL_KEY_COVERAGE_FAILED")
            physics = raw["physics"]["records"][route]
            for row in route_rows:
                i = int(row["mode_index"])
                mode = raw["physics"]["original_mode_manifest"]["modes"][i]
                if any(
                    row[k] != str(mode[k]) for k in ("side", "m", "n", "polarization")
                ):
                    raise ValueError("PHYSICAL_MODE_ALIGNMENT_FAILED")
                for kind in kinds:
                    for part in ("real", "imag"):
                        if (
                            float(row[kind + "_" + part])
                            != physics["ordered_complex_" + kind + "_channels"][i][part]
                        ):
                            raise ValueError("COMPLETE_COMPLEX_CHANNEL_ARRAY_FAILED")
                if (
                    float(row["per_mode_power_incident_normalized"])
                    != physics["ordered_per_channel_power"][i]
                ):
                    raise ValueError("PER_MODE_POWER_ARRAY_FAILED")
        if len(rows) != len(expected_routes) * 40:
            raise ValueError("UNEXPECTED_CHANNEL_ROUTES")
        channel_rows += len(rows)
    return dict(
        schema="ftt.structure-delivery-check.v1",
        verified_file_bindings=len(verified),
        verified_historical_source_blobs=len(source_pairs),
        complete_channel_CSV_rows=channel_rows,
        recomputed_actual_and_producer_gates=decisions,
        statuses_trusted=False,
        new_FE_model_forward_training_or_factor_calls=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = check(args.records)
    result["checker_source_sha256"] = digest(Path(__file__))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if not isinstance(v, dict)}))
