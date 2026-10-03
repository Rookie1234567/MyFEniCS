"""Bounded FE-only saved-field integrals and an existing p3-to-p4 witness.

No form assembly, global Maxwell/Gram matrix, factor, optimizer or Torch import.
The original qualified FE restoration/interpolation interfaces are reused.
"""

from dataclasses import replace
from pathlib import Path
from time import perf_counter

import numpy as np

from src.runners.feinn_workflow import write_json
from src.solvers.feinn_discretization_audit import atomic_npz
from src.solvers.feinn_native import load_native
from src.solvers.feinn_saved_attribution import frozen_fields
from src.solvers.feinn_saved_state import checked_entry
from src.solvers.neural_fe_action_packet import array_hash


def geometry(design, packet):
    from src.solvers.feinn_interpolation import full_space
    from src.solvers.feinn_fem import physical_config
    from src.constraints.floquet_3d import build_double_floquet_mpc

    _, data, space, centers, tags, notch, _ = full_space(design, 3)
    cfg, _ = physical_config(design, 3)
    floquet = build_double_floquet_mpc(space, data, cfg)
    assert_order(space, floquet, packet)
    return cfg, data, space, floquet, centers, tags, notch


def assert_order(space, floquet, packet):
    dofs = np.asarray(space.dofmap.list, np.int64)
    if not np.array_equal(dofs, packet.a["cell_dofs"]):
        raise ValueError("SAVED_FIELD_FE_NUMBERING_CHANGED")
    if not np.array_equal(np.sort(floquet.mpc.slaves), np.sort(packet.a["slaves"])):
        raise ValueError("SAVED_FIELD_MPC_NUMBERING_CHANGED")


def restore(floquet, packet, c):
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field

    field = restore_p0_full_field(floquet, packet.storage(c))
    expected = packet.expand(c)
    actual = field.x.array[packet.a["cell_dofs"]]
    defect = float(
        np.linalg.norm(actual - expected)
        / (np.linalg.norm(actual) + np.linalg.norm(expected))
    )
    if defect > 1e-10:
        raise ValueError("ACTUAL_FE_MPC_RESTORATION_FAILED")
    return field, defect


def fixed_regions(mesh, centers, tags, notch, bounds, h=1.25):
    mesh.topology.create_connectivity(2, 3)
    links = mesh.topology.connectivity(2, 3)
    interface = set()
    for facet in range(mesh.topology.index_map(2).size_local):
        cells = links.links(facet)
        if len(cells) == 2 and tags[cells[0]] != tags[cells[1]]:
            interface.update(map(int, cells))
    periodic = np.zeros(len(tags), bool)
    for axis in (0, 1):
        periodic |= (centers[:, axis] - bounds[axis][0] < h) | (
            bounds[axis][1] - centers[:, axis] < h
        )
    return dict(
        air_notch=np.flatnonzero((tags == 1) & notch),
        air_other=np.flatnonzero((tags == 1) & ~notch),
        periodic_boundary_neighbor=np.flatnonzero(periodic),
        material_interface_neighbor=np.array(sorted(interface), np.int32),
    )


def run(stage, design, pre, artifact, marker, manifest, load_index):
    from dolfinx import fem
    from src.solvers.feinn_bounded_field_integrals import BoundedFieldIntegrals

    cutoff = (
        manifest["supervision_budget_origin_monotonic"]
        + manifest["supervised_limit_seconds"]
        - 150
    )
    adapter_cutoff = min(cutoff, perf_counter() + 600)

    def guard():
        if perf_counter() >= cutoff:
            raise RuntimeError("FE_DIAGNOSTIC_SAVE_RESERVE")

    guard()
    native = load_index("e1_fe")
    packet = load_native(checked_entry(native["files"]["native"]))
    fields = frozen_fields(load_index("v12_saved_state_freeze"))
    with np.load(
        checked_entry(load_index("e3_reference")["files"]["reference"]),
        allow_pickle=False,
    ) as z:
        c_ref = np.array(z["c"])
    cfg, data, space, floquet, centers, tags, notch = geometry(design, packet)
    integrator = BoundedFieldIntegrals(data.mesh, cfg.k0)
    result = dict(
        no_training=True,
        no_parameter_updates=True,
        Gram_factor_created=False,
        Maxwell_factor_created=False,
        source_sha=manifest["source_sha"],
        reference_used_for_training=False,
        reference_used_for_diagnostic=True,
        official_candidate_results=False,
        production_initialization_allowed=False,
    )
    arrays = {}
    if stage == "v12_saved_field_integrals":
        b = load_index("v12_saved_field_attribution")["result"]
        if not b.get("C_admitted"):
            raise ValueError("SAVED_FIELD_IDENTITY_GATE_REQUIRED")
        error0 = fields["M3600"] - c_ref
        error1 = fields["Mfinal"] - c_ref
        delta = fields["Mfinal"] - fields["M3600"]
        energies, mpc = {}, {}
        for name, c in dict(
            before=error0,
            after=error1,
            delta=delta,
            minus=error0 - delta,
            reference=c_ref,
        ).items():
            guard()
            field, defect = restore(floquet, packet, c)
            energies[name] = integrator.energies(field).tolist()
            mpc[name] = defect
            marker("bounded_field_energy", dict(field=name, energies=energies[name]))
        terms = {}
        for i, name in enumerate(("E_L2", "scaled_curl_L2")):
            cross = (energies["after"][i] - energies["minus"][i]) / 2
            update = energies["delta"][i]
            change = energies["after"][i] - energies["before"][i]
            scale = max(
                energies["before"][i], energies["after"][i], abs(cross) + update
            )
            terms[name] = dict(
                before=energies["before"][i],
                after=energies["after"][i],
                cross=cross,
                update_energy=update,
                change=change,
                reconstructed_change=cross + update,
                operation_scale=scale,
                defect=abs(change - cross - update) / scale,
                reference_energy=energies["reference"][i],
            )
        G_check = {}
        for name, key in [("before", "M3600"), ("after", "Mfinal")]:
            combined = energies[name][0] + (5 * cfg.k0) ** 2 * energies[name][1]
            measured = b["rows"][key]["field_G_squared"]
            G_check[name] = dict(
                integrated_G_energy=combined,
                sparse_G_energy=measured,
                relative=abs(combined - measured) / measured,
            )
        ref_field, _ = restore(floquet, packet, c_ref)
        region_names = fixed_regions(
            data.mesh, centers, tags, notch, design["geometry"]["bounds_nm"]
        )
        dg0 = fem.functionspace(data.mesh, ("DG", 0))
        region_rows = {}
        cell_volume = np.array([np.linalg.det(j) for j in integrator.geometry])
        for name, cells in region_names.items():
            guard()
            indicator = fem.Function(dg0)
            indicator.x.array[:] = 0
            for cell in cells:
                indicator.x.array[dg0.dofmap.cell_dofs(int(cell))[0]] = 1
            ref_energy = integrator.energies(ref_field, indicator=indicator)
            volume = float(sum(cell_volume[cells]))
            row = dict(
                cells=len(cells),
                cell_ids_sha256=array_hash(cells),
                volume_nm3=volume,
                reference_energy=ref_energy.tolist(),
                overlaps_other_regions=True,
                states={},
            )
            arrays["cells_" + name] = cells
            for key in ("M3600", "Mfinal"):
                guard()
                field, defect = restore(floquet, packet, fields[key] - c_ref)
                value = integrator.energies(field, indicator=indicator)
                denominator = np.maximum(np.sqrt(ref_energy), 1e-12 * np.sqrt(volume))
                row["states"][key] = dict(
                    absolute=np.sqrt(value).tolist(),
                    error_energy=value.tolist(),
                    actual_denominator=denominator.tolist(),
                    relative=(np.sqrt(value) / denominator).tolist(),
                    incident_floor=1e-12 * np.sqrt(volume),
                    MPC_relative=defect,
                )
            region_rows[name] = row
            marker("bounded_region", dict(region=name, cells=len(cells)))
        result.update(
            status="SAVED_FIELD_INTEGRALS_COMPLETE",
            energy_terms=terms,
            energies=energies,
            G_norm_identity=G_check,
            MPC=mpc,
            regions=region_rows,
            units="E integral nm^3; curl/k0 same units; G ell=5nm",
            A_actions=0,
            Gsolve_count=0,
        )
        if (
            max(
                [x["defect"] for x in terms.values()]
                + [x["relative"] for x in G_check.values()]
            )
            > 1e-8
        ):
            raise ValueError("INDEPENDENT_FIELD_ENERGY_PAIRING_FAILED")
    else:
        started = perf_counter()
        old = load_index("v7_p_transfer_checks")
        if not old["result"]["M5_transfer"]["passed"]:
            raise ValueError("EXISTING_P34_QUALIFICATION_MISSING")
        packet4 = load_native(checked_entry(old["files"]["native"]))
        import basix.ufl
        from src.constraints.floquet_3d import build_double_floquet_mpc

        space4 = fem.functionspace(
            data.mesh, basix.ufl.element("N1curl", "hexahedron", 4)
        )
        floquet4 = build_double_floquet_mpc(
            space4, data, replace(cfg, nedelec_degree=4)
        )
        assert_order(space4, floquet4, packet4)
        if perf_counter() - started > 600:
            result.update(
                status="NOT_RUN_INPUT_OR_ADAPTER_UNAVAILABLE",
                adapter_seconds=perf_counter() - started,
            )
            return result, {}
        from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
            restore_p0_full_field,
        )

        embedded = {}
        pairing = {}
        for name, c in dict(
            p3reference=c_ref, M3600=fields["M3600"], Mfinal=fields["Mfinal"]
        ).items():
            guard()
            if perf_counter() >= adapter_cutoff:
                result.update(
                    status="NOT_RUN_INPUT_OR_ADAPTER_UNAVAILABLE",
                    reason="P34_RESTORE_600S_LIMIT",
                )
                return result, {}
            field3, defect = restore(floquet, packet, c)
            field4 = fem.Function(space4)
            field4.interpolate(field3)
            storage = field4.x.array.copy()
            storage[packet4.a["slaves"]] = 0
            recovered = restore_p0_full_field(floquet4, storage)
            mpc = float(
                np.linalg.norm(recovered.x.array - field4.x.array)
                / np.linalg.norm(field4.x.array)
            )
            diff = integrator.energies((field3, field4))
            denom = integrator.energies(field3)
            pairing[name] = dict(
                MPC=mpc,
                common_field_relative=np.sqrt(diff / denom).tolist(),
                p3_MPC=defect,
            )
            if max([mpc] + pairing[name]["common_field_relative"]) > 1e-10:
                raise ValueError("REUSED_P34_FIELD_PAIRING_FAILED")
            embedded[name] = storage[packet4.a["masters"]]
        write_json(
            Path(artifact) / "embedding_witness.json",
            dict(
                source_sha=manifest["source_sha"],
                embedding=pairing,
                p4_native=old["files"]["native"],
                new_assembly=False,
                new_factor=False,
            ),
        )
        with np.load(
            checked_entry(load_index("v8_p4_reference_recovery")["files"]["reference"]),
            allow_pickle=False,
        ) as z:
            if str(z["native_sha256"]) != old["files"]["native"]["sha256"]:
                raise ValueError("SAVED_P4_REFERENCE_OPERATOR_IDENTITY_CHANGED")
            # V8's qualified authority packet explicitly distinguishes scattered
            # FE coefficients from total-field port amplitudes. Never alias them.
            cref4 = reference_coefficients(z, "c_scattered", packet4.size)
        ref4 = packet4.apply(cref4) - packet4.f
        rows = {}
        residuals = {}
        for name, c in embedded.items():
            guard()
            r = packet4.apply(c) - packet4.f
            residuals[name] = r
            rows[name] = dict(
                native_absolute=float(np.linalg.norm(r)),
                native_denominator=packet4.bnorm,
                native_relative=float(np.linalg.norm(r) / packet4.bnorm),
            )
        base = residuals["p3reference"]
        for name in ("M3600", "Mfinal"):
            image = packet4.apply(embedded[name] - embedded["p3reference"])
            defect = float(
                np.linalg.norm(image - (residuals[name] - base))
                / (
                    np.linalg.norm(image)
                    + np.linalg.norm(residuals[name])
                    + np.linalg.norm(base)
                )
            )
            rows[name].update(
                relative_to_p3_baseline_absolute=float(
                    np.linalg.norm(residuals[name] - base)
                ),
                candidate_error_image_identity=defect,
            )
            if defect > 1e-10:
                raise ValueError("P4_TEST_ERROR_IDENTITY_FAILED")
        arrays.update({"embedded_" + k: v for k, v in embedded.items()})
        arrays.update({"r4_" + k: v for k, v in residuals.items()})
        arrays.update(f4=packet4.f, reference4_residual=ref4)
        result.update(
            status="EXISTING_P4_TEST_SPACE_WITNESS_COMPLETE",
            rows=rows,
            embedding=pairing,
            adapter_seconds=perf_counter() - started,
            p4_reference_native=float(np.linalg.norm(ref4) / packet4.bnorm),
            A4=packet4.counts["A"],
            AH4=packet4.counts["AH"],
            G4_created=False,
            p4_dual_norm_qualified=False,
            P34_source=old["source_sha"],
            trial_degree=3,
            test_degree=4,
            test_space_operator=old["files"]["native"],
        )
        if packet4.counts["A"] > 8 or result["p4_reference_native"] > 1e-10:
            raise ValueError("P4_TEST_WITNESS_BUDGET_OR_REFERENCE_FAILED")
    path = Path(artifact) / "field_diagnostic_arrays.npz"
    atomic_npz(path, **arrays)
    write_json(Path(artifact) / "partial_field_diagnostics.json", result)
    return result, dict(vectors=path)


def reference_coefficients(archive, key, size):
    value = np.array(archive[key])
    if (
        value.shape != (size,)
        or value.dtype != np.complex128
        or not np.isfinite(value).all()
    ):
        raise ValueError("SAVED_REFERENCE_MASTER_SCATTERED_LAYOUT_FAILED")
    return value


class RetainedA4Budget:
    """Persist a reservation before every action, including failed attempts."""

    def __init__(self, path, packet, identity, guard):
        self.path, self.packet, self.identity, self.guard = (
            Path(path),
            packet,
            identity,
            guard,
        )
        self.used = 0
        if self.path.exists():
            with np.load(self.path, allow_pickle=False) as z:
                if str(z["identity"]) != identity:
                    raise ValueError("BACKGROUND_ACTION_BUDGET_IDENTITY_CHANGED")
                self.used = int(z["used"])
        if not 0 <= self.used <= 4:
            raise ValueError("BACKGROUND_ACTION_BUDGET_INVALID")
        self.inherited = self.used

    def apply(self, c):
        self.guard()
        if self.used >= 4:
            raise RuntimeError("BACKGROUND_CUMULATIVE_A4_CAP")
        self.used += 1
        atomic_npz(
            self.path, used=np.asarray(self.used), identity=np.asarray(self.identity)
        )
        return self.packet.apply(c)


def background_embedding(field3, space4, floquet4, packet4, integrator):
    """Use the qualified FE interpolation and restore MPC exactly once."""
    from dolfinx import fem
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field

    field4 = fem.Function(space4)
    field4.interpolate(field3)
    storage = field4.x.array.copy()
    storage[packet4.a["slaves"]] = 0
    recovered = restore_p0_full_field(floquet4, storage)
    scale = np.linalg.norm(field4.x.array) + np.linalg.norm(recovered.x.array)
    mpc = float(
        np.linalg.norm(recovered.x.array - field4.x.array)
        / max(scale, np.finfo(float).tiny)
    )
    difference = integrator.energies((field3, recovered))
    reference = integrator.energies(field3)
    if np.any(reference <= 0):
        raise ValueError("BACKGROUND_COMMON_FIELD_NONZERO_SCALE_REQUIRED")
    relative = np.sqrt(difference / reference)
    if max(mpc, *relative) > 1e-10:
        raise ValueError("BACKGROUND_P34_PUBLIC_FIELD_PAIRING_FAILED")
    return storage[packet4.a["masters"]], dict(
        MPC_operation_relative=mpc,
        common_E_scaled_curl_relative=relative.tolist(),
        absolute_difference_energy=difference.tolist(),
        reference_energy=reference.tolist(),
        integration_degree=15,
        no_analytic_background_reinterpolation=True,
    )


def corrected_background_rows(residuals, correction, f4, total_rhs):
    """One shared affine shift, signed energy closure and invariant error images."""
    denominator, total_denominator = (
        float(np.linalg.norm(f4)),
        float(np.linalg.norm(total_rhs)),
    )
    if min(denominator, total_denominator) <= 0:
        raise ValueError("BACKGROUND_NONZERO_ORIGINAL_RHS_REQUIRED")
    update = float(np.vdot(correction, correction).real)
    corrected, rows = {}, {}
    for name, r in residuals.items():
        if not np.isfinite(r).all() or not np.isfinite(correction).all():
            raise ValueError("BACKGROUND_NONFINITE_SAVED_RESIDUAL")
        corrected[name] = r + correction
        before = float(np.vdot(r, r).real)
        after = float(np.vdot(corrected[name], corrected[name]).real)
        product = np.vdot(r, correction)
        cross = float(2 * product.real)
        scale = max(before, after, abs(cross) + update, np.finfo(float).tiny)
        defect = abs(after - before - cross - update) / scale
        if defect > 1e-8:
            raise ValueError("BACKGROUND_RESIDUAL_ENERGY_CLOSURE")
        phase_scale = float(np.linalg.norm(r) * np.linalg.norm(correction))
        rows[name] = dict(
            original_absolute=np.sqrt(before),
            correction_absolute=np.sqrt(update),
            corrected_absolute=np.sqrt(after),
            original_f4_denominator=denominator,
            original_relative=np.sqrt(before) / denominator,
            corrected_relative=np.sqrt(after) / denominator,
            total_rhs_diagnostic_denominator=total_denominator,
            corrected_total_rhs_diagnostic_relative=np.sqrt(after) / total_denominator,
            energy_before=before,
            energy_after=after,
            signed_cross=cross,
            correction_energy=update,
            energy_change=after - before,
            energy_operation_scale=scale,
            energy_closure_defect=defect,
            energy_removed_fraction=(before - after) / before if before else None,
            normalized_cross_complex=[
                product.real / phase_scale,
                product.imag / phase_scale,
            ]
            if phase_scale > 0
            else None,
            original_gate_denominator_retained=True,
        )
    for name in ("M3600", "Mfinal"):
        old = residuals[name] - residuals["p3reference"]
        new = corrected[name] - corrected["p3reference"]
        scale = (
            np.linalg.norm(residuals[name])
            + np.linalg.norm(residuals["p3reference"])
            + np.linalg.norm(corrected[name])
            + np.linalg.norm(corrected["p3reference"])
        )
        defect = float(np.linalg.norm(new - old) / max(scale, np.finfo(float).tiny))
        if defect > 1e-10:
            raise ValueError("BACKGROUND_SHARED_ERROR_IMAGE_CHANGED")
        rows[name].update(
            error_image_absolute=float(np.linalg.norm(old)),
            error_image_invariance_operation_relative=defect,
        )
    return rows, corrected


def background_transfer(design, artifact, marker, manifest, load_index):
    """Review V12's sole background witness; no solver or neural read path."""
    import basix.ufl
    from dolfinx import fem
    from mpi4py import MPI
    from petsc4py import PETSc
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.feinn_bounded_field_integrals import BoundedFieldIntegrals
    from src.runners.feinn_workflow import ROOT

    if (
        MPI.COMM_WORLD.size != 1
        or PETSc.ScalarType != np.complex128
        or PETSc.IntType != np.int64
    ):
        raise RuntimeError("BACKGROUND_ABI_MPI1_COMPLEX128_INT64_REQUIRED")
    cutoff = (
        manifest["supervision_budget_origin_monotonic"]
        + manifest["supervised_limit_seconds"]
        - 150
    )
    adapter_cutoff = min(cutoff, perf_counter() + 600)

    def guard():
        if perf_counter() >= cutoff:
            raise RuntimeError("BACKGROUND_SAVE_RESERVE")

    guard()
    native3, native4 = load_index("e1_fe"), load_index("v7_p_transfer_checks")
    old = load_index("v12_test_space_witness")
    identity3, identity4 = native3["result"]["identity"], native4["result"]["identity"]
    if (
        not native4["result"]["M5_transfer"]["passed"]
        or old["result"]["test_space_operator"] != native4["files"]["native"]
    ):
        raise ValueError("BACKGROUND_EXISTING_P34_IDENTITY_REQUIRED")
    physical_keys = (
        "mesh_coordinates_sha256",
        "geometry_cell_dofs_sha256",
        "cell_tags_sha256",
        "centers_sha256",
        "mode_manifest_sha256",
        "channels",
        "cells",
        "modes",
        "material",
    )
    if any(identity3[k] != identity4[k] for k in physical_keys):
        raise ValueError("BACKGROUND_P3_P4_PHYSICS_CHANGED")
    packet3 = load_native(checked_entry(native3["files"]["native"]))
    packet4 = load_native(checked_entry(native4["files"]["native"]))
    if (packet3.size, packet4.size, packet3.np, packet4.np) != (31968, 75264, 40, 40):
        raise ValueError("BACKGROUND_MASTER_PORT_LAYOUT_CHANGED")
    for packet, identity in [(packet3, identity3), (packet4, identity4)]:
        for key in (
            "background",
            "background_alpha",
            "total_g",
            "masters",
            "slaves",
            "cell_dofs",
            "evals",
        ):
            if array_hash(packet.a[key]) != identity["packet_array_hashes"][key]:
                raise ValueError("BACKGROUND_PACKET_ARRAY_IDENTITY_CHANGED")
        # The original native total RHS is total_g; its port RHS is zero.
        if np.any(packet.a["gp"] != 0):
            raise ValueError("BACKGROUND_ORIGINAL_ZERO_PORT_RHS_REQUIRED")
        if not np.array_equal(
            np.sort(np.r_[packet.a["masters"], packet.a["slaves"]]),
            np.arange(packet.full_rows),
        ):
            raise ValueError("BACKGROUND_FULL_MASTER_SLAVE_LAYOUT_FAILED")
    cfg, data, space3, floquet3, _, _, _ = geometry(design, packet3)
    space4 = fem.functionspace(data.mesh, basix.ufl.element("N1curl", "hexahedron", 4))
    floquet4 = build_double_floquet_mpc(space4, data, replace(cfg, nedelec_degree=4))
    assert_order(space4, floquet4, packet4)
    if perf_counter() >= adapter_cutoff:
        raise RuntimeError("BACKGROUND_INPUT_ADAPTER_600S_LIMIT")
    integrator = BoundedFieldIntegrals(data.mesh, cfg.k0)
    field3, mpc3 = restore(floquet3, packet3, packet3.a["background"])
    P34b3, pairing = background_embedding(field3, space4, floquet4, packet4, integrator)
    db = P34b3 - packet4.a["background"]
    with np.load(checked_entry(old["files"]["vectors"]), allow_pickle=False) as z:
        residuals = {
            k: reference_coefficients(z, "r4_" + k, packet4.size)
            for k in ("p3reference", "M3600", "Mfinal")
        }
        saved_embedded = {
            k: reference_coefficients(z, "embedded_" + k, packet4.size)
            for k in ("p3reference", "M3600", "Mfinal")
        }
        embedded_ref = saved_embedded["p3reference"]
        f4 = reference_coefficients(z, "f4", packet4.size)
    if not np.array_equal(f4, packet4.f):
        raise ValueError("BACKGROUND_ORIGINAL_F4_CHANGED")
    context = native4["files"]["native"]["sha256"] + old["files"]["vectors"]["sha256"]
    ops = RetainedA4Budget(
        ROOT / "tmp/task42extra/v13_A4_budget.npz", packet4, context, guard
    )
    arrays = dict(
        b3=packet3.a["background"],
        b4=packet4.a["background"],
        P34b3=P34b3,
        d_b=db,
        f4=f4,
        total_rhs4=packet4.a["total_g"],
    )
    arrays.update({"embedded_scattered_" + k: v for k, v in saved_embedded.items()})
    arrays.update(
        {"same_total_c_scattered_" + k: v + db for k, v in saved_embedded.items()}
    )
    result = dict(
        status="BACKGROUND_CONVERSION_PARTIAL",
        source_sha=manifest["source_sha"],
        diagnostic_only=True,
        no_training=True,
        no_network_forward=True,
        no_parameter_updates=True,
        Gram_factor_created=False,
        Maxwell_factor_created=False,
        G4_created=False,
        reference_used_for_training=False,
        reference_used_for_diagnostic=True,
        pde_only_solve=False,
        pde_only_solver_qualified=False,
        official_candidate_results=False,
        production_initialization_allowed=False,
        coefficient_schema="c_scattered_master_only",
        background_embedding=pairing,
        p3_background_MPC_relative=mpc3,
        identity=dict(
            p3_native=native3["files"]["native"],
            p4_native=native4["files"]["native"],
            saved_C2=old["files"]["vectors"],
            material=identity4["material"]["material_table_sha256"],
            mesh=identity4["mesh_coordinates_sha256"],
            modes=identity4["mode_manifest_sha256"],
        ),
        coefficient_hashes={k: array_hash(v) for k, v in arrays.items()},
        coefficient_absolute={k: float(np.linalg.norm(v)) for k, v in arrays.items()},
        historical_p3_NN_failure_unchanged=True,
    )
    path = Path(artifact) / "background_vectors.npz"
    try:
        guard()
        marker("background_A4_correction_begin", dict(cumulative_reserved=ops.used + 1))
        Adb = ops.apply(db)
        arrays["A4_d_b"] = Adb
        rows, corrected = corrected_background_rows(
            residuals, Adb, f4, packet4.a["total_g"]
        )
        arrays.update({"original_" + k: v for k, v in residuals.items()})
        arrays.update({"corrected_" + k: v for k, v in corrected.items()})
        result["rows"] = rows
        marker(
            "background_A4_direct_crosscheck_begin",
            dict(cumulative_reserved=ops.used + 1),
        )
        direct = ops.apply(embedded_ref + db) - f4
        arrays.update(
            direct_same_total_reference=direct,
            embedded_scattered_reference=embedded_ref,
        )
        scale = (
            np.linalg.norm(direct)
            + np.linalg.norm(residuals["p3reference"])
            + np.linalg.norm(Adb)
            + np.linalg.norm(f4)
        )
        defect = float(np.linalg.norm(direct - corrected["p3reference"]) / scale)
        result["direct_vs_saved_addition_operation_relative"] = defect
        if defect > 1e-10:
            raise ValueError("BACKGROUND_DIRECT_VS_SAVED_ADDITION_FAILED")
        result["status"] = "BACKGROUND_AFFINE_CONVERSION_COMPLETE"
    finally:
        result.update(
            A4=packet4.counts["A"],
            cumulative_A4_reserved=ops.used,
            inherited_A4_reserved=ops.inherited,
            AH4=packet4.counts["AH"],
            G_actions=0,
            Gsolve=0,
            new_reference_solves=0,
            network_forwards=0,
        )
        atomic_npz(path, **arrays)
        write_json(Path(artifact) / "partial_background_conversion.json", result)
    marker(
        "background_conversion_frozen", dict(status=result["status"], A4=result["A4"])
    )
    return result, dict(vectors=path)
