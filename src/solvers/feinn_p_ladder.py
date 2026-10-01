"""New-order reference audit orchestration, reusing qualified physical code."""

from copy import deepcopy
from dataclasses import replace
import gc
from pathlib import Path

import numpy as np

from src.solvers.feinn_discretization_audit import (
    POLICY,
    atomic_npz,
    clock,
    embedding_check,
    load_p3,
    measured_families,
    verify_model,
)
from src.solvers.feinn_exact_condensation import ExactInteriorCondensation, capacity
from src.solvers.feinn_native import load_native
from src.solvers.feinn_riesz import rss_bytes


def checks(design, native, reference, artifact, marker, manifest):
    import basix.ufl
    from dolfinx import fem
    from scipy.sparse.linalg import spsolve
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.feinn_interpolation import full_space
    from src.solvers.feinn_fem import build_model, export_native, native_gate
    from src.solvers.feinn_authority_assembly import BasixVolumeAudit, packet_csr
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    tick, cutoff = clock(manifest)
    _, _, original = load_p3(native, reference)
    plan = capacity(384, 5)
    marker("p5_preallocation_capacity", dict(plan, measured_rss_bytes=rss_bytes()))
    if rss_bytes() + plan["allocation_upper_bytes"] >= 12 * 2**30:
        raise RuntimeError("P5_RESOURCE_BLOCKED_BEFORE_ARRAYS")
    small = deepcopy(design)
    small["geometry"]["cells"] = [2, 2, 2]
    cfg, data, s4, *_ = full_space(small, 4)
    s5 = fem.functionspace(data.mesh, basix.ufl.element("N1curl", "hexahedron", 5))
    f4 = build_double_floquet_mpc(s4, data, cfg)
    f5 = build_double_floquet_mpc(s5, data, replace(cfg, nedelec_degree=5))
    transfer = embedding_check(data, s4, f4, s5, f5, seed=421901)
    if not transfer["passed"]:
        raise ValueError("P4_P5_EMBEDDING_FAILED")
    del data, s4, s5, f4, f5
    gc.collect()
    tick("small exact condensation")
    sm = build_model(small, degree=5, marker=marker, dtn_quadrature_degree=15)
    try:
        p, _ = export_native(sm, marker)
        reduced = ExactInteriorCondensation(
            p, sm["space"].element.basix_element.entity_dofs[3][0]
        )
        M, pair = reduced.assemble(marker=marker)
        z = spsolve(M, reduced.rhs)
        full = np.r_[*reduced.recover(z)]
        direct, _ = packet_csr(sm, p, marker)
        zfull = spsolve(direct, np.r_[p.a["g"], p.a["gp"]])
        small_pair = float(np.linalg.norm(full - zfull) / np.linalg.norm(zfull))
        small_residual = float(
            np.linalg.norm(direct @ full - np.r_[p.a["g"], p.a["gp"]])
            / np.linalg.norm(np.r_[p.a["g"], p.a["gp"]])
        )
        import ufl
        from src.solvers.feinn_bounded_field_integrals import BoundedFieldIntegrals
        from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
            restore_p0_full_field,
        )

        field = restore_p0_full_field(sm["floquet"], p.storage(full[: p.size]))
        dx = ufl.Measure(
            "dx", domain=sm["data"].mesh, metadata={"quadrature_degree": 15}
        )
        original_energy = np.array(
            [
                fem.assemble_scalar(fem.form(term * dx)).real
                for term in (
                    ufl.inner(field, field),
                    ufl.inner(ufl.curl(field), ufl.curl(field)) / sm["cfg"].k0 ** 2,
                )
            ]
        )
        bounded_energy = BoundedFieldIntegrals(sm["data"].mesh, sm["cfg"].k0).energies(
            field
        )
        integral_pair = float(
            np.linalg.norm(original_energy - bounded_energy)
            / np.linalg.norm(original_energy)
        )
        if max(pair, small_pair, small_residual, integral_pair) > 1e-10:
            raise ValueError("SMALL_EXACT_CONDENSATION_FAILED")
    finally:
        destroy_same_mesh_physical_action(sm["bundle"])
    del sm, p, reduced, M, direct, full, z, zfull
    gc.collect()
    tick("M5 p5")
    model = build_model(design, degree=5, marker=marker, dtn_quadrature_degree=15)
    try:
        equivalence = verify_model(model, original)
        equivalence["physical_parameters"]["physical_configuration_source"] = (
            "unchanged frozen design; only degree=5"
        )
        packet, identity = export_native(model, marker)
        families = measured_families(model["space"], packet)
        action = native_gate(model, packet)
        independent = BasixVolumeAudit(model, packet).check(seed=421905)
        if action["status"] != "PASS" or not independent["passed"]:
            raise ValueError("P5_INDEPENDENT_ACTION_FAILED")
        path = artifact / "p5_native.npz"
        atomic_npz(path, **packet.a)
        return dict(
            status="P_TRANSFER_CAPACITY_PASS",
            degree=5,
            identity=identity,
            independent_families=families,
            physics_equivalence_fields=equivalence,
            small_p4_p5_transfer=transfer,
            small_condensation=dict(
                relative=small_pair,
                original_augmented_residual=small_residual,
                reduced_action_relative=pair,
                bounded_integral_pair_relative=integral_pair,
            ),
            action=action,
            independent_integration=independent,
            array_capacity=plan,
            numeric_cutoff_monotonic=cutoff,
            new_Gram_matrix_count=0,
            new_Gram_factor_count=0,
            counts=packet.counts,
            **POLICY,
        ), dict(native=path)
    finally:
        destroy_same_mesh_physical_action(model["bundle"])


def reference(design, native, p3_reference, checks_index, artifact, marker, manifest):
    from src.solvers.feinn_authority_assembly import BasixVolumeAudit
    from src.solvers.feinn_discretization_audit import reference as authority

    def options(model, packet, output, mark):
        reduced = ExactInteriorCondensation(
            packet, model["space"].element.basix_element.entity_dofs[3][0]
        )

        def assemble(m, p, marker):
            return reduced.assemble(
                m, p, marker, save=output / "p5_condensed_csr_recovery.npz"
            )

        return dict(
            reduced_system=reduced,
            assembler=assemble,
            allocation_upper_bytes=capacity(packet.nc, 5, classes=len(packet.a["F"]))[
                "allocation_upper_bytes"
            ],
        )

    result, files = authority(
        design,
        native,
        p3_reference,
        checks_index,
        artifact,
        marker,
        manifest,
        degree=5,
        solve_options=options,
        independent_factory=BasixVolumeAudit,
    )
    result["degree"] = 5
    result["status"] = (
        "P5_REFERENCE_QUALIFIED"
        if result["reference_qualified"]
        else "P5_REFERENCE_FAILED"
    )
    result["c_scattered_meaning"] = (
        "all independent p5 scattering FE coefficients; no background/slaves"
    )
    result["physics_equivalence_fields"]["physical_parameters"][
        "physical_configuration_source"
    ] = "unchanged frozen design; only degree=5"
    files["condensed_csr_recovery"] = artifact / "p5_condensed_csr_recovery.npz"
    # The generic historical authority uses a p4 filename; publish this run under
    # an explicit new p5 name without touching any historical artifact.
    old = files["reference"]
    new = artifact / "p5_reference_state.npz"
    Path(old).rename(new)
    files["reference"] = new
    result["p5_native_sha256"] = result.pop("p4_native_sha256")
    result["p5_reference_sha256"] = result.pop("p4_reference_sha256")
    return result, files


def compare(
    design,
    old_native,
    old_reference,
    checks_index,
    new_reference,
    artifact,
    marker,
    manifest,
):
    from src.solvers.feinn_discretization_audit import compare as compare_orders
    from src.runners.feinn_workflow import sha

    def load_old(native_index, reference_index):
        expected = (
            "062137c4c5be83b62be6a5373cfa24244f203f0b37244aeb4fb0b8feb75eb9ad",
            "249d7dcb4f683a87e4a5169bc75f5bcf9374ca64e2075910c3a874d88e1cc2c2",
        )
        for key, idx, h in (
            ("native", native_index, expected[0]),
            ("reference", reference_index, expected[1]),
        ):
            if idx["files"][key]["sha256"] != h or sha(idx["files"][key]["path"]) != h:
                raise ValueError("P4_FROZEN_IDENTITY_FAILED")
        p = load_native(native_index["files"]["native"]["path"])
        with np.load(
            reference_index["files"]["reference"]["path"], allow_pickle=False
        ) as z:
            c = np.array(z["c_scattered"])
        return p, c, dict(identity=native_index["result"]["identity"])

    result, files = compare_orders(
        design,
        old_native,
        old_reference,
        checks_index,
        new_reference,
        artifact,
        marker,
        manifest,
        left_degree=4,
        right_degree=5,
        left_loader=load_old,
        bounded_integrals=True,
    )

    def rename(value):
        if isinstance(value, dict):
            return {
                k.replace("p4", "p5").replace("p3", "p4"): rename(v)
                for k, v in value.items()
            }
        if isinstance(value, str):
            return (
                value.replace("P3_P4", "P4_P5").replace("p4", "p5").replace("p3", "p4")
            )
        return value

    result = rename(result)
    result.update(
        left_degree=4,
        right_degree=5,
        common_integral_implementation="bounded independent Basix quadrature; at most 128 points and 8 cells",
    )
    return result, files
