"""Thin V23 dispatch into local components/checkers, never a field solver."""


def run_stage(manifest, artifact, marker, budget):
    from benchmarks.portable_facet_checks import admission_audit
    from src.io.fixed_phase_pilot import ROOT

    if manifest["stage"] == "v23_admission_audit":
        return admission_audit(ROOT, artifact, marker, budget)
    if manifest["stage"] == "v23_saved_checker":
        from benchmarks.portable_facet_audit import audit

        return audit(ROOT, artifact, marker, budget)
    from benchmarks.portable_facet_lifecycle import qualify, cold_lifecycle

    if manifest["stage"] == "v23_facet_qualification":
        return qualify(ROOT, artifact, marker, budget)
    implementations = {"v23_analytic_cold": "analytic", "v23_q60_cold": "q60"}
    if manifest["stage"] in implementations:
        return cold_lifecycle(
            ROOT, artifact, marker, budget, implementations[manifest["stage"]]
        )
    raise ValueError("V23_EXPLICIT_COMPONENT_STAGE_REQUIRED")
