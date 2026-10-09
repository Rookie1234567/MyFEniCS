"""Thin V34 wiring; full moments/variable projection stay in solver modules."""

import json
import sys
from time import monotonic

import numpy as np

from src.io.neural_wave_campaign import ROOT, digest, profile_paths, load_training_files

ROUTES = [
    ("v34_deterministic_complex_backfit", "DETERMINISTIC_COMPLEX_WAVE_BACKFIT"),
    ("v34_learned_complex_backfit", "LEARNED_COMPLEX_WAVE_BACKFIT"),
]
CHAIN = (
    "src/io/complex_wave_campaign.py",
    "src/runners/complex_wave_worker.py",
    "src/io/neural_wave_backfit_store.py",
    "src/solvers/neural_wave_moments.py",
    "src/solvers/neural_wave_decay.py",
    "src/solvers/neural_wave_decay_qualification.py",
    "src/solvers/neural_wave_decay_calibration.py",
    "src/solvers/neural_wave_backfit.py",
    "src/solvers/neural_wave_backfit_state.py",
    "src/solvers/neural_wave_backfit_run.py",
    "src/solvers/neural_wave_block_reconstruction.py",
    "src/runners/backfit_wave_worker.py",
    "src/solvers/neural_wave_multiscale.py",
)
MATHEMATICS_CHAIN = tuple(
    p
    for p in CHAIN
    if p
    not in (
        "src/io/complex_wave_campaign.py",
        "src/runners/complex_wave_worker.py",
        "src/solvers/neural_wave_backfit_run.py",
        "src/runners/backfit_wave_worker.py",
    )
)


def learned_pair_joint_pass(result):
    """Require both independently scored representations of the learned field."""
    if not isinstance(result, dict):
        return False
    if (
        result.get("reference_pass") is not True
        or result.get("statuses_trusted") is not False
    ):
        return False
    records = result.get("records")
    if not isinstance(records, dict):
        return False
    return all(
        isinstance(records.get(name), dict)
        and records[name].get("m5_full_discrete_numerical_gate") is True
        for name in (ROUTES[1][1], ROUTES[1][1] + "_PRODUCER")
    )


def run_stage(manifest, artifact, marker):
    spec = manifest["spec"]
    profile = profile_paths(spec)
    if digest(profile["design"]) != manifest["design_sha256"]:
        raise ValueError("FROZEN_V34_DESIGN_CHANGED")
    design = json.loads(profile["design"].read_text())
    role = spec["role"]
    if role.startswith("complex_pilot_"):
        gates = profile["artifacts"] / "v34_complex_compare/result.json"
        if not gates.exists() or not learned_pair_joint_pass(
            json.loads(gates.read_text())
        ):
            raise ValueError("CONDITIONAL_0P7_M5_JOINT_GATE_NOT_PASSED")
        if manifest["campaign"]["deadline_monotonic"] - monotonic() < 7200:
            raise ValueError("CONDITIONAL_0P7_TIME_RESERVE_NOT_AVAILABLE")
        # A passed M5 must bind a new pilot's mesh/material/modes/packets. This
        # branch cannot reuse M5 coefficients, pretend a calibration is a PDE,
        # or silently load the W1 material. Its dedicated binding is required.
        binding = profile["artifacts"] / "qualified_pilot_binding.json"
        if not binding.exists():
            raise ValueError("QUALIFIED_M5_REQUIRES_NEW_PILOT_BINDING_BEFORE_EXECUTION")
        from src.runners.neural_wave_complex_pilot import run_pilot_stage

        return run_pilot_stage(manifest, design, artifact, marker)
    unlabelled = role in (r[1] for r in ROUTES) or role == "complex_wave_checks"
    if unlabelled:
        from src.io.complex_wave_campaign import training_open_allowed

        design["active_training_artifact"] = str(artifact)

        def firewall(event, args):
            if event == "open" and not training_open_allowed(
                args[0], design, qualification=role == "complex_wave_checks"
            ):
                raise PermissionError("UNLABELLED_V34_ACCESS_REJECTED: " + str(args[0]))

        sys.addaudithook(firewall)
        marker(
            "unlabelled_firewall",
            dict(reference_read_allowed=False, decay_parameters_are_explicit_real=True),
        )
    if role == "complex_wave_calibration":
        from src.solvers.neural_wave_decay_calibration import calibrate_decay

        result = calibrate_decay(marker)
        result["bound_numerical_chain"] = {p: digest(ROOT / p) for p in CHAIN}
        return result
    if (
        role == "complex_wave_checks"
        and (artifact / "qualification_reuse.json").exists()
    ):
        # A denominator-only checker fix reuses all 32 healthy full witnesses.
        # Preserve and hash-bind the original negative classification, and
        # forbid reuse across any changed numerical kernel or input.
        from src.solvers.neural_wave_decay_qualification import saved_witness_gate
        from src.io.neural_wave_backfit_store import check_boundary

        recovery = json.loads((artifact / "qualification_reuse.json").read_text())
        old_file = artifact / recovery["original_result_file"]
        old = json.loads(old_file.read_text())
        checker_path = "src/solvers/neural_wave_decay_qualification.py"
        if (
            old_file.parent != artifact
            or digest(old_file) != recovery["original_result_sha256"]
            or old["source_sha"] != "7c0dcc1985af1be6d5b0c919e982ba778d857537"
            or old["bound_numerical_chain"][checker_path]
            != "c1bbb48ca3ee0a33fd8d3df9bf4c0bbd4ea01adaadb51ffe13fd5292496efaac"
            or old["design_sha256"] != manifest["design_sha256"]
            or not all(
                old["bound_numerical_chain"][p] == digest(ROOT / p)
                for p in CHAIN
                if p not in (checker_path, "src/runners/complex_wave_worker.py")
            )
            or old["actual_complete_trials"] != 32
        ):
            raise ValueError("SAVED_COMPLEX_QUALIFICATION_NUMERICAL_CHAIN_CHANGED")
        check_boundary(artifact / "complex_short_block/committed.json")
        result = dict(old)
        result["implementation_qualified"] = saved_witness_gate(
            old["rows"], old["actual_saved_loop"], old["anchor_restored_bitwise"]
        )
        result.update(
            original_result_file=recovery["original_result_file"],
            original_result_sha256=recovery["original_result_sha256"],
            qualification_producer_source_sha=old["source_sha"],
            qualification_checker_source_sha=manifest["source_sha"],
            original_implementation_qualified=old["implementation_qualified"],
            residual_gate_denominator="original ||f||; saved-residual denominator retained diagnostic only",
            newly_executed_complete_trials=0,
            reused_complete_trials=32,
            newly_executed_original_action_calls=0,
            bound_numerical_chain={p: digest(ROOT / p) for p in CHAIN},
        )
        marker(
            "saved_complex_witness_gate_recomputed",
            dict(
                qualified=result["implementation_qualified"],
                new_trials=0,
                reused_trials=32,
                original_result_sha256=recovery["original_result_sha256"],
            ),
        )
        return result
    files = load_training_files(design)
    from src.solvers.feinn_native import load_native

    action = load_native(files["native"])
    with np.load(files["moments_q30"], allow_pickle=False) as arrays:
        packet = {k: np.array(arrays[k]) for k in arrays.files}
    if (action.size, action.nc, action.np) != (31968, 384, 40) or not np.array_equal(
        packet["master_native_rows"], action.a["masters"]
    ):
        raise ValueError("ORIGINAL_M5_COMPLETE_MASTER_IDENTITY_FAILED")
    if role == "complex_reconstruct":
        from src.runners.neural_wave_worker import verify

        return verify(
            design,
            action,
            packet,
            artifact,
            marker,
            stable_rebuild=True,
            include_producer=True,
            routes=ROUTES,
            route_root=profile["artifacts"],
        )
    if role == "complex_compare":
        from src.runners.block_wave_worker import saved_checker

        result = saved_checker(
            action,
            profile["artifacts"] / "v34_complex_reconstruct/result.json",
            design,
            marker,
        )
        # Neither the saved producer nor its independently regenerated network
        # can substitute for the other; both use the full saved-array checker.
        result["learned_joint_pass"] = learned_pair_joint_pass(result)
        return result
    if role == "complex_early_validate":
        from src.runners.backfit_wave_worker import early_validate

        return early_validate(
            action,
            packet,
            design,
            artifact,
            spec,
            profile["artifacts"],
            marker,
            manifest["source_sha"],
            routes=ROUTES,
        )
    from src.solvers.neural_wave_backfit_state import load_anchor

    space, blocks, anchor, checks = load_anchor(action, design)
    for block in blocks:
        block["decay_kappa"] = np.zeros_like(block["wave_q"])
    if role == "complex_wave_checks":
        from src.solvers.neural_wave_decay_qualification import qualify_decay

        high_entry = design["qualification_q60"]
        high_path = ROOT / high_entry["path"]
        if digest(high_path) != high_entry["sha256"]:
            raise ValueError("BOUND_HIGH_MOMENT_PACKET_CHANGED")
        with np.load(high_path, allow_pickle=False) as arrays:
            high = {k: np.array(arrays[k]) for k in arrays.files}
        result = qualify_decay(
            action,
            packet,
            high,
            space,
            blocks,
            2 * np.pi / design["model"]["wavelength_nm"],
            complex(*design["decay"]["beta_si_nm_inverse"]),
            artifact,
            anchor,
            dict(
                route="QUALIFICATION",
                source_sha=manifest["source_sha"],
                wave_representation="oscillation+decay.v1",
            ),
            marker,
        )
        result.update(
            anchor=checks, bound_numerical_chain={p: digest(ROOT / p) for p in CHAIN}
        )
        return result
    for stage, key in (
        ("v34_complex_wave_checks", "implementation_qualified"),
        ("v34_complex_wave_calibration", "calibration_qualified"),
    ):
        receipt = json.loads((profile["artifacts"] / stage / "result.json").read_text())
        if not receipt[key] or not all(
            receipt["bound_numerical_chain"].get(p) == digest(ROOT / p)
            for p in MATHEMATICS_CHAIN
        ):
            raise ValueError("V34_SHARED_NUMERICAL_DEPENDENCIES_NOT_QUALIFIED")
    from src.solvers.neural_wave_backfit_run import run_backfit

    return run_backfit(
        action, packet, space, blocks, anchor, design, manifest, artifact, marker
    )
