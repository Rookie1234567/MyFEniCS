"""Independent process: recompute saved physics and the G/FE norm identity."""

import json
from pathlib import Path
import sys

import numpy as np

from src.io.neural_wave_campaign import ROOT, digest
from src.io.neural_space_campaign import field_policy, require_oracle_policy
from src.solvers.neural_wave_greedy import atomic_json


def integral_energy(E, curl, weights, ell=5.0):
    return float(
        np.sum(
            weights
            * (np.sum(abs(E) ** 2, axis=-1) + ell**2 * np.sum(abs(curl) ** 2, axis=-1))
        )
    )


def main(directory, design_file=None, oracle_file=None):
    from src.runners.block_wave_worker import saved_checker
    from src.solvers.feinn_native import load_native

    directory = ROOT / Path(directory)
    design = json.loads(
        (ROOT / (design_file or "input/task042extra_feinn_5nm/design_v35.json")).read_text()
    )
    file = directory / "verifier_result.json"
    frozen = json.loads(file.read_text())
    native = ROOT / design["files"]["native"]["path"]
    if digest(native) != design["files"]["native"]["sha256"]:
        raise ValueError("ORIGINAL_NATIVE_HASH_CHANGED")
    result = saved_checker(load_native(native), file, design, lambda *_: None)
    with np.load(
        ROOT / frozen["raw_complete_fields"]["path"], allow_pickle=False
    ) as data:
        w = data["weights"]
        dref = integral_energy(data["REFERENCE_E"], data["REFERENCE_curl"], w)
        oracle = json.loads(
            (
                ROOT
                / (oracle_file or "benchmarks/artifacts/task42extra/v35/v35_labelled_field_oracle/result.json")
            ).read_text()
        )
        identities = {}
        for name, record in oracle["records"].items():
            if "model" not in record:
                continue
            require_oracle_policy(record)
            key = name + "_ORACLE"
            energy = integral_energy(
                data[key + "_E"] - data["REFERENCE_E"],
                data[key + "_curl"] - data["REFERENCE_curl"],
                w,
            )
            pair = abs(energy - record["actual_error_G_energy"]) / max(energy, 1e-300)
            denominator_pair = abs(dref - record["reference_G_energy"]) / dref
            identities[name] = dict(
                error_energy_original_G=record["actual_error_G_energy"],
                error_energy_independent_FE=energy,
                reference_energy_original_G=record["reference_G_energy"],
                reference_energy_independent_FE=dref,
                error_energy_relative_pair=pair,
                reference_energy_relative_pair=denominator_pair,
                epsilon_G_independent=float(np.sqrt(energy / dref)),
                original_ell_nm=5,
                identity_pass=bool(max(pair, denominator_pair) <= 1e-8),
            )
    for name, record in result["records"].items():
        record.update(field_policy(name))
    result.update(
        G_FE_norm_identities=identities,
        oracle_always_diagnostic=True,
        checker_process_separate=True,
        reference_solve_count=0,
        candidate_decision="NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE",
        verifier_result_sha256=digest(file),
    )
    atomic_json(directory / "saved_checker.json", result)
    print(
        json.dumps(
            dict(
                status="SAVED_ARRAY_AUDIT_COMPLETE",
                norm_identities=identities,
                statuses_trusted=False,
                oracle_is_solver=False,
            )
        )
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
