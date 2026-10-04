"""Thin V23 dispatch into local components/checkers, never a field solver."""


def run_stage(manifest, artifact, marker, budget):
    from benchmarks.portable_facet_checks import admission_audit
    from src.io.fixed_phase_pilot import ROOT

    if manifest["stage"] == "v23_admission_audit":
        return admission_audit(ROOT, artifact, marker, budget)
    raise ValueError("V23_EXPLICIT_COMPONENT_STAGE_REQUIRED")
