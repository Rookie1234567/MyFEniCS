"""Compare-only reconstruction of real, unqualified saved direct states.

No state is corrected, no algebra gate is waived and no factor is repeated.
This supplies the independent C diagnostics required when B saved a negative.
"""

import json
from pathlib import Path
import numpy as np


def choose_closed_negative(root, role):
    choices = []
    for directory in sorted(
        (root / "results/task42extra").glob("task42extra_v20_" + role.lower() + "_*")
    ):
        manifest = directory / "run_manifest.json"
        summary = directory / "run_summary.json"
        if not manifest.exists() or not summary.exists():
            continue
        m = json.loads(manifest.read_text())
        s = json.loads(summary.read_text())
        artifact = Path(m["artifact_directory"])
        if (
            m.get("role") != role
            or m.get("stage") != "v20_" + role.lower()
            or m.get("group") != "B"
            or not artifact.resolve().is_relative_to(
                (root / "benchmarks/artifacts/task42extra").resolve()
            )
        ):
            raise ValueError("NEGATIVE_SOURCE_ROLE_OR_ARTIFACT_SCOPE")
        if (
            not s.get("descendants_cleared")
            or not (directory / "worker_failure.json").exists()
            or not all(
                (artifact / k).exists()
                for k in ("field_state.npz", "native.npz", "identity.json")
            )
        ):
            continue
        failure = json.loads((directory / "worker_failure.json").read_text())
        if failure["source_sha"] != m["source_sha"]:
            raise ValueError("NEGATIVE_SOURCE_IDENTITY")
        events = [
            json.loads(row)
            for row in (directory / "events.jsonl").read_text().splitlines()
        ]
        release = [
            r["values"]
            for r in events
            if r["phase"] == "reference_release_before_postprocessing"
        ]
        if (
            not release
            or not release[-1].get("factor_released")
            or not release[-1].get("matrix_released")
        ):
            continue
        if (
            release[-1]["rss_after_release_bytes"]
            >= release[-1]["rss_before_release_bytes"]
        ):
            continue
        choices.append(
            dict(
                directory=directory,
                artifact=artifact,
                manifest=m,
                release=release[-1],
                failure=failure,
            )
        )
    return choices[-1] if choices else None


def inspect_state(packet, state):
    required = {
        "c_scattered",
        "c_total",
        "alpha_scattered",
        "alpha_total",
        "background",
        "background_alpha",
        "masters",
    }
    if set(state) != required:
        raise ValueError("NEGATIVE_SAVED_STATE_LAYOUT")
    for name in ("c_scattered", "c_total", "background"):
        if (
            state[name].shape != (packet.size,)
            or state[name].dtype != np.complex128
            or not np.isfinite(state[name]).all()
        ):
            raise ValueError("NEGATIVE_SAVED_FE_LAYOUT")
    for name in ("alpha_scattered", "alpha_total", "background_alpha"):
        if (
            state[name].shape != (packet.np,)
            or state[name].dtype != np.complex128
            or not np.isfinite(state[name]).all()
        ):
            raise ValueError("NEGATIVE_SAVED_PORT_LAYOUT")
    if not np.array_equal(state["masters"], packet.a["masters"]):
        raise ValueError("NEGATIVE_SAVED_MASTER_ORDER")
    for a, b in (
        ("background", "background"),
        ("background_alpha", "background_alpha"),
    ):
        if not np.array_equal(state[a], packet.a[b]):
            raise ValueError("NEGATIVE_SAVED_BACKGROUND_IDENTITY")
    if not np.array_equal(
        state["c_total"], state["c_scattered"] + state["background"]
    ) or not np.array_equal(
        state["alpha_total"], state["alpha_scattered"] + state["background_alpha"]
    ):
        raise ValueError("NEGATIVE_SAVED_AFFINE_IDENTITY")


def native_without_fields(root, existing):
    """Audit retained packets for roles which never produced a field."""
    from benchmarks.fixed_phase_checker import interior_port_support
    from src.runners.fixed_phase_campaign import sha

    records = {}
    for role in ("O3", "E3", "E4", "O6"):
        if role in existing:
            continue
        for directory in sorted(
            (root / "results/task42extra").glob(
                "task42extra_v20_" + role.lower() + "_*"
            )
        ):
            paths = {
                k: directory / name
                for k, name in (
                    ("manifest", "run_manifest.json"),
                    ("summary", "run_summary.json"),
                    ("failure", "worker_failure.json"),
                )
            }
            if not all(p.is_file() for p in paths.values()):
                continue
            manifest, summary, failure = (
                json.loads(paths[k].read_text()) for k in paths
            )
            artifact = Path(manifest["artifact_directory"])
            if (
                manifest["role"] != role
                or manifest["group"] != "B"
                or not artifact.resolve().is_relative_to(
                    (root / "benchmarks/artifacts/task42extra").resolve()
                )
                or failure["source_sha"] != manifest["source_sha"]
            ):
                raise ValueError("NATIVE_WITHOUT_FIELD_SOURCE")
            if (
                not summary["descendants_cleared"]
                or (artifact / "field_state.npz").exists()
                or not (artifact / "native.npz").exists()
            ):
                continue
            paths["native"] = artifact / "native.npz"
            with np.load(paths["native"], allow_pickle=False) as z:
                arrays = {
                    k: np.array(z[k])
                    for k in ("masters", "idofs", "br", "bv", "dr", "dv")
                }
            records[role] = dict(
                source_sha=manifest["source_sha"],
                original_failure=failure["reason"],
                field_status="NOT_RETAINED_NO_SAVED_VECTOR",
                original_files={
                    k: dict(path=str(p), sha256=sha(p)) for k, p in paths.items()
                },
                port_support=interior_port_support(arrays),
            )
    return records


def negative_indices(root, target, existing, marker, budget, source):
    from src.solvers.fixed_phase_reference import ROLES
    from src.solvers.fixed_phase_fem import build_model
    from src.geometry.fixed_phase_plan import physical_design
    from src.solvers.feinn_native import load_native
    from src.solvers.fixed_phase_audit import (
        PhysicalVolumeAudit,
        surface_blocks,
        incident_rhs,
    )
    from src.solvers.fixed_phase_comparison import self_physics
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from src.runners.fixed_phase_campaign import write, sha
    from benchmarks.fixed_phase_checker import solved

    for role, (mesh, degree, phase) in ROLES.items():
        if role in existing:
            continue
        chosen = choose_closed_negative(root, role)
        if chosen is None:
            marker(
                "negative_role_not_retained",
                dict(role=role, status="NOT_RETAINED_OR_NOT_RUN"),
            )
            continue
        artifact = chosen["artifact"]
        budget("independent negative reconstruction")
        original = {
            k: dict(path=str(artifact / name), sha256=sha(artifact / name))
            for k, name in [
                ("native", "native.npz"),
                ("field", "field_state.npz"),
                ("identity", "identity.json"),
            ]
        }
        original["failure"] = dict(
            path=str(chosen["directory"] / "worker_failure.json"),
            sha256=sha(chosen["directory"] / "worker_failure.json"),
        )
        identity = json.loads((artifact / "identity.json").read_text())
        model = build_model(physical_design(mesh), degree, phase, operators=False)
        for k in (
            "physical_model_sha256",
            "mesh_coordinates_sha256",
            "geometry_cell_dofs_sha256",
            "cell_tags_sha256",
            "mode_manifest_sha256",
            "degree",
            "native_rows",
            "slaves",
        ):
            if model["record"][k] != identity[k]:
                raise ValueError("NEGATIVE_PHYSICAL_OR_DISCRETE_IDENTITY:" + k)
        p = load_native(artifact / "native.npz")
        with np.load(artifact / "field_state.npz", allow_pickle=False) as z:
            state = {k: np.array(z[k]) for k in z.files}
        inspect_state(p, state)
        if not np.array_equal(model["space"].dofmap.list, p.a["cell_dofs"]):
            raise ValueError("NEGATIVE_CELL_DOF_ORDER")
        c, alpha = state["c_scattered"], state["alpha_scattered"]
        normal = p.audit(c)
        raw_top = p.volume(c) + p.B(alpha) - p.a["g"]
        raw_bottom = -p.D(c) + p.a["H"] * alpha - p.a["gp"]
        augmented = float(
            np.linalg.norm(np.r_[raw_top, raw_bottom]) / np.linalg.norm(p.a["g"])
        )
        total, atotal = state["c_total"], state["alpha_total"]
        tr = p.volume(total) + p.B(atotal) - p.a["total_g"]
        tb = -p.D(total) + p.a["H"] * atotal
        total_r = float(np.linalg.norm(np.r_[tr, tb]) / np.linalg.norm(p.a["total_g"]))
        va = PhysicalVolumeAudit(model, p)
        B, D, H = surface_blocks(model, p)
        rhs = incident_rhs(model, p, B)
        from src.solvers.fixed_phase_audit import block_pair

        rhs_pair = float(np.linalg.norm(rhs - p.a["total_g"]) / np.linalg.norm(rhs))
        port_pair = block_pair(p, B, D, H)
        if not port_pair["passed"] or rhs_pair > 1e-10:
            raise ValueError("NEGATIVE_REBUILD_PHYSICAL_PORT_OR_RHS_NOT_PAIRED")
        independent = float(
            np.linalg.norm(
                np.r_[va.volume(total) + B @ atotal - rhs, -D @ total + H * atotal]
            )
            / np.linalg.norm(rhs)
        )
        restored = restore_p0_full_field(model["floquet"], p.storage(total))
        local = p.expand(total)
        mpc = float(
            np.linalg.norm(restored.x.array[p.a["cell_dofs"]] - local)
            / max(np.linalg.norm(local), 1e-30)
        )
        expected_alpha = p.alpha(c)
        port = float(
            np.linalg.norm(expected_alpha - alpha) / max(np.linalg.norm(alpha), 1e-12)
        )
        from src.solvers.dtn_port_3d import _mode_boundary_phase

        phase_values = np.asarray(
            [_mode_boundary_phase(m, model["cfg"]) for m in model["bundle"]["modes"]]
        )
        beta = phase_values * alpha
        beta_expected = phase_values * expected_alpha
        port_observation = dict(
            original_coordinate_relative=port,
            boundary_coordinate_relative=float(
                np.linalg.norm(beta - beta_expected) / max(np.linalg.norm(beta), 1e-12)
            ),
            boundary_max_absolute=float(np.max(abs(beta - beta_expected))),
            original_alpha_norm=float(np.linalg.norm(alpha)),
            boundary_alpha_norm=float(np.linalg.norm(beta)),
            original_H_min=float(p.a["H"].min()),
            boundary_phase_min=float(abs(phase_values).min()),
            diagnostic_only_original_gate_unchanged=True,
        )
        worst = np.argsort(abs(alpha - expected_alpha))[-3:][::-1]
        port_observation["dominant_original_error_modes"] = [
            dict(
                key=[
                    model["bundle"]["modes"][j].side,
                    model["bundle"]["modes"][j].m,
                    model["bundle"]["modes"][j].n,
                    model["bundle"]["modes"][j].polarization,
                ],
                alpha_difference_absolute=float(abs(alpha[j] - expected_alpha[j])),
                boundary_difference_absolute=float(abs(beta[j] - beta_expected[j])),
                boundary_expected_absolute=float(abs(beta_expected[j])),
                H=float(p.a["H"][j]),
            )
            for j in worst
        ]
        full = dict(
            native_relative=normal["native_relative"],
            augmented_relative=augmented,
            original_total_augmented_relative=total_r,
            independent_physical_weak=independent,
            recovery=max(
                port, mpc, chosen["release"].get("original_port_recovery_relative", 0)
            ),
            channels=p.np,
            full_FE_recovered=True,
        )
        checker = solved(full, reference=role == "O6")
        output = target / ("saved_negative_" + role)
        output.mkdir()
        physics = self_physics(model, p, c, alpha, output, marker, budget)
        record = dict(
            schema="fixed_phase.negative-saved-reconstruction.v1",
            source_sha=chosen["manifest"]["source_sha"],
            audit_source_sha=source,
            result=dict(
                stage_qualified=False,
                role=role,
                identity=identity,
                full_equation=full,
                checker=checker,
                physics=physics,
                original_failure=chosen["failure"],
                deterministic_direct=chosen["release"],
                state_unchanged=True,
                no_new_solve_or_factor=True,
                not_official=True,
                MPC_relative=mpc,
                original_port_recovery_relative=port,
                port_coordinate_observation=port_observation,
                neural_gain="NOT_TESTED",
                independent_ports=port_pair,
                independent_rhs_relative=rhs_pair,
                audit_counts=dict(p.counts),
            ),
            files=original,
        )
        record["files"]["observables"] = dict(
            path=str(output / "observables.npz"), sha256=sha(output / "observables.npz")
        )
        for k, v in original.items():
            if sha(v["path"]) != v["sha256"]:
                raise ValueError("NEGATIVE_ORIGINAL_SAVED_STATE_CHANGED")
        write(output / "index.json", record)
        existing[role] = record
        marker(
            "saved_negative_physical_diagnostic_frozen",
            dict(
                role=role,
                full_equation=full,
                preserved_failure=chosen["failure"]["reason"],
                field_sha256=original["field"]["sha256"],
                A_counts=p.counts,
            ),
        )
        del model, p, va, B, D, H, rhs, state, restored, local, c, alpha, total, atotal
        import gc

        gc.collect()
    return existing
