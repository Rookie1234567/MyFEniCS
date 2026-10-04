"""Independent compact qualification/benchmarks for a local facet component.

No Maxwell assembly, inverse, training, or full target-mode inventory here.
"""

import hashlib
import json
from pathlib import Path

import numpy as np

from src.solvers.strict_port_admission import qualification, digest_file


def binding(path):
    path = Path(path)
    return dict(path=str(path), sha256=digest_file(path), bytes=path.stat().st_size)


def array_digest(value):
    value = np.ascontiguousarray(value)
    h = hashlib.sha256(str(value.dtype).encode() + str(value.shape).encode())
    h.update(value.tobytes())
    return h.hexdigest()


def admission_audit(root, artifact, marker, budget):
    """Derive new rejection states from accepted receipts; no field re-action."""
    from src.runners.fixed_phase_campaign import write, v22_admission
    from src.solvers.fixed_phase_reliable_ports import correction

    records = root / "docs/task042extra_feinn_5nm/outcomes/records"
    audit = json.loads((records / "review_v22_evidence_audit.json").read_text())
    gate = json.loads((records / "gate_decisions_v22.json").read_text())
    frozen = json.loads((root / "tmp/task42extra/v23/frozen_inputs.json").read_text())
    for item in frozen.values():
        assert digest_file(item["path"]) == item["sha256"], "V23_FROZEN_INPUT_CHANGED"
    design_path = root / "input/task042extra_feinn_5nm/design_v20.json"
    design = json.loads(design_path.read_text())
    roles = {}
    for role in ("E3", "E4"):
        budget("strict_saved_role_" + role)
        path = (
            root
            / "benchmarks/artifacts/task42extra"
            / ("index_v22_" + role.lower() + "_correction_attempt1.json")
        )
        assert digest_file(path) == frozen[role.lower() + "_index"]["sha256"], (
            "CALLER_FROZEN_ROLE_INDEX_CHANGED"
        )
        index = json.loads(path.read_text())
        files = {
            k: binding(index["files"][k]["path"])
            for k in ("native", "field", "observables")
        }
        for k in files:
            assert files[k]["sha256"] == index["files"][k]["sha256"]
        files.update(
            gate=binding(records / "gate_decisions_v22.json"),
            review=binding(records / "review_v22_evidence_audit.json"),
        )
        with np.load(files["field"]["path"], allow_pickle=False) as state:
            background = array_digest(state["background"])
            low = array_digest(state["total_lo"])
        with np.load(files["observables"]["path"], allow_pickle=False) as state:
            modes = array_digest(state["mode_keys"])
        expected = dict(
            material=hashlib.sha256(
                json.dumps(design["models"]["G0"]["materials"], sort_keys=True).encode()
            ).hexdigest(),
            modes=modes,
            background=background,
            total_lo=low,
            native=files["native"]["sha256"],
            source="c3844846435764cd0ca7a4351a1ba8374373b6ae",
            files=files,
        )
        original = gate["corrected_original_equations"][role]
        arithmetic = original["arithmetic"]
        physical = original["physical_origin_sensitivity"]["rows"]
        reused = audit["raw_recomputation"]["conditioning"][role]
        equation = index["result"]["full_equation"]
        # These are already accepted measurements, never a new dot/factor.
        metrics = dict(
            stored_operator_arithmetic=max(
                arithmetic["rows"][name]["original_coordinates_relative"]
                for name in ("scattered", "background", "total")
            ),
            oracle_self_consistency=max(
                v["oracle1_vs_oracle2"]
                for k, v in reused.items()
                if k.startswith("corrected_")
            ),
            actual_vector_projection=max(
                r["original_coordinates_relative"] for r in physical.values()
            ),
            original_equation=max(
                equation[k]
                for k in (
                    "native_relative",
                    "augmented_relative",
                    "original_total_augmented_relative",
                    "independent_physical_weak",
                )
            ),
            MPC=max(index["result"]["MPC"]),
            affine=None,
        )
        # The exact-sum boolean is not a retained relative scalar bound.
        proof = dict(
            schema="strict_port_qualification.v1",
            identity={k: v for k, v in expected.items() if k != "files"},
            files=files,
            metrics=metrics,
            shared_physics=gate["P2"]["shared"],
            role_component=gate["P2"]["roles"][role],
            all_consumers=index["result"]["complete_output_qualified"],
        )
        state = qualification(proof, expected)
        rejected = {}
        for label, call in (
            (
                "campaign",
                lambda: v22_admission(
                    "v22_" + role.lower() + "_correction",
                    [],
                    strict_evidence=proof,
                    current_expected=expected,
                ),
            ),
            (
                "direct",
                lambda: correction(
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    strict_evidence=proof,
                    current_expected=expected,
                ),
            ),
        ):
            try:
                call()
            except RuntimeError as exc:
                rejected[label] = str(exc)
            else:
                raise AssertionError("V23_SOLVE_GUARD_SENTINEL_REACHED")
        roles[role] = dict(
            expected=expected,
            evidence=proof,
            derived=state,
            entry_rejections=rejected,
            old_index=binding(path),
            legacy_status_unchanged=True,
            unknown_fields=["affine"],
        )
        marker("strict_negative_role_saved", dict(role=role, failed=state["failed"]))
    target = artifact / "strict_roles.json"
    write(target, roles)
    return dict(
        audit_completed=True,
        readable_negative_fields=True,
        component_passed=False,
        strict_complete_qualified=False,
        solve_admitted=False,
        stage_qualified=False,
        strict_guard_tests_passed=all(
            len(r["entry_rejections"]) == 2 for r in roles.values()
        ),
        new_Maxwell_factor_solve_Gram_training=0,
        old_data_unchanged=True,
        reused_audit=binding(records / "review_v22_evidence_audit.json"),
    ), dict(strict_roles=target)
