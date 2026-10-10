"""Parameter-only FTT stage wiring; numerical kernels and physics stay in src."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from time import monotonic
import traceback
import numpy as np
from src.io.neural_wave_campaign import ROOT, digest
from src.io.ftt_campaign import DESIGN, load_files
from src.solvers.neural_wave_greedy import atomic_json

CHAIN = (
    "src/solvers/ftt_field.py",
    "src/solvers/ftt_moments.py",
    "src/solvers/ftt_optimization.py",
    "src/solvers/ftt_qualification.py",
    "src/postprocessing/ftt_verification.py",
    "src/io/ftt_campaign.py",
    "src/runners/ftt_worker.py",
    "src/solvers/optimization_checkpoint.py",
    "src/solvers/feinn_torch.py",
    "src/solvers/feinn_native.py",
    "src/solvers/feinn_interpolation.py",
    "src/solvers/feinn_reference.py",
    "src/solvers/feinn_fem.py",
    "src/postprocessing/neural_wave_audit.py",
    "src/runners/block_wave_worker.py",
    "src/runners/saved_field_supervision.py",
)
ART = ROOT / "benchmarks/artifacts/task42extra/v38"


def training_allowed(path, design, active, labelled):
    try:
        path = Path(path).resolve()
    except TypeError:
        return True
    allowed = {(ROOT / e["path"]).resolve() for e in design["files"].values()}
    if labelled:
        allowed.update(
            (ROOT / design[k]["path"]).resolve() for k in ("reference", "gram")
        )
    if path.is_relative_to(ROOT / "benchmarks/artifacts/task42extra"):
        return path in allowed or path.is_relative_to(active)
    if path.suffix in (".npz", ".pt", ".pth"):
        return path in allowed or path.is_relative_to(active)
    return True


def load_arrays(path):
    with np.load(path, allow_pickle=False) as arrays:
        return {k: np.array(arrays[k]) for k in arrays.files}


def ftt_abi(mode):
    from src.runners.neural_wave_worker import abi

    facts = abi(mode)
    if mode == "ml":
        facts["neuron_and_derivative_dtype"] = (
            "FTT parameters and coordinate buffers float64; "
            "paired complex outputs and complete moments complex128"
        )
        facts["dtype_verification"] = "explicit FTTField dtype and qualified mapping"
    return facts


def subphase(directory, phase):
    manifest = json.loads((directory / "run_manifest.json").read_text())
    design = json.loads(DESIGN.read_text())
    artifact = ROOT / manifest["artifact"]
    mode = "ml" if phase == "reconstruct" else "fe"
    from src.runners.neural_wave_worker import publish_event

    atomic_json(artifact / (phase + "_abi.json"), ftt_abi(mode))
    from src.solvers.feinn_native import load_native

    files = load_files(design)
    action = load_native(files["native"])
    packet = load_arrays(files["moments_q30"])
    from src.postprocessing.ftt_verification import reconstruct, compare

    def marker(stage, values):
        publish_event(directory, stage, values)

    if phase == "reconstruct":
        high = load_arrays(files["moments_q60"])
        reconstruct(design, action, packet, high, artifact, marker, fit=True)
    else:
        compare(design, action, packet, artifact, artifact, marker, fit=True)


def run_stage(manifest, artifact, marker, directory):
    spec = manifest["spec"]
    design = json.loads(DESIGN.read_text())
    if digest(DESIGN) != manifest["design_sha256"]:
        raise ValueError("FTT_DESIGN_CHANGED_AFTER_LAUNCH")
    fit = spec.get("metric_kind") == "reference_fit_G"
    if spec["role"] == "ftt_train":
        qualification = json.loads((ART / "v38_ftt_checks/result.json").read_text())
        if not qualification["models"][spec["model_kind"]]["qualified"]:
            raise ValueError("NEW_FTT_INTERFACE_NOT_QUALIFIED")
        if fit:
            checked = json.loads(
                (ART / "v38_ftt_compare/saved_checker.json").read_text()
            )
            if checked["records"]["FTTNN_R8_NATIVE_EUC"][
                "m5_full_discrete_numerical_gate"
            ]:
                raise ValueError("FIT_NOT_AUTHORIZED_AFTER_UNLABELLED_PASS")

        def firewall(event, args):
            if event == "open" and not training_allowed(args[0], design, artifact, fit):
                raise PermissionError(
                    "FTT_TRAINING_FILE_ISOLATION_REJECTED:" + str(args[0])
                )

        sys.addaudithook(firewall)
        marker(
            "training_file_firewall_installed",
            dict(
                reference_access_allowed=fit,
                Gram_factor_allowed=False,
                old_weights_allowed=False,
            ),
        )
    if spec["role"] == "ftt_fit_compare":
        from src.runners.guarded_exec import ticks

        for phase, mode in (("reconstruct", "ml"), ("compare", "fe")):
            if phase == "reconstruct" and (artifact / "reconstruction.json").exists():
                continue
            if phase == "compare" and (artifact / "verifier_result.json").exists():
                continue
            command = (
                "source scripts/activate_task42extra.sh "
                + mode
                + " && exec python -m src.runners.ftt_worker "
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
        return independent_checker(manifest, artifact)
    from src.solvers.feinn_native import load_native

    files = load_files(design, labelled=fit and spec["role"] == "ftt_train")
    action = load_native(files["native"])
    packet = load_arrays(files["moments_q30"])
    if (action.size, action.nc, action.np) != (31968, 384, 40) or not np.array_equal(
        packet["master_native_rows"], action.a["masters"]
    ):
        raise ValueError("FTT_ORIGINAL_M5_FULL_FE_IDENTITY_REQUIRED")
    if spec["role"] == "ftt_checks":
        from src.solvers.ftt_qualification import qualify

        return qualify(
            action,
            packet,
            load_arrays(files["moments_q60"]),
            design["model"]["geometry"]["bounds_nm"],
            marker,
        )
    if spec["role"] == "ftt_train":
        from src.solvers.ftt_optimization import make_model, make_metric, run_training

        model = make_model(
            design["model"]["geometry"]["bounds_nm"], spec["model_kind"], design["seed"]
        )
        kw = {}
        if fit:
            from scipy import sparse

            label = load_arrays(files["reference"])["c"]
            kw = dict(G=sparse.load_npz(files["gram"]), reference=label)
        metric = make_metric(action, spec["metric_kind"], **kw)
        binding = {
            k: manifest[k]
            for k in (
                "source_sha",
                "input_sha256",
                "design_sha256",
                "reference_used_for_training",
                "features_reference_exposed",
                "pde_only_solve",
                "production_initialization_allowed",
                "model_kind",
                "metric_kind",
            )
        }
        binding.update(
            native_sha256=design["files"]["native"]["sha256"],
            moments_sha256=design["files"]["moments_q30"]["sha256"],
            reference_sha256=design["reference"]["sha256"] if fit else None,
            pde_only_solver_qualified=False,
            official_candidate_results=False,
            benchmark_previously_seen=True,
            model_schema="ftt-field.v1",
        )
        return run_training(
            action,
            packet,
            model,
            metric,
            artifact,
            binding,
            manifest["worker_stop_monotonic"],
            marker,
            call_limit=500 if fit else 1000,
            adam_steps=100 if fit else 500,
        )
    if spec["role"] == "ftt_reconstruct":
        from src.postprocessing.ftt_verification import reconstruct

        return dict(
            reconstruction=reconstruct(
                design,
                action,
                packet,
                load_arrays(files["moments_q60"]),
                artifact,
                marker,
            )
        )
    if spec["role"] == "ftt_compare":
        from src.postprocessing.ftt_verification import compare

        if not (artifact / "verifier_result.json").exists():
            compare(
                design, action, packet, ART / "v38_ftt_reconstruct", artifact, marker
            )
        return independent_checker(manifest, artifact)
    raise ValueError("FTT_UNIMPLEMENTED_STAGE")


def independent_checker(manifest, artifact):
    from src.runners.saved_field_supervision import run_checker

    command = [
        "bash",
        "-lc",
        "source scripts/activate_task42extra.sh pure && exec python -m src.postprocessing.ftt_verification "
        + shlex.quote(str(artifact.relative_to(ROOT))),
    ]
    summary = run_checker(
        command,
        artifact / "independent_pure_checker",
        manifest["worker_stop_monotonic"],
        manifest["source_sha"],
    )
    return dict(
        saved_checker=json.loads((artifact / "saved_checker.json").read_text()),
        independent_checker_summary=summary,
        reference_solve_count=0,
        global_Maxwell_factor_count=0,
        global_Gram_factor_count=0,
        Gsolve_count=0,
    )


def main():
    directory = ROOT / Path(sys.argv[1])
    if len(sys.argv) == 4 and sys.argv[2] == "--subphase":
        subphase(directory, sys.argv[3])
        return
    manifest = json.loads((directory / "run_manifest.json").read_text())
    artifact = ROOT / manifest["artifact"]
    from src.runners.neural_wave_worker import publish_event

    started = monotonic()

    def marker(stage, values):
        publish_event(directory, stage, values)

    try:
        atomic_json(directory / "abi.json", ftt_abi(manifest["spec"]["mode"]))
        result = run_stage(manifest, artifact, marker, directory)
        result.update(
            reference_used_for_training=manifest["reference_used_for_training"],
            features_reference_exposed=manifest["features_reference_exposed"],
            pde_only_solve=manifest["pde_only_solve"],
            production_initialization_allowed=False,
            official_candidate_results=False,
            pde_only_solver_qualified=False,
        )
        result.update(
            source_sha=manifest["source_sha"],
            input_sha256=manifest["input_sha256"],
            design_sha256=manifest["design_sha256"],
            worker_elapsed_seconds=monotonic() - started,
            actual_route_elapsed_seconds=monotonic()
            - manifest["route_origin_monotonic"],
            full_original_target_qualified=False,
        )
        atomic_json(artifact / "result.json", result)
        marker(
            "stage_frozen",
            dict(
                stage=manifest["spec"]["stage"],
                result_sha256=digest(artifact / "result.json"),
            ),
        )
    except BaseException as error:
        atomic_json(
            artifact / ("failure_" + directory.name + ".json"),
            dict(
                error=repr(error),
                traceback=traceback.format_exc(),
                source_sha=manifest["source_sha"],
                elapsed_seconds=monotonic() - started,
            ),
        )
        raise


if __name__ == "__main__":
    main()
