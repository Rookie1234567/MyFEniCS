"""Thin V33 opt-in wiring; numerical work lives in reusable solver modules."""

import json
import sys
from time import monotonic

import numpy as np

from src.io.neural_wave_campaign import ROOT, digest, profile_paths, load_training_files
from src.solvers.neural_wave_greedy import atomic_json

ROUTES = [
    ("v33_deterministic_backfit", "DETERMINISTIC_WAVE_BACKFIT"),
    ("v33_learned_varpro_backfit", "LEARNED_VARPRO_BACKFIT"),
]
CHAIN = (
    "src/solvers/neural_wave_backfit.py",
    "src/solvers/neural_wave_backfit_state.py",
    "src/solvers/neural_wave_backfit_run.py",
    "src/solvers/neural_wave_backfit_qualification.py",
    "src/io/neural_wave_backfit_store.py",
    "src/solvers/neural_wave_moments.py",
    "src/solvers/neural_wave_multiscale.py",
    "src/runners/backfit_wave_worker.py",
    "src/io/backfit_wave_campaign.py",
)
# These three files wire timing, roles and qualification consumption. Their
# changes need targeted contract tests; they do not invalidate unchanged real
# moments/LS/derivative/QR/transaction evidence. Keep the full CHAIN in run/source
# bindings and receipts, and compare every numerical dependency below.
MATHEMATICS_CHAIN = tuple(p for p in CHAIN if p not in (
    "src/solvers/neural_wave_backfit_run.py",
    "src/runners/backfit_wave_worker.py",
    "src/io/backfit_wave_campaign.py",
))


def receipt_matches(receipt, key):
    relevant = (
        ("src/solvers/neural_wave_backfit_state.py",)
        if key == "anchor_qualified" else MATHEMATICS_CHAIN
    )
    return bool(receipt[key]) and all(
        receipt["bound_numerical_chain"].get(p) == digest(ROOT / p)
        for p in relevant
    )


def early_validate(action, packet, design, artifact, spec, root, marker, source,
                   *, routes=None):
    from src.solvers.neural_wave_block_reconstruction import rebuild_stable
    from src.solvers.feinn_fem import build_model
    from src.postprocessing.neural_wave_audit import (
        save_complete_field_samples,
        relative_error,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    route = "learned" if "learned" in spec["stage"] else "deterministic"
    node = int(spec["stage"][-1])
    directory = root / (ROUTES if routes is None else routes)[route == "learned"][0]
    request = json.loads((directory / f"validation_requested_{node}.json").read_text())
    boundary = directory / "basis/committed.json"
    if digest(boundary) != request["boundary_sha256"]:
        raise ValueError("SCALAR_SCORING_NOT_AT_REQUESTED_COMMITTED_STATE")
    c, producer, _ = rebuild_stable(directory / "basis", packet, marker)
    index = json.loads(
        (ROOT / "benchmarks/artifacts/task42extra/index_e3_reference.json").read_text()
    )
    entry = index["files"]["reference"]
    if digest(entry["path"]) != entry["sha256"]:
        raise ValueError("SAME_P3_REFERENCE_HASH_FAILED")
    with np.load(entry["path"], allow_pickle=False) as z:
        ref = np.array(z["c"])
    model = build_model(design["model"], marker=marker)
    try:
        for k, v in design["native_identity"].items():
            if model["record"][k] != v:
                raise ValueError("SAME_M5_PHYSICAL_IDENTITY_REQUIRED")
        raw, _ = save_complete_field_samples(
            model, action, packet, ref, {"CANDIDATE": c}, artifact, marker
        )
        with np.load(raw, allow_pickle=False) as z:
            errors = {
                k: relative_error(
                    z["CANDIDATE_" + k] - z["REFERENCE_" + k],
                    z["REFERENCE_" + k],
                    weights=z["weights"],
                )
                for k in ("E", "curl")
            }
        audit = action.audit(c)
        ineffective = max(
            audit["native_relative"], audit["augmented_relative"]
        ) > design["anchor"]["native_relative"] * 0.5 and all(
            errors[k]["relative"] >= 0.01 for k in errors
        )
        result = dict(
            node=node,
            audit=audit,
            scattered_errors=errors,
            boundary_sha256=digest(boundary),
            ineffective=ineffective,
            continuation_allowed=not ineffective or node == 1,
            reference_sha256=entry["sha256"],
            reference_solve_count=0,
            raw_samples=dict(path=str(raw.relative_to(ROOT)), sha256=digest(raw)),
            model_mapping=float(
                np.linalg.norm(c - producer) / max(np.linalg.norm(c), 1e-30)
            ),
        )
        atomic_json(artifact / "scoring_record.json", result)
        atomic_json(
            directory / f"validation_scalars_{node}.json",
            dict(
                schema="backfit.validation.scalars.v1",
                node=node,
                boundary_sha256=digest(boundary),
                native_relative=audit["native_relative"],
                augmented_relative=audit["augmented_relative"],
                scattered_E_relative=errors["E"]["relative"],
                scattered_H_relative=errors["curl"]["relative"],
                continuation_allowed=result["continuation_allowed"],
                ineffective=ineffective,
                source_sha=source,
                scoring_result_sha256=digest(artifact / "scoring_record.json"),
            ),
        )
        return result
    finally:
        destroy_same_mesh_physical_action(model["bundle"])


def run_stage(manifest, artifact, marker):
    spec = manifest["spec"]
    profile = profile_paths(spec)
    design = json.loads(profile["design"].read_text())
    if digest(profile["design"]) != manifest["design_sha256"]:
        raise ValueError("FROZEN_V33_DESIGN_CHANGED")
    role = spec["role"]
    if role.startswith("backfit_transfer"):
        gates = profile["artifacts"] / "v33_backfit_compare/result.json"
        if not gates.exists() or not json.loads(gates.read_text()).get(
            "learned_joint_pass", False
        ):
            raise ValueError("CONDITIONAL_0P7_M5_JOINT_GATE_NOT_PASSED")
        if manifest["campaign"]["deadline_monotonic"] - monotonic() < 7200:
            raise ValueError("CONDITIONAL_0P7_TIME_RESERVE_NOT_AVAILABLE")
        raise ValueError("CONDITIONAL_TRANSFER_REQUIRES_FROZEN_QUALIFIED_M5_BINDING")
    unlabelled = role in (r[1] for r in ROUTES) or role in (
        "backfit_anchor_checks",
        "backfit_math_checks",
    )
    if unlabelled:
        from src.io.backfit_wave_campaign import training_open_allowed

        design["active_training_artifact"] = str(artifact)

        def firewall(event, args):
            if event == "open" and not training_open_allowed(args[0], design):
                raise PermissionError("UNLABELLED_V33_ACCESS_REJECTED: " + str(args[0]))

        sys.addaudithook(firewall)
        marker("unlabelled_firewall", dict(reference_read_allowed=False))
    files = load_training_files(design)
    from src.solvers.feinn_native import load_native

    action = load_native(files["native"])
    with np.load(files["moments_q30"], allow_pickle=False) as z:
        packet = {k: np.array(z[k]) for k in z.files}
    if (action.size, action.nc, action.np) != (31968, 384, 40) or not np.array_equal(
        packet["master_native_rows"], action.a["masters"]
    ):
        raise ValueError("M5_COMPLETE_MASTER_IDENTITY_FAILED")
    if role == "backfit_reconstruct":
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
    if role == "backfit_compare":
        from src.runners.block_wave_worker import saved_checker

        result = saved_checker(
            action,
            profile["artifacts"] / "v33_backfit_reconstruct/result.json",
            design,
            marker,
        )
        return result
    if role == "backfit_early_validate":
        return early_validate(
            action,
            packet,
            design,
            artifact,
            spec,
            profile["artifacts"],
            marker,
            manifest["source_sha"],
        )
    from src.solvers.neural_wave_backfit_state import load_anchor

    space, blocks, anchor, checks = load_anchor(action, design)
    if role == "backfit_anchor_checks":
        return dict(
            anchor_qualified=bool(
                abs(checks["native"] - design["anchor"]["native_relative"]) < 1e-10
            ),
            anchor=checks,
            anchor_sha256=design["anchor"]["boundary_sha256"],
            reference_read_count=0,
            bound_numerical_chain={p: digest(ROOT / p) for p in CHAIN},
        )
    if role == "backfit_math_checks":
        from src.solvers.neural_wave_backfit_qualification import qualify_real

        result = qualify_real(
            action,
            packet,
            space,
            blocks,
            2 * np.pi / 5,
            marker,
            artifact=artifact,
            anchor=anchor,
            binding=dict(source_sha=manifest["source_sha"], route="QUALIFICATION"),
        )
        result["bound_numerical_chain"] = {p: digest(ROOT / p) for p in CHAIN}
        return result
    for stage, key in (
        ("v33_backfit_anchor_checks", "anchor_qualified"),
        ("v33_backfit_math_checks", "implementation_qualified"),
    ):
        receipt = json.loads((profile["artifacts"] / stage / "result.json").read_text())
        if not receipt_matches(receipt, key):
            raise ValueError("BACKFIT_SHARED_IMPLEMENTATION_NOT_QUALIFIED")
    marker("backfit_qualified_dependencies_reused", dict(
        unchanged_mathematical_dependencies=MATHEMATICS_CHAIN,
        full_run_source_binding_retained=True,
        orchestration_contract_tests_required=True,
    ))
    from src.solvers.neural_wave_backfit_run import run_backfit

    return run_backfit(
        action, packet, space, blocks, anchor, design, manifest, artifact, marker
    )
