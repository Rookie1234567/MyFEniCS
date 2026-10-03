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
