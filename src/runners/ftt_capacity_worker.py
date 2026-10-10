"""Saved-state capacity diagnostics through the existing supervised entry."""

import json
from pathlib import Path
import sys
from time import monotonic
import traceback

import numpy as np
from src.io.neural_wave_campaign import ROOT, digest
from src.io.ftt_capacity_campaign import DESIGN, checked_file
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz

ART = ROOT / "benchmarks/artifacts/task42extra/v40"
CHAIN = (
    "src/solvers/ftt_capacity.py", "src/solvers/ftt_interior_bridge.py",
    "src/solvers/ftt_feature_capacity.py", "src/solvers/ftt_capacity_checks.py",
    "src/io/ftt_capacity_campaign.py", "src/runners/ftt_capacity_worker.py",
    "benchmarks/check_ftt_capacity.py", "src/solvers/ftt_field.py",
    "src/solvers/optimization_checkpoint.py", "src/postprocessing/ftt_verification.py",
    "src/solvers/feinn_interpolation.py", "src/solvers/feinn_bounded_field_integrals.py",
    "src/geometry/neural_micro_pilot.py", "src/runners/neural_wave_campaign.py",
    "src/runners/neural_wave_dependencies.py", "src/runners/block_wave_admission.py",
    "src/runners/feinn_resources.py", "src/runners/saved_field_supervision.py",
)


def arrays(path):
    with np.load(path, allow_pickle=False) as value:
        return {k: np.array(value[k]) for k in value.files}


def phase(artifact, name, payload, **saved):
    if saved:
        path = artifact / (name + ".npz")
        atomic_npz(path, **saved)
        payload["arrays"] = dict(path=str(path.relative_to(ROOT)), sha256=digest(path))
    atomic_json(artifact / (name + ".json"), payload)
    return payload


def run_stage(manifest, artifact, marker):
    from src.solvers.ftt_capacity import full_spectrum, rank_bound, necessary_ranks, feature_bound

    design = json.loads(DESIGN.read_text())
    if digest(DESIGN) != manifest["design_sha256"]:
        raise ValueError("CAPACITY_FROZEN_DESIGN_CHANGED")
    role = manifest["spec"]["role"]
    if role == "ftt_capacity_checks":
        from src.solvers.ftt_capacity_checks import algebra_checks, functional_checks
        a = algebra_checks()
        b = functional_checks(arrays(checked_file(design["files"]["moments_q30"])),
                              arrays(checked_file(design["files"]["native"])))
        if not (a["qualified"] and b["qualified"]):
            raise ValueError("CAPACITY_TARGETED_QUALIFICATION_FAILED")
        return phase(artifact, "qualification", dict(algebra=a, original_functionals=b,
                     qualified=True, status="DIAGNOSTIC_QUALIFIED"))
    if role == "ftt_interior_tensor":
        q = json.loads((ART / "v40_capacity_checks/qualification.json").read_text())
        if not q["qualified"]:
            raise ValueError("CAPACITY_PREREQUISITE_NOT_QUALIFIED")
        from src.solvers.ftt_interior_bridge import build_tensor
        packet = arrays(checked_file(design["files"]["moments_q30"]))
        native = arrays(checked_file(design["files"]["native"]))
        reference = arrays(checked_file(design["reference"]))
        built = build_tensor(design["model"], packet, native, reference["c"], marker)
        report = built["report"]
        old = json.loads(checked_file(design["norm_record"]).read_text())
        denominator = old["physics"]["reference_scattered_norms"][0]
        report["original_full_scattered_E_denominator"] = denominator
        report["full_E_norm_independent_relative"] = abs(report["reference_E_norm"]-denominator)/denominator
        report["full_E_norm_independent_pass"] = report["full_E_norm_independent_relative"] <= 1e-10
        report["input_identity"] = {k: design[k] for k in ("reference", "norm_record", "native_identity")}
        saved = {f"{group}_{label}": T for group in ("full", "independent", "subset", "subset_independent")
                 for label, T in built[group].items()}
        saved.update(axis_ids=built["axis_ids"], transform_example=built["transform_example"])
        report["tensor_shapes"] = {s: list(T.shape) for s, T in built["full"].items()}
        report["tensor_complex128_bytes"] = sum(T.nbytes for T in built["full"].values())
        report["status"] = "DIAGNOSTIC_BRIDGE_LIMITED" if not report["rank_bound_transferable_to_actual_FE"] else "DIAGNOSTIC_BRIDGE_QUALIFIED"
        return phase(artifact, "interior_tensor", report, **saved)
    if role == "ftt_capacity_bounds":
        tensor_record = json.loads((ART / "v40_interior_moment_tensor/interior_tensor.json").read_text())
        if not (tensor_record["numerical_moment_pairing_pass"] and tensor_record["full_E_norm_independent_pass"]):
            raise ValueError("CAPACITY_REFERENCE_MOMENT_NUMERICAL_PAIRING_FAILED")
        saved = arrays(checked_file(tensor_record["arrays"]))
        tensors = {s: saved["full_"+s] for s in "xyz"}
        spectra, S = {}, {}
        for s, T in tensors.items():
            spectra[s] = []
            for a in range(3):
                (U, sigma, Vh), report = full_spectrum(T, a)
                if not report["qualified"]:
                    raise ValueError("CAPACITY_FULL_SVD_BACKWARD_ERROR")
                spectra[s].append(report)
                for suffix, value in (("U", U), ("s", sigma), ("Vh", Vh)):
                    S[f"{s}_{a}_{suffix}"] = value
        denominator = tensor_record["original_full_scattered_E_denominator"]
        defect = float(np.sqrt(sum(np.linalg.norm(saved["full_"+s]-saved["independent_"+s])**2 for s in "xyz")))
        bounds = {name: rank_bound(spectra, ranks, denominator, defect)
                  for name, ranks in (("pure_r8", [8,64,8]), ("width16", [8,17,8]), ("cheb19", [8,19,8]))}
        spectral = phase(artifact, "spectra", dict(spectra=spectra, bounds=bounds,
            necessary_ranks=necessary_ranks(spectra, denominator, defect),
            measured_input_pair_defect_norm=defect, tensor_record_sha256=digest(ART / "v40_interior_moment_tensor/interior_tensor.json"),
            rank_scope=tensor_record["rank_scope"], status="DIAGNOSTIC_FULL_SPECTRUM_FROZEN"), **S)
        marker("full_spectra_frozen", dict(shape_bytes=sum(v.nbytes for v in S.values())))
        from src.solvers.ftt_feature_capacity import feature_spaces, chebyshev_spaces
        from src.solvers.ftt_field import FTTField
        from src.solvers.optimization_checkpoint import load_checkpoint
        from src.postprocessing.ftt_verification import validate_checkpoint_identity
        features, Fsave = {}, {}
        bounds_nm = design["model"]["geometry"]["bounds_nm"]
        cells = design["model"]["geometry"]["cells"]
        for name in ("native_final", "fit_final", "chebyshev"):
            if name == "chebyshev":
                bases, records, values = chebyshev_spaces(tensors, bounds_nm, cells)
            else:
                parent = design["parents"][name]
                candidate = json.loads(checked_file(parent["result"]).read_text())
                model = FTTField(bounds_nm, "fttnn")
                state = load_checkpoint(checked_file(parent["checkpoint"]), parent["checkpoint"]["sha256"])
                validate_checkpoint_identity(state, candidate, model, name == "fit_final")
                model.load_state_dict(state["model"], strict=True)
                bases, records, values = feature_spaces(model, tensors, bounds_nm, cells)
            bound = feature_bound(tensors, bases, denominator, defect)
            stable = all(r["finite_functional_space_qualified"] for rows in records.values() for r in rows)
            actual_FP64 = all(r["actual_FP64_arbitrary_output_certificate"] for rows in records.values() for r in rows)
            bound.update(axis_feature_records=records, finite_chart_full_space_qualified=stable,
                full_space_qualified=bool(stable and actual_FP64 and tensor_record["rank_bound_transferable_to_actual_FE"]),
                actual_FE_certificate=False if not tensor_record["rank_bound_transferable_to_actual_FE"] else bool(stable and actual_FP64),
                conditional_cartesian_chart_only=not tensor_record["rank_bound_transferable_to_actual_FE"],
                reference_exposed=True, pde_only_solve=False, production_initialization_allowed=False,
                numerical_margin=bounds["pure_r8"]["numerical_margin"], original_parent=design["parents"].get(name))
            features[name] = bound
            Fsave.update({name+"_"+k: value for k, value in values.items()})
            phase(artifact, "features_"+name, bound, **values)
            marker("frozen_axis_features_completed", dict(state=name, qualified_actual_FE=bound["full_space_qualified"]))
        return phase(artifact, "features", dict(records=features, spectra_record=spectral,
                     reference_exposed=True, status="DIAGNOSTIC_FEATURES_FROZEN"), **Fsave)
    if role == "ftt_capacity_decision":
        from benchmarks.check_ftt_capacity import check_saved
        checked = check_saved(ART, frozen_design=dict(
            path=str(DESIGN.relative_to(ROOT)), sha256=manifest['design_sha256']))
        phase(artifact, "saved_checker", checked)
        return dict(status="DIAGNOSTIC_COMPLETE", decision=checked["decision"],
                    saved_checker=checked, future_training_authorized=False,
                    next_production_candidate="NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE")
    raise ValueError("UNKNOWN_CAPACITY_DIAGNOSTIC_ROLE")


def main():
    directory = ROOT / Path(sys.argv[1])
    manifest = json.loads((directory / "run_manifest.json").read_text())
    artifact = ROOT / manifest["artifact"]
    from src.runners.neural_wave_worker import abi, publish_event
    started = monotonic()
    def marker(stage, values):
        publish_event(directory, stage, values)
    try:
        atomic_json(directory / "abi.json", abi(manifest["spec"]["mode"]))
        result = run_stage(manifest, artifact, marker)
        result.update(source_sha=manifest["source_sha"], input_sha256=manifest["input_sha256"],
            design_sha256=manifest["design_sha256"], worker_elapsed_seconds=monotonic()-started,
            result_kind="DIAGNOSTIC", reference_exposed=manifest["spec"]["role"]!="ftt_capacity_checks",
            reference_used_for_training=False, new_training_count=0, forward_solve_count=0,
            global_Maxwell_factor_count=0, global_Gram_factor_count=0, Gsolve_count=0,
            pde_only_solve=False, production_initialization_allowed=False,
            pde_only_solver_qualified=False, official_candidate_results=False,
            full_original_target_qualified=False)
        atomic_json(artifact / "result.json", result)
        marker("stage_frozen", dict(result_sha256=digest(artifact / "result.json")))
    except BaseException as error:
        atomic_json(artifact / ("failure_"+directory.name+".json"), dict(
            error=repr(error), traceback=traceback.format_exc(), source_sha=manifest["source_sha"],
            worker_elapsed_seconds=monotonic()-started, status="FAILED_NOT_RECLASSIFIED"))
        raise


if __name__ == "__main__":
    main()
