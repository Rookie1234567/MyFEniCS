"""Independent FE reference scoring: export only predeclared scalar feedback.

No Torch import or network training. Full reference arrays stay in a separate
artifact directory which the training process cannot open.
"""

import json
import sys
from pathlib import Path
import numpy as np
from src.io.neural_wave_campaign import ROOT, digest
from src.solvers.neural_wave_greedy import atomic_json

FIELDS = {"schema", "round", "boundary_sha256", "field_sha256", "source_sha",
          "design_sha256", "native_relative", "augmented_relative",
          "scattered_E_relative", "scattered_H_relative", "scattered_curl_relative",
          "reference_feedback", "production_initialization_allowed"}


def read_scalars(path, request):
    value = json.loads(Path(path).read_text())
    if set(value) != FIELDS or value["schema"] != "ftt.bloch-validation.scalars.v1":
        raise ValueError("BLOCH_NONSCALAR_OR_UNREGISTERED_REFERENCE_FEEDBACK")
    for key in ("round", "boundary_sha256", "field_sha256", "source_sha", "design_sha256"):
        if value[key] != request[key]:
            raise ValueError("BLOCH_REFERENCE_SCALAR_BOUNDARY_MISMATCH:" + key)
    numbers = [value[k] for k in FIELDS if k.endswith("_relative")]
    if not np.isfinite(numbers).all() or min(numbers) < 0 or value["production_initialization_allowed"] or value["reference_feedback"] != "scalars_only":
        raise ValueError("BLOCH_SCALAR_VALUES_OR_USE_FLAGS_INVALID")
    return value


def score(request_file, isolated, scalar_file):
    from src.io.ftt_bloch_campaign import DESIGN
    from src.io.ftt_campaign import load_files
    from src.runners.ftt_worker import load_arrays, ftt_abi
    from src.solvers.feinn_native import load_native
    from src.solvers.feinn_fem import build_model
    from src.postprocessing.neural_wave_audit import save_complete_field_samples, relative_error
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action

    request = json.loads(Path(request_file).read_text())
    design = json.loads(DESIGN.read_text())
    if digest(DESIGN) != request["design_sha256"] or request["production_initialization_allowed"]:
        raise ValueError("BLOCH_SCORING_REQUEST_IDENTITY")
    field = ROOT / request["field_path"]
    if digest(field) != request["field_sha256"]:
        raise ValueError("BLOCH_SCORING_FIELD_HASH")
    isolated.mkdir(parents=True, exist_ok=False)
    atomic_json(isolated / "abi.json", ftt_abi("fe"))
    files = load_files(design)
    action = load_native(files["native"])
    packet = load_arrays(files["moments_q30"])
    with np.load(field, allow_pickle=False) as z:
        c, r = np.array(z["c"]), np.array(z["r"])
    if np.linalg.norm(action.apply(c) - action.f - r) / action.bnorm > 1e-10:
        raise ValueError("BLOCH_SCALAR_ORIGINAL_RESIDUAL_PAIR")
    path = ROOT / design["reference"]["path"]
    if digest(path) != design["reference"]["sha256"]:
        raise ValueError("BLOCH_SCALAR_SAME_P3_REFERENCE_HASH")
    with np.load(path, allow_pickle=False) as z:
        reference = np.array(z["c"])
    model = build_model(design["model"])
    try:
        for key, expected in design["native_identity"].items():
            if model["record"][key] != expected:
                raise ValueError("BLOCH_SCALAR_PHYSICAL_IDENTITY:" + key)
        raw, _ = save_complete_field_samples(model, action, packet, reference, {"CANDIDATE": c}, isolated, lambda *_: None)
        with np.load(raw, allow_pickle=False) as z:
            errors = {k: relative_error(z["CANDIDATE_" + k] - z["REFERENCE_" + k], z["REFERENCE_" + k], weights=z["weights"])["relative"] for k in ("E", "curl")}
        audit = action.audit(c)
        value = dict(schema="ftt.bloch-validation.scalars.v1", **{k: request[k] for k in ("round", "boundary_sha256", "field_sha256", "source_sha", "design_sha256")},
            native_relative=audit["native_relative"], augmented_relative=audit["augmented_relative"],
            scattered_E_relative=errors["E"], scattered_H_relative=errors["curl"], scattered_curl_relative=errors["curl"],
            reference_feedback="scalars_only", production_initialization_allowed=False)
        # The original model has constant mu: H=(i k0 mu)^-1 curl E;
        # hence the H and curl relative norms use the identical actual denominator.
        atomic_json(isolated / "scoring_receipt.json", dict(request=request, scalars=value,
            raw=dict(path=str(raw.relative_to(ROOT)), sha256=digest(raw)),
            H_relative_equals_curl_for_original_constant_mu=True, reference_solve_count=0,
            production_initialization_allowed=False))
        atomic_json(scalar_file, value)
    finally:
        destroy_same_mesh_physical_action(model["bundle"])


if __name__ == "__main__":
    score(ROOT / sys.argv[1], ROOT / sys.argv[2], ROOT / sys.argv[3])
