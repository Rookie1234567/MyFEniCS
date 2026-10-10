"""Thin V41 opt-in wiring; existing supervision and independent field audit."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from time import monotonic
import traceback
from dataclasses import dataclass

from src.io.neural_wave_campaign import ROOT, digest
from src.io.ftt_core_campaign import DESIGN, routes
from src.io.ftt_campaign import load_files
from src.runners.ftt_worker import (
    CHAIN as BASE_CHAIN,
    ftt_abi,
    load_arrays,
    training_allowed,
)
from src.solvers.neural_wave_greedy import atomic_json

ART = ROOT / "benchmarks/artifacts/task42extra/v41"
CHAIN = BASE_CHAIN + (
    "src/solvers/ftt_factored_moments.py",
    "src/solvers/ftt_conditional_core.py",
    "src/solvers/ftt_core_training.py",
    "src/solvers/ftt_core_qualification.py",
    "src/io/ftt_core_campaign.py",
    "src/runners/ftt_core_worker.py",
    "src/runners/neural_wave_campaign.py",
    "src/runners/neural_wave_dependencies.py",
    "src/runners/block_wave_admission.py",
    "src/runners/feinn_resources.py",
)


@dataclass(frozen=True)
class CoreWorkerProfile:
    design: Path = DESIGN
    artifacts: Path = ART
    route_pairs: object = routes
    checks_stage: str = "v41_core_linear_checks"
    checks_role: str = "ftt_core_checks"
    compare_role: str = "ftt_core_compare"
    learned_role: str = "FTTNN_CONDITIONAL_CORE_LEARNED"
    worker_module: str = "src.runners.ftt_core_worker"
    model_factory: object = None
    qualification: object = None
    independent_field: object = None
    training_options: object = None


DEFAULT_PROFILE = CoreWorkerProfile()


def install_unlabelled_firewall(design, artifact):
    """Actually reject label opens, before any original native training load."""

    def firewall(event, args):
        if event == "open" and not training_allowed(args[0], design, artifact, False):
            raise PermissionError("CORE_UNLABELLED_DATA_FIREWALL:" + str(args[0]))

    sys.addaudithook(firewall)
    forbidden = [
        design["reference"]["path"],
        design["gram"]["path"],
        "benchmarks/artifacts/task42extra/v40/v40_interior_moment_tensor/interior_tensor.npz",
        "benchmarks/artifacts/task42extra/v39/v39_fttnn_fit_continue/checkpoints/committed_000001.pt",
    ]
    records = []
    for name in forbidden:
        try:
            with (ROOT / name).open("rb") as stream:
                stream.read(0)
        except PermissionError as error:
            if not str(error).startswith("CORE_UNLABELLED_DATA_FIREWALL:"):
                raise
            records.append(dict(path=name, actual_open_rejected=True, bytes_read=0))
        else:
            raise ValueError("CORE_LABEL_ACTUAL_OPEN_NOT_REJECTED")
    return records


def subphase(directory, phase, profile=DEFAULT_PROFILE):
    manifest = json.loads((directory / "run_manifest.json").read_text())
    design = json.loads(profile.design.read_text())
    artifact = ROOT / manifest["artifact"]
    from src.runners.neural_wave_worker import publish_event

    def marker(stage, values):
        publish_event(directory, stage, values)

    atomic_json(
        artifact / (phase + "_abi.json"),
        ftt_abi("ml" if phase == "reconstruct" else "fe"),
    )
    from src.solvers.feinn_native import load_native

    files = load_files(design)
    action = load_native(files["native"])
    packet = load_arrays(files["moments_q30"])
    from src.postprocessing.ftt_verification import reconstruct, compare

    if phase == "reconstruct":
        reconstruct(
            design,
            action,
            packet,
            load_arrays(files["moments_q60"]),
            artifact,
            marker,
            route_pairs=profile.route_pairs(),
            source_root=profile.artifacts,
            model_factory=profile.model_factory,
            independent_field=profile.independent_field,
        )
    elif phase == "compare":
        compare(
            design, action, packet, artifact, artifact, marker, route_pairs=profile.route_pairs()
        )
    else:
        raise ValueError("UNKNOWN_CORE_VERIFICATION_PHASE")


def checker_directory(artifact, directory):
    """Each recovery owns a fresh supervisor directory; old evidence stays."""
    return artifact / ("independent_pure_checker_" + directory.name)


def independent_compare(manifest, artifact, marker, directory, profile=DEFAULT_PROFILE):
    from src.runners.guarded_exec import ticks

    for phase, mode, name in [
        ("reconstruct", "ml", "reconstruction.json"),
        ("compare", "fe", "verifier_result.json"),
    ]:
        if (artifact / name).exists():
            continue
        command = (
            "source scripts/activate_task42extra.sh "
            + mode
            + " && exec python -m " + profile.worker_module + " "
            + shlex.quote(str(directory.relative_to(ROOT)))
            + " --subphase "
            + phase
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "src.runners.guarded_exec",
                str(os.getpid()),
                str(ticks(os.getpid())),
                "bash",
                "-lc",
                command,
            ],
            cwd=ROOT,
            check=True,
        )
    from src.runners.saved_field_supervision import run_checker
    from src.postprocessing.ftt_verification import seal_saved_research_policy

    policy_seal = seal_saved_research_policy(artifact, manifest["source_sha"])
    if policy_seal:
        marker("saved_research_use_policy_corrected", policy_seal)

    command = [
        "bash",
        "-lc",
        "source scripts/activate_task42extra.sh pure && exec python -m src.postprocessing.ftt_verification "
        + shlex.quote(str(artifact.relative_to(ROOT)))
        + " --design "
        + shlex.quote(str(profile.design.relative_to(ROOT))),
    ]
    summary = run_checker(
        command,
        checker_directory(artifact, directory),
        manifest["worker_stop_monotonic"],
        manifest["source_sha"],
    )
    return dict(
        saved_checker=json.loads((artifact / "saved_checker.json").read_text()),
        independent_checker_summary=summary,
        verification_complete=True,
        new_reference_solve_count=0,
        previously_healthy_reconstruction_and_FE_compare_reused=True,
        research_use_policy_seal=policy_seal
        or json.loads((artifact / "verifier_result.json").read_text()).get(
            "research_use_policy_seal"
        ),
    )


def run_stage(manifest, artifact, marker, directory, profile=DEFAULT_PROFILE):
    spec = manifest["spec"]
    design = json.loads(profile.design.read_text())
    if digest(profile.design) != manifest["design_sha256"]:
        raise ValueError("CORE_FROZEN_DESIGN_CHANGED")
    if spec["role"] == profile.compare_role:
        return independent_compare(manifest, artifact, marker, directory, profile)
    if spec["role"] != profile.checks_role:
        qualification = json.loads(
            (profile.artifacts / profile.checks_stage / "result.json").read_text()
        )
        if not qualification["models"][spec["model_kind"]]["qualified"]:
            raise ValueError("CORE_ACTUAL_NEW_OPERATOR_NOT_QUALIFIED")

        label_checks = install_unlabelled_firewall(design, artifact)
        marker(
            "training_file_firewall_installed",
            dict(
                reference_allowed=False,
                fit_allowed=False,
                V40_tensor_allowed=False,
                actual_open_negative_checks=label_checks,
            ),
        )
    from src.solvers.feinn_native import load_native

    files = load_files(design)
    action = load_native(files["native"])
    packet = load_arrays(files["moments_q30"])
    if (action.size, action.nc, action.np) != (31968, 384, 40):
        raise ValueError("CORE_ORIGINAL_M5_IDENTITY")
    if spec["role"] == profile.checks_role:
        from src.solvers.ftt_core_qualification import actual_checks

        qualifier = profile.qualification or actual_checks
        result = qualifier(
            action, packet, design, marker, manifest["worker_stop_monotonic"]
        )
        forbidden = [
            design["reference"]["path"],
            design["gram"]["path"],
            "benchmarks/artifacts/task42extra/v40/v40_interior_moment_tensor/interior_tensor.npz",
            "benchmarks/artifacts/task42extra/v39/v39_fttnn_fit_continue/checkpoints/committed_000001.pt",
        ]
        result["label_firewall_negative_checks"] = [
            dict(
                path=p, rejected=not training_allowed(ROOT / p, design, artifact, False)
            )
            for p in forbidden
        ]
        result["qualified"] &= all(
            v["rejected"] for v in result["label_firewall_negative_checks"]
        )
        if not result["qualified"]:
            atomic_json(artifact / "qualification_failed.json", result)
            raise ValueError("CORE_TARGETED_ACTUAL_QUALIFICATION_FAILED")
        return result
    from src.solvers.ftt_field import FTTField
    from src.solvers.ftt_core_training import run_core_training

    model = FTTField(
        design["model"]["geometry"]["bounds_nm"],
        spec["model_kind"],
        seed=design["seed"],
    ) if profile.model_factory is None else profile.model_factory(design, spec["model_kind"])
    binding = dict(
        source_sha=manifest["source_sha"],
        input_sha256=manifest["input_sha256"],
        design_sha256=manifest["design_sha256"],
        native_sha256=design["files"]["native"]["sha256"],
        moments_sha256=design["files"]["moments_q30"]["sha256"],
        reference_sha256=None,
        model_kind=spec["model_kind"],
        metric_kind="native_euc",
        route=spec["role"],
        route_origin_monotonic=manifest["route_origin_monotonic"],
        reference_used_for_training=False,
        features_reference_exposed=False,
        pde_only_solve=True,
        benchmark_previously_seen=True,
        design_informed_by_reference_diagnostics=True,
        production_initialization_allowed=False,
        official_candidate_results=False,
        pde_only_solver_qualified=False,
    )
    if "phase_definition" in design:
        binding.update(phase_sha256=design["phase_definition"]["sha256"],
            phase_definition=design["phase_definition"], validation_used_for_stopping=True)
    options = {} if profile.training_options is None else profile.training_options(
        manifest, artifact, marker, directory, design)
    result = run_core_training(
        action,
        packet,
        model,
        artifact,
        binding,
        manifest["worker_stop_monotonic"],
        marker,
        learned=spec["role"] == profile.learned_role,
        **options,
    )
    result["label_firewall_actual_open_negative_checks"] = label_checks
    return result


def main(profile=DEFAULT_PROFILE):
    directory = ROOT / Path(sys.argv[1])
    if len(sys.argv) == 4 and sys.argv[2] == "--subphase":
        subphase(directory, sys.argv[3], profile)
        return
    manifest = json.loads((directory / "run_manifest.json").read_text())
    artifact = ROOT / manifest["artifact"]
    from src.runners.neural_wave_worker import publish_event

    def marker(stage, values):
        publish_event(directory, stage, values)

    began = monotonic()
    try:
        atomic_json(directory / "abi.json", ftt_abi(manifest["spec"]["mode"]))
        result = run_stage(manifest, artifact, marker, directory, profile)
        result.update(
            source_sha=manifest["source_sha"],
            input_sha256=manifest["input_sha256"],
            design_sha256=manifest["design_sha256"],
            worker_elapsed_seconds=monotonic() - began,
            reference_used_for_training=False,
            features_reference_exposed=False,
            benchmark_previously_seen=True,
            design_informed_by_reference_diagnostics=True,
            production_initialization_allowed=False,
            official_candidate_results=False,
            pde_only_solver_qualified=False,
            global_Maxwell_factor_count=0,
            global_Gram_factor_count=0,
            Gsolve_count=0,
            full_original_target_qualified=False,
        )
        atomic_json(artifact / "result.json", result)
        marker("stage_frozen", dict(result_sha256=digest(artifact / "result.json")))
    except BaseException as error:
        atomic_json(
            artifact / ("failure_" + directory.name + ".json"),
            dict(
                error=repr(error),
                traceback=traceback.format_exc(),
                source_sha=manifest["source_sha"],
                worker_elapsed_seconds=monotonic() - began,
                status="FAILED_NOT_RECLASSIFIED",
            ),
        )
        raise


if __name__ == "__main__":
    main()
