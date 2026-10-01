"""Strict opt-in one-run inputs for the frozen full-FE 5 nm experiment."""

import hashlib
import json
from pathlib import Path
import tomllib

from src.io.input_loader import InputError
from src.io.run_specification import RunSpecification
from src.runners.feinn_campaign import STAGES as CAMPAIGN_STAGES, AUTHORITY
from src.runners.feinn_gn_campaign import (
    STAGES as GN_STAGES,
    AUTHORITY as GN_AUTHORITY,
    SUPERVISED as GN_SUPERVISED,
)

from src.runners.feinn_cached_gn_campaign import (
    STAGES as CACHED_STAGES,
    SUPERVISED as CACHED_SUPERVISED,
)

GN_STAGES = GN_STAGES | CACHED_STAGES
GN_SUPERVISED = GN_SUPERVISED | CACHED_SUPERVISED

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "input/task042extra_feinn_5nm/design_v1.json"
STAGES = {
    "v7_p_transfer_checks": ("fe", 1200),
    "v7_p4_reference": ("fe", 3600),
    "v7_p3_p4_compare": ("fe", 1200),
    "v6_operator_readout_checks": ("ml", 600),
    "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT": ("ml", 1800),
    "v6_residual_readout_reconstruct": ("ml", 600),
    "v6_residual_readout_compare_only": ("fe", 600),
    "e1_smoke": ("fe", 1800),
    "e1_fe": ("fe", 3600),
    "e1_grad": ("ml", 7200),
    "FEINN-EUC": ("ml", 10800),
    "FEINN-DUAL": ("ml", 10800),
    "FREE-FE-DUAL": ("ml", 10800),
    "e3_reference": ("fe", 3600),
    "e4_p4": ("fe", 3600),
    "v2_state_diagnostic": ("ml", 1800),
    "v2_scaling_checks": ("ml", 1800),
    "FREE-FE-DUAL-GRAM-DIAG": ("ml", 10800),
    "v2_compare_only": ("fe", 3600),
    "v3_error_geometry": ("ml", 1200),
    "v3_fit_checks": ("ml", 1800),
    "FEINN-REFERENCE-FIT-G": ("ml", 10800),
    "v3_retained_snapshot": ("ml", 1800),
    "v3_fit_reconstruct": ("ml", 1800),
    "v3_fit_compare_only": ("fe", 3600),
    "v4_boundary_checks": ("ml", 1800),
    "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY": ("ml", 10800),
    "v4_fit_reconstruct": ("ml", 1800),
    "v4_fit_compare_only": ("fe", 1800),
    "v5_readout_checks": ("ml", 1200),
    "FEINN-FROZEN-HIDDEN-READOUT-G": ("ml", 3600),
    "v5_readout_reconstruct": ("ml", 900),
    "v5_readout_compare_only": ("fe", 900),
}
STAGES.update({name: (entry[0], entry[1]) for name, entry in CAMPAIGN_STAGES.items()})
STAGES.update({name: (entry[0], entry[1]) for name, entry in GN_STAGES.items()})


def load_pilot(path):
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"[task42extra]" not in raw:
        return None
    try:
        config = tomllib.loads(raw.decode())
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise InputError(str(error)) from error
    if (
        set(config) != {"schema_version", "task42extra"}
        or config["schema_version"] != 1
    ):
        raise InputError("Task42extra accepts only one frozen explicit stage")
    item = config["task42extra"]
    authority = (
        item.get("stage", "").startswith("v7_")
        or item.get("stage") in AUTHORITY | GN_AUTHORITY
    )
    authority_policy = dict(
        audit_kind="DISCRETIZATION_AUTHORITY_AUDIT",
        reference_role="REFERENCE_ONLY",
        training_reference_allowed=False,
    )
    residual_readout = (
        item.get("stage", "").startswith("v6_")
        or item.get("stage") == "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT"
    )
    readout = residual_readout or (
        item.get("stage", "").startswith("v5_")
        or item.get("stage") == "FEINN-FROZEN-HIDDEN-READOUT-G"
    )
    policy = dict(
        reference_used_for_training=True,
        pde_only_solve=False,
        production_initialization_allowed=False,
        pde_only_solver_qualified=False,
        official_candidate_results=False,
    )
    if residual_readout:
        policy.update(features_reference_exposed=True, readout_rhs_uses_reference=False)
    v8_neural = item.get("stage") in (CAMPAIGN_STAGES | GN_STAGES) and not authority
    if v8_neural:
        supervised = item["stage"] in GN_SUPERVISED or item["stage"] in (
            "v8_plain_reference_fit",
            "v8_phase_reference_fit",
            "v8_representation_reconstruct",
            "v8_representation_compare",
        )
        policy.update(
            reference_used_for_training=supervised,
            features_reference_exposed=supervised,
            pde_only_solve=not supervised,
            benchmark_previously_seen=True,
        )
    allowed = (
        {"stage", "run_id", "design_sha256"}
        | (set(policy) if readout or v8_neural else set())
        | (set(authority_policy) if authority else set())
    )
    if set(item) != allowed or item["stage"] not in STAGES:
        raise InputError("Task42extra stage inventory mismatch")
    if (readout or v8_neural) and any(
        item[k] is not value for k, value in policy.items()
    ):
        raise InputError("reference-exposed readout policy required")
    if authority and any(item[k] != value for k, value in authority_policy.items()):
        raise InputError("explicit DISCRETIZATION_AUTHORITY_AUDIT required")
    if (
        not isinstance(item["run_id"], str)
        or not item["run_id"].startswith("task42extra_")
        or Path(item["run_id"]).name != item["run_id"]
    ):
        raise InputError("Task42extra local run_id required")
    digest = hashlib.sha256(DESIGN.read_bytes()).hexdigest()
    if item["design_sha256"] != digest:
        raise InputError("frozen design SHA mismatch")
    design = json.loads(DESIGN.read_text())
    mode, seconds = STAGES[item["stage"]]
    return RunSpecification(
        identity=dict(
            model_id=(
                "M5-p5-authority-audit"
                if item["stage"] in GN_AUTHORITY
                else "M5-p3-p4-authority-audit"
            )
            if authority
            else "M5-full-p3",
            run_id=item["run_id"],
        ),
        geometry=design["geometry"],
        materials=design["materials"],
        incidence=design["incidence"],
        discretization=dict(
            design["finite_element"], degree=5 if item["stage"] in GN_AUTHORITY else 4
        )
        if authority
        else design["finite_element"],
        boundary=design["boundary"],
        method=dict(kind="research_full_FEINN", stage=item["stage"]),
        solver=dict(preconditioner="task42extra_full_fe_opt_in"),
        execution=dict(
            mpi_size=1,
            math_threads=1,
            timeout_seconds=seconds,
            warning_memory_gib=12,
            terminate_memory_gib=16,
            require_zero_swap=True,
        ),
        output=dict(results_root="results/task42extra"),
        derived=dict(
            stage=item["stage"],
            environment_mode=mode,
            design_path=str(DESIGN),
            design_sha256=digest,
            identity_hash_meaning="frozen design; actual mesh/operator hashes bound after export",
            **(policy if readout or v8_neural else {}),
            **(authority_policy if authority else {}),
        ),
        source_path=path,
        raw_input_bytes=raw,
        input_sha256=hashlib.sha256(raw).hexdigest(),
        physical_model_sha256=digest,
        expected_output_parent=ROOT / "results/task42extra",
    )
