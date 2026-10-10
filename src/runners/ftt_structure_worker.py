"""V39 opt-in wiring; shared terminal, optimizer, and independent physics."""

import json
import os
import shlex
import subprocess
import sys
import traceback
from time import monotonic
from src.io.neural_wave_campaign import ROOT, digest
from src.io.ftt_structure_campaign import DESIGN
from src.io.ftt_campaign import load_files
from src.runners.ftt_worker import CHAIN as BASE_CHAIN, ftt_abi, load_arrays
from src.solvers.neural_wave_greedy import atomic_json

CHAIN = BASE_CHAIN + (
    "src/solvers/ftt_factored_moments.py",
    "src/solvers/ftt_structure_qualification.py",
    "src/io/ftt_structure_campaign.py",
    "src/runners/ftt_structure_worker.py",
)
ART = ROOT / "benchmarks/artifacts/task42extra/v39"


def routes(fit=False):
    return [
        (
            "v39_fttnn_fit_continue" if fit else "v39_fttnn_native_continue",
            "FTTNN_R8_FACTORED_FIT_CONTINUE"
            if fit
            else "FTTNN_R8_FACTORED_MAP_CONTINUE",
        ),
        (
            "v39_chebtt_fit_continue" if fit else "v39_chebtt_native_continue",
            "CHEB_TT_R8_FACTORED_FIT_CONTINUE"
            if fit
            else "CHEB_TT_R8_FACTORED_MAP_CONTINUE",
        ),
    ]


def training_allowed(path, design, active, fit, kind):
    from src.runners.ftt_worker import training_allowed as baseline

    try:
        p = ROOT.__class__(path).resolve()
    except TypeError:
        return True
    entry = design["parents"][kind + ("_fit" if fit else "_native")]
    if p in {(ROOT / entry[key]["path"]).resolve() for key in ("checkpoint", "result")}:
        return True
    return baseline(path, design, active, fit)


def subphase(directory, phase):
    manifest = json.loads((directory / "run_manifest.json").read_text())
    spec = manifest["spec"]
    design = json.loads(DESIGN.read_text())
    artifact = ROOT / manifest["artifact"]
    fit = spec["metric_kind"] == "reference_fit_G"
    from src.runners.neural_wave_worker import publish_event

    def marker(stage, value):
        publish_event(directory, stage, value)

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
            fit=fit,
            route_pairs=routes(fit),
            source_root=ART,
        )
    else:
        compare(
            design,
            action,
            packet,
            artifact,
            artifact,
            marker,
            fit=fit,
            route_pairs=routes(fit),
        )


def run_stage(manifest, artifact, marker, directory):
    spec = manifest["spec"]
    design = json.loads(DESIGN.read_text())
    if digest(DESIGN) != manifest["design_sha256"]:
        raise ValueError("FTT_STRUCTURE_DESIGN_CHANGED")
    fit = spec.get("metric_kind") == "reference_fit_G"
    if spec["role"] == "ftt_independent_compare":
        from src.runners.guarded_exec import ticks

        for phase, mode, file in [
            ("reconstruct", "ml", "reconstruction.json"),
            ("compare", "fe", "verifier_result.json"),
        ]:
            if (artifact / file).exists():
                continue
            command = (
                "source scripts/activate_task42extra.sh "
                + mode
                + " && exec python -m src.runners.ftt_structure_worker "
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

        command = [
            "bash",
            "-lc",
            "source scripts/activate_task42extra.sh pure && exec python -m src.postprocessing.ftt_verification "
            + shlex.quote(str(artifact.relative_to(ROOT)))
            + " --design "
            + shlex.quote(str(DESIGN.relative_to(ROOT))),
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
        )
    if spec["role"] == "ftt_train":
        kind = spec["model_kind"]
        q = json.loads((ART / "v39_ftt_factored_checks/result.json").read_text())
        b = json.loads((ART / "v39_ftt_factored_benchmark/result.json").read_text())
        if not q["models"][kind]["qualified"]:
            raise ValueError("FTT_MAPPING_EQUIVALENCE_GATE_FAILED")
        if not b["models"][kind][
            "fit_execution_cost_gate" if fit else "native_execution_cost_gate"
        ]:
            raise ValueError("FTT_EXECUTION_COST_GATE_FAILED")
        if fit:
            checker = json.loads(
                (ART / "v39_ftt_independent_compare/saved_checker.json").read_text()
            )
            if checker["records"]["FTTNN_R8_FACTORED_MAP_CONTINUE"][
                "m5_full_discrete_numerical_gate"
            ]:
                raise ValueError("FTT_FIT_NOT_AUTHORIZED_AFTER_NATIVE_PASS")

        def firewall(event, args):
            if event == "open" and not training_allowed(
                args[0], design, artifact, fit, kind
            ):
                raise PermissionError(
                    "FTT_STRUCTURE_TRAINING_FILE_ISOLATION_REJECTED:" + str(args[0])
                )

        sys.addaudithook(firewall)
        marker(
            "training_file_firewall_installed",
            dict(
                reference_access_allowed=fit,
                Gram_factor_allowed=False,
                global_Maxwell_factor_allowed=False,
                parent_kind=kind,
            ),
        )
    from src.solvers.feinn_native import load_native

    files = load_files(design, labelled=fit and spec["role"] == "ftt_train")
    action = load_native(files["native"])
    packet = load_arrays(files["moments_q30"])
    if (action.size, action.nc, action.np) != (31968, 384, 40):
        raise ValueError("FTT_ORIGINAL_M5_IDENTITY")
    if spec["role"] == "ftt_factored_checks":
        from src.solvers.ftt_structure_qualification import qualify

        return qualify(
            action, packet, load_arrays(files["moments_q60"]), design, artifact, marker
        )
    if spec["role"] == "ftt_factored_benchmark":
        from src.solvers.ftt_structure_qualification import benchmark

        return benchmark(action, packet, design, artifact, marker)
    if spec["role"] == "ftt_train":
        from src.solvers.ftt_structure_qualification import load_parent_model
        from src.solvers.ftt_factored_moments import FactoredMomentMap
        from src.solvers.ftt_optimization import make_metric, run_training

        model, _, state, candidate = load_parent_model(design, spec["model_kind"], fit)
        kwargs = {}
        if fit:
            from scipy.sparse import load_npz

            kwargs = dict(
                G=load_npz(files["gram"]),
                reference=load_arrays(files["reference"])["c"],
            )
        metric = make_metric(action, spec["metric_kind"], **kwargs)
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
            mapping_kind=spec["mapping_kind"],
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
            mapping=FactoredMomentMap(packet),
            resume_state=state,
            resume_identity=candidate,
        )
    raise ValueError("FTT_STRUCTURE_UNIMPLEMENTED_STAGE")


def main():
    directory = ROOT / sys.argv[1]
    if len(sys.argv) == 4 and sys.argv[2] == "--subphase":
        subphase(directory, sys.argv[3])
        return
    manifest = json.loads((directory / "run_manifest.json").read_text())
    artifact = ROOT / manifest["artifact"]
    from src.runners.neural_wave_worker import publish_event

    def marker(stage, values):
        publish_event(directory, stage, values)

    start = monotonic()
    try:
        atomic_json(directory / "abi.json", ftt_abi(manifest["spec"]["mode"]))
        result = run_stage(manifest, artifact, marker, directory)
        result.update(
            {
                k: manifest[k]
                for k in (
                    "source_sha",
                    "input_sha256",
                    "design_sha256",
                    "reference_used_for_training",
                    "features_reference_exposed",
                    "pde_only_solve",
                )
            }
        )
        result.update(
            model_kind=manifest["model_kind"],
            metric_kind=manifest["metric_kind"],
            worker_elapsed_seconds=monotonic() - start,
            production_initialization_allowed=False,
            pde_only_solver_qualified=False,
            official_candidate_results=False,
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
                elapsed_seconds=monotonic() - start,
            ),
        )
        raise


if __name__ == "__main__":
    main()
