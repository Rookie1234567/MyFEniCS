"""Opt-in same-mesh p authority audit; no neural or Gram dependencies.

Different-order fields are compared on a common mesh, never by subtracting
their coefficient vectors. The direct factor is confined to reference().
"""

from copy import deepcopy
from dataclasses import replace
import gc
import json
import os
from pathlib import Path
import tempfile
from time import perf_counter

import numpy as np

from src.geometry.neural_micro_pilot import hexa_inventory
from src.solvers.feinn_native import load_native
from src.solvers.feinn_riesz import rss_bytes
from src.solvers.neural_fe_action_packet import array_hash

AUDIT_KIND = "DISCRETIZATION_AUTHORITY_AUDIT"
POLICY = dict(
    audit_kind=AUDIT_KIND,
    reference_role="REFERENCE_ONLY",
    reference_used_for_training=False,
    training_reference_allowed=False,
    neural_solver_qualified=False,
    production_initialization_allowed=False,
    continuum_convergence_claim=False,
    mesh_accuracy_qualified=False,
    port_truncation_qualified=False,
)
EXPECTED = dict(
    native="2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215",
    reference="0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7",
    material="55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2",
    mesh="78e294e0337292d2750f587ddf394aaa868bd726f8b1104d4eae6a68db039086",
    modes="1e37bd91b3cabafe27741db2e0cb99fce7392c2521c84ff9e67f4cfd6a28c14e",
)


def atomic_npz(path, **values):
    """FE-only synchronous temporary/fsync/replace, with directory fsync."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            np.savez(stream, **values)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def positive_energy(value, scale):
    """Only tolerate a scale-aware floating point negative roundoff."""
    value = complex(value)
    tolerance = 128 * np.finfo(float).eps * max(float(scale), np.finfo(float).tiny)
    if not np.isfinite(value) or abs(value.imag) > tolerance or value.real < -tolerance:
        raise ValueError("COMPARISON_INVALID_ENERGY")
    return float(0 if value.real < 0 else value.real)


def difference_record(left_norm, right_norm, absolute, natural):
    denominator = max(float(right_norm), 1e-12 * float(natural))
    if denominator <= 0 or not np.isfinite([left_norm, right_norm, absolute, denominator]).all():
        raise ValueError("INVALID_COMPARISON_SCALE")
    return dict(p3_norm=float(left_norm), p4_norm=float(right_norm), absolute=float(absolute),
                denominator=denominator, natural_scale=float(natural), relative=float(absolute / denominator),
                near_zero=bool(right_norm < 1e-12 * natural), difference="p3_minus_p4")


def channel_key(row, top_z, bottom_z):
    return (row["side"], int(row["m"]), int(row["n"]), row["polarization"],
            float(top_z if row["side"] == "top" else bottom_z))


def capacity_plan(cells, degree, ports=40):
    inventory = hexa_inventory(cells, degree)
    nc, dim = inventory["cells"], inventory["cell_dimension"]
    independent = inventory["full_fe_rows"] - inventory["periodic_slaves"]
    # Conservative all-cell tensor + dense upper bounds on both port couplings,
    # CSR/COO/PETSc conversion and JIT temporaries; no MPI replication at MPI1.
    triplets = nc * dim**2 + 2 * independent * ports + ports
    resident = nc * dim**2 * 16 + 2 * independent * ports * 16 + independent * 16 * 12
    conversion = triplets * 80 + 512 * 2**20
    return dict(kind="derived simultaneous allocation bound, not measured RSS or factor prediction",
                inventory=inventory, independent_rows=independent, augmented_rows=independent + ports,
                nnz_upper=triplets, full_cell_tensor_bytes=nc * dim**2 * 16,
                resident_upper_bytes=resident, assembly_conversion_reserve_bytes=conversion,
                allocation_upper_bytes=resident + conversion, MPI_copies=1,
                factor_bytes="UNKNOWN_UNTIL_SYMBOLIC", planning_cap_bytes=12 * 2**30)


def clock(manifest):
    from src.runners.feinn_workflow import replay_closure_deadline
    cutoff = replay_closure_deadline(manifest)

    def check(stage):
        if perf_counter() >= cutoff:
            raise RuntimeError("AUTHORITY_TIME_SAVE_RESERVE: " + stage)
    check("entry")
    return check, cutoff


def load_p3(native_index, reference_index):
    from src.io.feinn_pilot import ROOT
    from src.runners.feinn_workflow import sha
    paths = dict(native=native_index["files"]["native"], reference=reference_index["files"]["reference"])
    for name, entry in paths.items():
        if entry["sha256"] != EXPECTED[name] or sha(entry["path"]) != EXPECTED[name]:
            raise ValueError("ARTIFACT_BLOCKED: p3 " + name)
    if sha(ROOT / "input/materials/si_optical_constants_v1.json") != EXPECTED["material"]:
        raise ValueError("MATERIAL_IDENTITY_FAILED")
    packet = load_native(paths["native"]["path"])
    with np.load(paths["reference"]["path"], allow_pickle=False) as saved:
        c = np.array(saved["c"])
        alpha = np.array(saved["alpha"])
    if c.shape != (31968,) or c.dtype != np.complex128:
        raise ValueError("P3_REFERENCE_ORDER_FAILED")
    if np.linalg.norm(alpha - packet.alpha(c)) / np.linalg.norm(alpha) > 1e-10:
        raise ValueError("P3_REFERENCE_PORT_IDENTITY_FAILED")
    identity = native_index["result"]["identity"]
    if identity["mesh_coordinates_sha256"] != EXPECTED["mesh"] or identity["mode_manifest_sha256"] != EXPECTED["modes"]:
        raise ValueError("P3_FROZEN_PHYSICAL_IDENTITY_FAILED")
    return packet, c, dict(paths=paths, material_sha256=EXPECTED["material"], identity=identity)


def p3_on_same_mesh(model, packet):
    import basix.ufl
    from dolfinx import fem
    from src.constraints.floquet_3d import build_double_floquet_mpc
    space = fem.functionspace(model["data"].mesh, basix.ufl.element("N1curl", "hexahedron", 3))
    if not np.array_equal(np.asarray(space.dofmap.list, dtype=np.int64), packet.a["cell_dofs"]):
        raise ValueError("P3_REBUILT_NATIVE_ORDER_FAILED")
    floquet = build_double_floquet_mpc(space, model["data"], replace(model["cfg"], nedelec_degree=3))
    if not np.array_equal(np.sort(floquet.mpc.slaves), np.sort(packet.a["slaves"])):
        raise ValueError("P3_REBUILT_MPC_ORDER_FAILED")
    return space, floquet


def embedding_check(data, space3, floquet3, space4, floquet4, *, seed=421701):
    import basix
    import ufl
    from dolfinx import fem
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    n3 = space3.dofmap.index_map.size_local
    masters3 = np.setdiff1d(np.arange(n3), floquet3.mpc.slaves)
    rng = np.random.default_rng(seed)
    storage = np.zeros(n3, dtype=np.complex128)
    storage[masters3] = rng.normal(size=len(masters3)) + 1j * rng.normal(size=len(masters3))
    field3 = restore_p0_full_field(floquet3, storage)
    field4 = fem.Function(space4)
    field4.interpolate(field3)
    independent_storage = field4.x.array.copy()
    independent_storage[floquet4.mpc.slaves] = 0
    recovered4 = restore_p0_full_field(floquet4, independent_storage)
    mpc_defect = np.linalg.norm(recovered4.x.array - field4.x.array) / np.linalg.norm(field4.x.array)
    q, _ = basix.make_quadrature(basix.CellType.hexahedron, 5)
    cells = np.arange(data.mesh.topology.index_map(3).size_local, dtype=np.int32)
    witnesses = {}
    for name, transform in (("E", lambda E: E), ("curl", ufl.curl)):
        left = fem.Expression(transform(field3), q).eval(data.mesh, cells)
        right = fem.Expression(transform(field4), q).eval(data.mesh, cells)
        witnesses[name] = float(np.linalg.norm(left - right) / (np.linalg.norm(left) + np.linalg.norm(right)))
    data.mesh.topology.create_entity_permutations()
    result = dict(common_points_per_cell=len(q), common_point_E_relative=witnesses["E"],
                  common_point_curl_relative=witnesses["curl"], MPC_embedding_relative=float(mpc_defect),
                  p3_nonzero_complex_norm=float(np.linalg.norm(storage)),
                  p4_internal_nonzero_norm=float(np.linalg.norm(field4.x.array[np.unique(np.asarray(space4.dofmap.list)[:, space4.element.basix_element.entity_dofs[3][0]])])),
                  orientation_classes=len(np.unique(data.mesh.topology.get_cell_permutation_info())),
                  phase_x=[floquet4.phase_x.real, floquet4.phase_x.imag], phase_y=[floquet4.phase_y.real, floquet4.phase_y.imag])
    result["passed"] = max(witnesses.values(), default=0) <= 1e-10 and mpc_defect <= 1e-10
    return result


def measured_families(space, packet):
    element = space.element.basix_element
    dofs = np.asarray(space.dofmap.list)
    result = {}
    for dimension, name in ((1, "edge"), (2, "face"), (3, "interior")):
        local = [j for entity in element.entity_dofs[dimension] for j in entity]
        unique = np.unique(dofs[:, local])
        result[name] = int(len(np.intersect1d(unique, packet.a["masters"])))
    if sum(result.values()) != packet.size:
        raise ValueError("P4_INDEPENDENT_FAMILIES_INCOMPLETE")
    return result


def verify_model(model, original):
    record = model["record"]
    identity = original["identity"]
    keys = ("mesh_coordinates_sha256", "geometry_cell_dofs_sha256", "cell_tags_sha256", "centers_sha256", "mode_manifest_sha256", "cells", "channels", "actual_material_cell_counts", "actual_notch_cells", "dtn_quadrature_degree")
    if any(record[k] != identity[k] for k in keys):
        raise ValueError("PHYSICS_EQUIVALENCE_FAILED")
    fields = {k: dict(p3=identity[k], p4=record[k], equal=True) for k in keys}
    cfg = model["cfg"]
    fields["physical_parameters"] = dict(wavelength_nm=cfg.lambda0, kx=cfg.kx, ky=cfg.ky,
        bounds_nm=[[axis[0], axis[-1]] for axis in model["axes"]],
        n_air=cfg.n_air, n_substrate=cfg.n_substrate, n_grating=cfg.n_grating, mu_r=cfg.mu_r,
        incident_theta_deg=cfg.incident_theta_deg, incident_phi_deg=cfg.incident_phi_deg,
        polarization_kind=cfg.polarization_kind, amplitude=cfg.incident_amplitude,
        time_convention="exp(-i omega t)", physical_configuration_source="unchanged hash-bound design_v1 and physical_config; only degree argument=4",
        MPC_phase_x=model["floquet"].phase_x, MPC_phase_y=model["floquet"].phase_y,
        volume_quadrature_degree=15, original_complete_Fourier_DtN=True)
    return fields


def checks(design, native_index, reference_index, artifact, marker, manifest):
    import basix.ufl
    from dolfinx import fem
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.feinn_fem import build_model, export_native, native_gate
    from src.solvers.feinn_interpolation import full_space
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    tick, cutoff = clock(manifest)
    packet3, _, original = load_p3(native_index, reference_index)
    plan = capacity_plan(design["geometry"]["cells"], 4)
    marker("p4_pre_array_capacity", dict(plan, measured_rss_bytes=rss_bytes()))
    if rss_bytes() + plan["allocation_upper_bytes"] >= 12 * 2**30:
        raise RuntimeError("P4_REFERENCE_RESOURCE_BLOCKED_BEFORE_ARRAYS")
    small = deepcopy(design)
    small["geometry"]["cells"] = [2, 2, 2]
    cfg, data, s3, *_ = full_space(small, 3)
    s4 = fem.functionspace(data.mesh, basix.ufl.element("N1curl", "hexahedron", 4))
    f3 = build_double_floquet_mpc(s3, data, cfg)
    f4 = build_double_floquet_mpc(s4, data, replace(cfg, nedelec_degree=4))
    small_check = embedding_check(data, s3, f3, s4, f4)
    marker("small_p_transfer", small_check)
    if not small_check["passed"]:
        raise ValueError("SMALL_P_TRANSFER_FAILED")
    del data, s3, s4, f3, f4
    gc.collect()
    tick("M5 p4 model")
    model = build_model(design, degree=4, marker=marker, dtn_quadrature_degree=15)
    try:
        equivalence = verify_model(model, original)
        space3, floquet3 = p3_on_same_mesh(model, packet3)
        transfer = embedding_check(model["data"], space3, floquet3, model["space"], model["floquet"])
        marker("M5_p_transfer", transfer)
        tick("p4 export")
        packet4, identity4 = export_native(model, marker)
        families = measured_families(model["space"], packet4)
        action = native_gate(model, packet4)
        marker("p4_original_native_action", action)
        if not transfer["passed"] or action["status"] != "PASS":
            raise ValueError("P4_TRANSFER_ACTION_NOT_QUALIFIED")
        path = artifact / "p4_native.npz"
        atomic_npz(path, **packet4.a)
        return dict(status="P_TRANSFER_CAPACITY_PASS", small_transfer=small_check, M5_transfer=transfer,
                    identity=identity4, physics_equivalence_fields=equivalence, independent_families=families,
                    action=action, array_capacity=plan, numeric_cutoff_monotonic=cutoff,
                    original=original, counts=packet4.counts, **POLICY), dict(native=path)
    finally:
        destroy_same_mesh_physical_action(model["bundle"])


def reference(design, native_index, reference_index, checks_index, artifact, marker, manifest, *, assembler=None, independent_factory=None):
    from src.solvers.feinn_fem import build_model
    from src.solvers.feinn_reference import exact_solve, field_physics
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action, restore_p0_full_field
    from src.runners.feinn_workflow import sha
    tick, cutoff = clock(manifest)
    if checks_index["result"]["status"] != "P_TRANSFER_CAPACITY_PASS":
        raise RuntimeError("P4_REFERENCE_U0_NOT_QUALIFIED")
    _, _, original = load_p3(native_index, reference_index)
    packet = load_native(checks_index["files"]["native"]["path"])
    model = build_model(design, degree=4, marker=marker, dtn_quadrature_degree=15)
    try:
        equivalence = verify_model(model, original)
        if not np.array_equal(model["space"].dofmap.list, packet.a["cell_dofs"]):
            raise ValueError("P4_REFERENCE_NATIVE_ORDER_FAILED")
        def save(c, alpha, facts):
            atomic_npz(artifact / "p4_reference_state.npz", c_scattered=c,
                       alpha_scattered=alpha, alpha_total=alpha + packet.a["background_alpha"],
                       source_sha=np.asarray(manifest["source_sha"]), input_sha256=np.asarray(manifest["input_sha256"]),
                       native_sha256=np.asarray(checks_index["files"]["native"]["sha256"]),
                       metadata_json=np.asarray(json.dumps(dict(facts=facts, **POLICY))), **{k: np.asarray(v) for k, v in POLICY.items()})
        options = dict(check_budget=tick, save_packet=save)
        if assembler is not None:
            options["assembler"] = assembler
        c, direct = exact_solve(model, packet, artifact, marker, audit_options=options)
        independent_total = None
        if independent_factory is not None:
            integration = independent_factory(model, packet)
            independent_total = integration.total_residual(c)
            marker("independent_Basix_final_total", dict(relative=independent_total, scope=integration.scope))
            del integration
            if independent_total > 1e-10:
                raise ValueError("REFERENCE_INDEPENDENCE_UNRESOLVED_FINAL")
        recovered_field = restore_p0_full_field(model["floquet"], packet.storage(c))
        actual_local = recovered_field.x.array[packet.a["cell_dofs"]]
        expected_local = packet.expand(c)
        MPC_recovery_relative = float(np.linalg.norm(actual_local-expected_local) / np.linalg.norm(expected_local))
        del recovered_field, actual_local, expected_local
        tick("postprocessing")
        physics, _ = field_physics(model, packet, c, {}, artifact, marker)
        audit = physics["records"]["REFERENCE"]["audit"]
        qualified = bool(physics["reference_pass"] and max(audit[k] for k in ("native_relative", "augmented_relative", "original_total_augmented_relative", "independent_DOLFINx_total_native_relative", "port_operation_relative", "port_full_rhs_relative")) <= 1e-10
                         and audit["slave_storage_max"] <= 1e-10 and MPC_recovery_relative <= 1e-10)
        reference_path = artifact / "p4_reference_state.npz"
        return dict(status="P4_REFERENCE_QUALIFIED" if qualified else "REFERENCE_FAILED",
                    reference_qualified=qualified, physics=physics, direct=direct,
                    c_scattered_meaning="independent p4 master scattering FE coefficients; background excluded",
                    alpha_scattered_meaning="original alpha(c_scattered) with layered FE background removed",
                    alpha_total_meaning="background_alpha + alpha_scattered; includes known top incident projection",
                    identity=checks_index["result"]["identity"], independent_families=checks_index["result"]["independent_families"],
                    MPC_recovery_relative=MPC_recovery_relative,
                    independent_Basix_total_relative=independent_total,
                    physics_equivalence_fields=equivalence, p4_native_sha256=checks_index["files"]["native"]["sha256"],
                    p4_reference_sha256=sha(reference_path), numeric_cutoff_monotonic=cutoff,
                    MUMPS_symbolic_numeric_solve_count=[1, 1, 1], new_Gram_matrix_count=0, new_Gram_factor_count=0,
                    counts=packet.counts, **POLICY), dict(reference=reference_path)
    finally:
        destroy_same_mesh_physical_action(model["bundle"])


def compare(design, native_index, reference_index, checks_index, p4_index, artifact, marker, manifest):
    """Freeze-before-load comparison; no new Maxwell CSR or factor."""
    import ufl
    from dolfinx import fem
    from src.solvers.feinn_fem import build_model
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action, restore_p0_full_field
    tick, cutoff = clock(manifest)
    if not p4_index["result"]["reference_qualified"]:
        raise RuntimeError("P4_REFERENCE_NOT_QUALIFIED_FOR_COMPARISON")
    packet3, c3, original = load_p3(native_index, reference_index)
    packet4 = load_native(checks_index["files"]["native"]["path"])
    with np.load(p4_index["files"]["reference"]["path"], allow_pickle=False) as saved:
        c4 = np.array(saved["c_scattered"])
        alpha4 = np.array(saved["alpha_total"])
    if np.linalg.norm(alpha4 - packet4.a["background_alpha"] - packet4.alpha(c4)) / np.linalg.norm(alpha4) > 1e-10:
        raise ValueError("P4_FROZEN_PORT_IDENTITY_FAILED")
    model = build_model(design, degree=4, marker=marker, dtn_quadrature_degree=15)
    try:
        equivalence = verify_model(model, original)
        _, f3 = p3_on_same_mesh(model, packet3)
        fields = {}
        for kind in ("total", "scattered"):
            left = c3 + packet3.a["background"] if kind == "total" else c3
            right = c4 + packet4.a["background"] if kind == "total" else c4
            fields[kind] = (restore_p0_full_field(f3, packet3.storage(left)),
                            restore_p0_full_field(model["floquet"], packet4.storage(right)))
        k0 = model["cfg"].k0
        msh = model["data"].mesh
        natural = float(np.sqrt(np.prod([axis[-1] - axis[0] for axis in model["axes"]])))
        def energies(E, q=15, indicator=1):
            tick("common energy degree " + str(q))
            dx = ufl.Measure("dx", domain=msh, metadata={"quadrature_degree": q})
            raw = [fem.assemble_scalar(fem.form(indicator * form * dx)) for form in (ufl.inner(E, E), ufl.inner(ufl.curl(E), ufl.curl(E)) / k0**2)]
            return np.array([positive_energy(v, max(natural**2, abs(v))) for v in raw])
        errors, energy_pairs = {}, {}
        for kind, (left, right) in fields.items():
            le, re, de = energies(left), energies(right), energies(left - right)
            energy_pairs[kind] = dict(p3=le, p4=re, difference=de)
            for j, name in enumerate(("L2", "scaled_curl")):
                errors[kind + "_" + name] = difference_record(np.sqrt(le[j]), np.sqrt(re[j]), np.sqrt(de[j]), natural)
        # Exactly one q30 difference-only pass for each total/scattered field.
        qchecks = {}
        for kind, (left, right) in fields.items():
            q30 = energies(left - right, q=30)
            q15 = np.asarray(energy_pairs[kind]["difference"])
            scale = np.maximum(np.asarray(energy_pairs[kind]["p4"]), 1e-24 * natural**2)
            qchecks[kind] = dict(degree15=q15, degree30=q30, denominator_energy=scale,
                                 normalized_absolute_difference=abs(q30 - q15) / scale)
        points = np.array([[-4.375, -3.125, -.625], [-4.375, -3.125, .625], [-1.875, -.625, 3.125], [.625, -.625, 3.125], [1.875, 3.125, 6.875], [-.625, -1.875, 8.125]])
        cells = np.argmin(np.linalg.norm(model["centers"][:, None] - points[None], axis=2), axis=0).astype(np.int32)
        if np.max(np.linalg.norm(model["centers"][cells] - points, axis=1)) > 1e-12:
            raise ValueError("SAMPLE_REFERENCE_COORDINATES_FAILED")
        samples = {}
        for kind, (left, right) in fields.items():
            values = {}
            for name, E in (("p3", left), ("p4", right)):
                values[name] = dict(E=E.eval(points, cells), H_code=fem.Expression(ufl.curl(E) / (1j * k0 * model["cfg"].mu_r), np.array([[.5, .5, .5]])).eval(msh, cells).reshape(len(cells), 3))
            samples[kind] = values
            for quantity in ("E", "H_code"):
                left_value, r = values["p3"][quantity], values["p4"][quantity]
                errors[kind + "_selected_" + quantity] = difference_record(np.linalg.norm(left_value), np.linalg.norm(r), np.linalg.norm(left_value-r), 1)
                for point in range(len(points)):
                    errors[kind + "_selected_" + quantity + "_point_" + str(point)] = difference_record(np.linalg.norm(left_value[point]), np.linalg.norm(r[point]), np.linalg.norm(left_value[point]-r[point]), 1)
        tags = np.asarray(model["tags"])
        msh.topology.create_connectivity(2, 3)
        links = msh.topology.connectivity(2, 3)
        near = set()
        for facet in range(msh.topology.index_map(2).size_local):
            adjacent = links.links(facet)
            if len(adjacent) == 2 and tags[adjacent[0]] != tags[adjacent[1]]:
                near.update(int(c) for c in adjacent)
        regions = dict(air=np.flatnonzero(tags == 1), substrate=np.flatnonzero(tags == 2), grating=np.flatnonzero(tags == 3), interface_near=np.array(sorted(near)))
        dg0 = fem.functionspace(msh, ("DG", 0))
        regional = {}
        for name, cell_ids in regions.items():
            indicator = fem.Function(dg0)
            indicator.x.array[:] = 0
            for cell in cell_ids:
                indicator.x.array[dg0.dofmap.cell_dofs(int(cell))[0]] = 1
            regional[name] = dict(cells=len(cell_ids), cell_ids=cell_ids, cell_ids_sha256=array_hash(cell_ids.astype(np.int32)), fields={})
            for kind, (left, right) in fields.items():
                le, re, de = energies(left, indicator=indicator), energies(right, indicator=indicator), energies(left-right, indicator=indicator)
                regional[name]["fields"][kind] = {key: difference_record(np.sqrt(le[j]), np.sqrt(re[j]), np.sqrt(de[j]), natural * np.sqrt(len(cell_ids)/len(tags))) for j, key in enumerate(("L2", "scaled_curl"))}
        # Original reference physical observables are reused by physical key,
        # side, polarization and reference plane, rather than file row number.
        physics3 = reference_index["result"]["physics"]
        physics4 = p4_index["result"]["physics"]
        def complex_values(values):
            return np.asarray([complex(v["real"], v["imag"]) for v in values])
        rows3 = original["identity"]["modes"]
        rows4 = p4_index["result"]["identity"]["modes"]
        def key(row):
            return channel_key(row, model["cfg"].z_max, model["cfg"].z_min)
        positions = {key(row): j for j, row in enumerate(rows4)}
        if len(positions) != 40 or set(positions) != {key(row) for row in rows3}:
            raise ValueError("CHANNEL_PHYSICAL_KEY_ALIGNMENT_FAILED")
        ordering = np.asarray([positions[key(row)] for row in rows3], dtype=int)
        records3, records4 = physics3["records"]["REFERENCE"], physics4["records"]["REFERENCE"]
        channels = {}
        for name in ("total", "outgoing", "boundary_outgoing", "scattered"):
            field = "ordered_complex_" + name + "_channels"
            left_value, r = complex_values(records3[field]), complex_values(records4[field])[ordering]
            channels[name] = dict(p3=left_value, p4=r, difference=left_value-r, error=difference_record(np.linalg.norm(left_value), np.linalg.norm(r), np.linalg.norm(left_value-r), 1))
            errors["channels_" + name] = channels[name]["error"]
        powers3 = np.asarray(records3["ordered_per_channel_power"])
        powers4 = np.asarray(records4["ordered_per_channel_power"])[ordering]
        powers = dict(keys=rows3, p3=powers3, p4=powers4, difference=powers3-powers4,
                      max_absolute=float(np.max(abs(powers3-powers4))))
        observables = {}
        for name in ("R_total", "T_total", "A_balance", "R00_s", "R00_p", "R00_total"):
            left_value, r = records3["port"][name], records4["port"][name]
            observables[name] = dict(p3=left_value, p4=r, difference=left_value-r, absolute=abs(left_value-r))
        left_value, r = records3["volume"]["A_volume_total"], records4["volume"]["A_volume_total"]
        observables["A_volume"] = dict(p3=left_value, p4=r, difference=left_value-r, absolute=abs(left_value-r))
        q_pass = all(max(v["normalized_absolute_difference"]) <= 1e-10 for v in qchecks.values())
        main_pass = all(v["relative"] <= 1e-3 for v in errors.values()) and all(observables[k]["absolute"] <= 1e-4 for k in ("R_total", "T_total", "A_balance", "A_volume")) and powers["max_absolute"] <= 1e-4
        region_pass = all(v["relative"] <= 1e-3 for reg in regional.values() for f in reg["fields"].values() for v in f.values())
        status = "COMPARISON_QUADRATURE_UNRESOLVED" if not q_pass else ("P3_P4_SMALL_CHANGE_LIMITED" if main_pass else "P3_P4_SENSITIVITY_OBSERVED")
        return dict(status=status, comparison_qualified=q_pass, small_change_signal=main_pass and q_pass,
                    local_sensitivity_remains=main_pass and not region_pass, errors=errors, energy_pairs=energy_pairs,
                    quadrature=qchecks, samples=samples, points_nm=points, cells=cells, reference_coordinates=[.5,.5,.5],
                    regions=regional, channels=channels, powers=powers, observables=observables,
                    H_code_meaning="curl(E)/(i k0 mu_r); mu_r=1; SI H requires impedance/unit conversion",
                    p3_energy_closure=physics3["reference_energy_closure_absolute"], p4_energy_closure=physics4["reference_energy_closure_absolute"],
                    physics_equivalence_fields=equivalence, channel_alignment_p4_indices=ordering,
                    numeric_cutoff_monotonic=cutoff, global_phase_fit=False,
                    MUMPS_symbolic_numeric_solve_count=[0,0,0], new_Gram_matrix_count=0, new_Gram_factor_count=0, **POLICY), {}
    finally:
        destroy_same_mesh_physical_action(model["bundle"])
