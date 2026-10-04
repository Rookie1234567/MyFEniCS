"""Independent same-mesh p3 witness, permitted only after all routes freeze.

The single global p3 reference LU is released before native FE/power/field
verification. Candidates never import or call this reference-only module.
"""

from pathlib import Path
from time import perf_counter

import numpy as np

from src.solvers.neural_fe_action_packet import (
    array_hash,
    file_hash,
    operation_relative,
)


def reference_csr(packet):
    from scipy import sparse

    a = packet.a
    rows, cols, values = [], [], []
    for cell in range(packet.nc):
        selected = (a["erows"] // packet.lt) == cell
        local_rows = a["erows"][selected] % packet.lt
        ids = a["eids"][selected]
        active = np.unique(ids)
        E = sparse.coo_matrix(
            (a["evals"][selected], (local_rows, np.searchsorted(active, ids))),
            shape=(packet.lt, len(active)),
        ).toarray()
        block = E.conj().T @ a["S"][a["classes"][cell]] @ E
        rows.append(np.repeat(active, len(active)))
        cols.append(np.tile(active, len(active)))
        values.append(block.ravel())
        B = E.conj().T @ a["Bhat"][cell]
        D = -a["Dhat"][cell] @ E
        for block, rr, cc in (
            (B, active, np.arange(packet.np) + packet.nt),
            (D, np.arange(packet.np) + packet.nt, active),
        ):
            r, c = np.nonzero(block)
            rows.append(rr[r])
            cols.append(cc[c])
            values.append(block[r, c])
    rr, cc = np.nonzero(a["Hhat"])
    rows.extend([rr + packet.nt, a["br"], a["dp"] + packet.nt])
    cols.extend([cc + packet.nt, a["bp"] + packet.nt, a["dr"]])
    values.extend([a["Hhat"][rr, cc], a["bv"], -a["dv"]])
    matrix = sparse.coo_matrix(
        (np.concatenate(values), (np.concatenate(rows), np.concatenate(cols))),
        shape=(packet.size, packet.size),
    ).tocsr()
    matrix.sum_duplicates()
    matrix.eliminate_zeros()  # exact zero only, no numerical sparsification.
    return matrix


def blind_reference(design, packet, route_records, artifact, *, sample, marker, save):
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.solvers.condensed_fine_reference import numeric_allowance
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor

    began = perf_counter()
    artifact = Path(artifact)
    costs = {}
    # Check all immutable candidate states before constructing a reference.
    states = {}
    frozen = {}
    if set(route_records) != {"NEURAL-TRACE", "FREE-FE-OPT", "FE-LSQR"}:
        raise ValueError("all three terminated routes are required before reference")
    for route, record in route_records.items():
        state = record["state"]
        path = Path(state["path"]).resolve()
        if (
            not path.is_relative_to(Path(record["artifact_directory"]))
            or file_hash(path) != state["sha256"]
        ):
            raise ValueError("candidate state was not frozen before blind reference")
        with np.load(path, allow_pickle=False) as data:
            states[route] = np.array(data["z"])
        if array_hash(states[route]) != state["z_sha256"]:
            raise ValueError("candidate frozen vector hash mismatch")
        if (
            states[route].shape != (packet.size,)
            or not np.isfinite(states[route]).all()
        ):
            raise ValueError("invalid frozen candidate vector")
        frozen[route] = dict(
            state=state,
            source_sha=record["source_sha"],
            final_audit=record["final_audit"],
        )
    save("all_candidates_frozen_before_reference", frozen)
    resource = sample()
    # Retained COO blocks, concatenation, CSR/PETSc copies and conversion
    # workspace. This is a conservative allocation bound, not measured RSS.
    triplets = packet.nc * (packet.lt**2 + 2 * packet.lt * packet.np)
    triplets += packet.np**2 + len(packet.a["bv"]) + len(packet.a["dv"])
    assembly_upper = 4 * triplets * 32 + 512 * 2**20
    assembly_gate = dict(
        allocation_upper_bytes=assembly_upper,
        tree_rss_before_bytes=resource["rss_bytes"],
        planning_cap_bytes=12 * 2**30,
        status="ADMISSIBLE"
        if resource["rss_bytes"] + assembly_upper < 12 * 2**30
        else "CAPACITY_NOT_ADMITTED",
        kind="reference-only assembly allocation bound, not measured peak",
    )
    save("reference_pre_assembly_capacity", assembly_gate)
    if assembly_gate["status"] != "ADMISSIBLE":
        return dict(
            status="REFERENCE_CAPACITY_NOT_ADMITTED",
            capacity=assembly_gate,
            comparisons={},
            p4_enrichment="NOT_RUN_REFERENCE_GATE",
        )
    start = perf_counter()
    csr = reference_csr(packet)
    rng = np.random.default_rng(420909)
    witness = rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)
    difference = operation_relative(
        np.linalg.norm(csr @ witness - packet.apply(witness)),
        np.linalg.norm(csr @ witness),
    )
    if difference > 1e-10:
        raise ValueError("independent reference S CSR/action mismatch")
    matrix = PETSc.Mat().createAIJ(
        size=csr.shape,
        csr=(
            np.asarray(csr.indptr, dtype=PETSc.IntType),
            np.asarray(csr.indices, dtype=PETSc.IntType),
            csr.data,
        ),
        comm=MPI.COMM_WORLD,
    )
    matrix.assemble()
    nnz = int(csr.nnz)
    del csr
    costs["reference_matrix_build_check"] = perf_counter() - start
    factor = None
    vectors = []
    reference = None
    record = dict(
        global_p3_reference_factor=True,
        global_p4_factor=False,
        reference_only=True,
        deployed_in_candidates=False,
        rows=packet.size,
        nnz=nnz,
        matrix_action_pair=difference,
        symbolic_calls=0,
        numeric_calls=0,
        solve_calls=0,
        factor_released=False,
    )
    try:
        factor = _MumpsFactor(matrix)
        start = perf_counter()
        marker("reference_symbolic", dict(rows=packet.size, nnz=nnz))
        factor.symbolic(matrix)
        record["symbolic_calls"] = 1
        record["symbolic_info"] = factor.info((22, 29))
        record["mumps_memory_settings"] = factor.symbolic_memory_settings()
        costs["symbolic"] = perf_counter() - start
        resource = sample()
        resource["numeric_planning_cap_bytes"] = 12 * 2**30
        admission = numeric_allowance(
            resource, record["symbolic_info"], 2 * 2**30 + 16 * packet.full_rows * 16
        )
        record["numeric_admission"] = admission
        save("reference_symbolic_gate", record)
        if (
            admission["status"] != "ADMISSIBLE"
            or record["mumps_memory_settings"]["icntl"]["22"] != 0
        ):
            return dict(
                status="REFERENCE_CAPACITY_NOT_ADMITTED",
                factor=record,
                costs_exclusive_seconds=costs,
                comparisons={},
                p4_enrichment="NOT_RUN_REFERENCE_GATE",
            )
        factor.set_memory_limit_mb(admission["icntl23_mb"])
        start = perf_counter()
        marker("reference_numeric", admission)
        factor.numeric(matrix)
        record["numeric_calls"] = 1
        record["numeric_info"] = factor.info((22, 29))
        costs["numeric"] = perf_counter() - start
        b = matrix.createVecRight()
        x = matrix.createVecRight()
        delta = matrix.createVecRight()
        vectors.extend([b, x, delta])
        b.array[:] = packet.a["b"]
        start = perf_counter()
        factor.solve(b, x)
        record["solve_calls"] = 1
        first = packet.a["b"] - packet.apply(x.array)
        record["initial_schur_relative"] = float(np.linalg.norm(first) / packet.bnorm)
        # One explicit correction using the same factor; no re-factor or scan.
        if record["initial_schur_relative"] > 1e-10:
            b.array[:] = first
            factor.solve_repeated(b, delta)
            x.array[:] += delta.array
            record["solve_calls"] += 1
        reference = x.array.copy()
        if not np.isfinite(reference).all():
            raise ValueError("nonfinite accurate reference")
        costs["solve_and_optional_one_correction"] = perf_counter() - start
    finally:
        start = perf_counter()
        if factor is not None:
            factor.destroy()
            record["factor_released"] = factor.destroyed
        for vector in vectors:
            vector.destroy()
        matrix.destroy()
        costs["factor_matrix_release"] = perf_counter() - start
        save("factor_lifecycle", record)
    np.savez(artifact / "accurate_reference_state.npz", z=reference)
    reference_state = dict(
        path=str(artifact / "accurate_reference_state.npz"),
        sha256=file_hash(artifact / "accurate_reference_state.npz"),
        z_sha256=array_hash(reference),
    )
    start = perf_counter()
    audit = packet.audit(reference)
    costs["reference_original_packet_audit"] = perf_counter() - start
    save("reference_original_audit", audit)
    if any(
        audit[key] > 1e-10
        for key in (
            "schur_relative",
            "native_relative",
            "augmented_relative",
            "port_operation_relative",
            "recovery_relative",
            "original_total_augmented_relative",
        )
    ):
        return dict(
            status="REFERENCE_ACCURACY_UNRESOLVED",
            factor=record,
            reference_audit=audit,
            reference_state=reference_state,
            costs_exclusive_seconds=costs,
            comparisons={},
            p4_enrichment="NOT_RUN_REFERENCE_ACCURACY",
        )
    marker("factor_released_begin_independent_FE_physics", {})
    save("reference_costs_before_physics", costs)
    start = perf_counter()
    physics, comparisons = independent_physics(
        design, packet, reference, states, artifact
    )
    costs["independent_FE_rebuild_all_fields_power_and_io"] = perf_counter() - start
    return dict(
        status="BLIND_REFERENCE_COMPLETE"
        if physics["reference_native_pass"]
        else "REFERENCE_NATIVE_AUDIT_UNRESOLVED",
        reference_audit=audit,
        reference_state=reference_state,
        factor=record,
        physics=physics,
        comparisons=comparisons,
        candidates_frozen=frozen,
        costs_exclusive_seconds=costs,
        worker_numerical_seconds=perf_counter() - began,
        p4_enrichment="CONDITIONAL_NOT_YET_RUN",
        reference_before_training=False,
        no_reference_feedback_to_training=True,
    )


def l2_scaled_curl_forms(field, k0, dx):
    import ufl

    return (
        ufl.real(ufl.inner(field, field)) * dx,
        (ufl.real(ufl.inner(ufl.curl(field), ufl.curl(field))) / k0**2) * dx,
    )


def verify_saved_reference(design, packet, route_records, identity, artifact):
    """Replay only postprocessing after the single recorded UFL wiring fix."""
    import json

    began = perf_counter()
    original = Path(identity["original_artifact"]).resolve()
    records = {}
    for name, entry in identity["files"].items():
        path = Path(entry["path"]).resolve()
        if file_hash(path) != entry["sha256"]:
            raise ValueError("saved-reference identity/hash failure")
        records[name] = path
    lifecycle = json.loads(records["factor_lifecycle"].read_text())
    if (
        not lifecycle["factor_released"]
        or lifecycle["numeric_calls"] != 1
        or lifecycle["global_p4_factor"]
        or lifecycle["rows"] != packet.size
    ):
        raise ValueError("released reference-only factor lifecycle required")
    with np.load(records["reference_vector"], allow_pickle=False) as data:
        reference = np.array(data["z"])
    if reference.shape != (packet.size,) or not np.isfinite(reference).all():
        raise ValueError("invalid saved reference vector")
    states = {}
    if set(route_records) != {"NEURAL-TRACE", "FREE-FE-OPT", "FE-LSQR"}:
        raise ValueError("all three original frozen candidates required")
    previous = json.loads(records["candidates_frozen"].read_text())
    for route, record in route_records.items():
        state = record["state"]
        if (
            state != previous[route]["state"]
            or file_hash(state["path"]) != state["sha256"]
        ):
            raise ValueError("candidate was changed after reference")
        with np.load(state["path"], allow_pickle=False) as data:
            states[route] = np.array(data["z"])
        if array_hash(states[route]) != state["z_sha256"]:
            raise ValueError("original frozen candidate vector hash mismatch")
    audit = packet.audit(reference)
    if any(
        audit[k] > 1e-10
        for k in (
            "schur_relative",
            "native_relative",
            "augmented_relative",
            "port_operation_relative",
            "recovery_relative",
            "original_total_augmented_relative",
        )
    ):
        raise ValueError("saved accurate reference failed original-equation recheck")
    costs = dict(saved_identity_and_original_recheck=perf_counter() - began)
    start = perf_counter()
    physics, comparisons = independent_physics(
        design, packet, reference, states, Path(artifact)
    )
    costs["independent_FE_rebuild_all_fields_power_and_io"] = perf_counter() - start
    return dict(
        status="BLIND_REFERENCE_COMPLETE"
        if physics["reference_native_pass"]
        else "REFERENCE_NATIVE_AUDIT_UNRESOLVED",
        reference_audit=audit,
        reference_state=dict(
            path=str(records["reference_vector"]),
            sha256=file_hash(records["reference_vector"]),
            z_sha256=array_hash(reference),
        ),
        factor=lifecycle,
        physics=physics,
        comparisons=comparisons,
        original_reference=identity,
        reused_original_artifact=str(original),
        symbolic_calls_this_run=0,
        numeric_calls_this_run=0,
        solve_calls_this_run=0,
        replay_scope="only FE/E/H/power checks; same saved p3 reference and candidates",
        costs_exclusive_seconds=costs,
        worker_numerical_seconds=perf_counter() - began,
        p4_enrichment="CONDITIONAL_NOT_YET_RUN",
        reference_before_training=False,
        no_reference_feedback_to_training=True,
    )


def independent_physics(design, packet, reference, states, artifact, *, offline_diagnostic=None, audit_function=None):
    import ufl
    from dolfinx import fem

    from src.common.modes_3d import incident_power_3d
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.postprocessing.rta_3d import compute_volume_absorption_3d
    from src.solvers.dtn_port_3d import (
        _mode_carries_outward_power,
        _mode_power_at_boundary,
        _outgoing_projection,
        _port_power_metrics,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
        restore_p0_full_field,
    )
    from src.solvers.learned_coarse_inverse import native_numpy_apply
    from src.solvers.neural_fe_pilot import physical_inventory
    from src.solvers.neural_trace_dolfinx import pilot_space

    physical, (cfg, modes, rows, mode_hash) = physical_inventory(design)
    _, data, space, centers, _, _, _ = pilot_space(design)
    if not np.array_equal(
        np.asarray(space.dofmap.list)[:, space.element.basix_element.entity_dofs[3][0]],
        packet.a["idofs"],
    ):
        raise ValueError("same-mesh reference recovery/FE numbering mismatch")
    floquet = build_double_floquet_mpc(space, data, cfg)
    setup = dict(
        mesh=data.mesh, mesh_data=data, spaces={3: space}, floquets={3: floquet}
    )
    bundle = build_same_mesh_physical_action(
        setup,
        cfg,
        3,
        mode_inventory=(modes, rows, mode_hash),
        volume_quadrature_metadata=(
            {"quadrature_degree": 15},
            {"quadrature_degree": 15},
        ),
    )
    try:
        native = native_numpy_apply(bundle)
        all_states = {"REFERENCE": reference, **states}
        reference_total = packet.a["background"] + packet.recover(reference)
        refE = restore_p0_full_field(floquet, reference_total)
        ref_scattered = restore_p0_full_field(floquet, packet.recover(reference))
        dx = ufl.Measure("dx", domain=data.mesh, metadata={"quadrature_degree": 15})

        def norms(field):
            l2_form, curl_form = l2_scaled_curl_forms(field, cfg.k0, dx)
            l2 = float(fem.assemble_scalar(fem.form(l2_form)).real)
            curl = float(fem.assemble_scalar(fem.form(curl_form)).real)
            return np.sqrt(max(l2, 0)), np.sqrt(max(curl, 0))

        ref_norm = np.asarray(norms(refE))
        ref_sca_norm = np.asarray(norms(ref_scattered))
        diagnostic = None
        if offline_diagnostic is not None:
            try:
                diagnostic = offline_diagnostic(dict(
                    reference=reference, states=states,
                    restore=lambda values: restore_p0_full_field(floquet, values),
                    norms=norms, dx=dx, k0=cfg.k0,
                ))
            except Exception as error:
                # This optional, frozen representation check cannot block the
                # independent checks of the saved physical candidates.
                diagnostic = dict(status="OFFLINE_DIAGNOSTIC_FAILED",
                                  error=type(error).__name__ + ": " + str(error),
                                  reference_feedback=False)
        points = np.array(
            [
                [-0.6125, -0.4375, -0.0875],
                [-0.6125, -0.4375, 0.0875],
                [-0.2625, -0.0875, 0.4375],
                [0.0875, 0.0875, 0.4375],
                [0.2625, 0.4375, 0.9625],
                [-0.0875, -0.2625, 1.1375],
            ]
        )
        cells = np.argmin(
            np.linalg.norm(centers[:, None, :] - points[None, :, :], axis=2), axis=0
        ).astype(np.int32)
        if np.max(np.linalg.norm(centers[cells] - points, axis=1)) > 1e-12:
            raise ValueError("selected E/H points must be fixed micro cell centers")

        def samples(field):
            E = field.eval(points, cells)
            H_expression = fem.Expression(
                ufl.curl(field) / (1j * cfg.k0 * cfg.mu_r), np.array([[0.5, 0.5, 0.5]])
            )
            H = np.asarray(H_expression.eval(data.mesh, cells)).reshape(len(cells), 3)
            return E, H

        ref_E, ref_H = samples(refE)
        records = {}
        for name, z in all_states.items():
            a = (packet.audit if audit_function is None else audit_function)(z)
            total = packet.a["background"] + packet.recover(z)
            field = restore_p0_full_field(floquet, total)
            alpha = packet.a["background_alpha"] + z[packet.nt :]
            native_r = packet.a["total_g"] - native(total)
            a["independent_DOLFINx_total_native_relative"] = float(
                np.linalg.norm(native_r) / np.linalg.norm(packet.a["total_g"])
            )
            port = _port_power_metrics(
                cfg, list(modes), alpha, list(bundle["incident_projections"])
            )
            output = artifact / ("diagnostic_" + name.lower().replace("-", "_"))
            volume = compute_volume_absorption_3d(
                data,
                cfg,
                field,
                output,
                incident_power=incident_power_3d(cfg),
                port_metrics=port,
            )
            E, H = samples(field)
            per_power = []
            for mode, value, inc in zip(
                modes, alpha, bundle["incident_projections"], strict=True
            ):
                outgoing = _outgoing_projection(value, inc, mode.side)
                per_power.append(
                    _mode_power_at_boundary(mode, cfg, outgoing)
                    / incident_power_3d(cfg)
                    if _mode_carries_outward_power(mode)
                    else 0.0
                )
            records[name] = dict(
                audit=a,
                port=port,
                volume=volume,
                ordered_complex_port_vector=alpha,
                ordered_complex_scattered_port_vector=z[packet.nt :],
                ordered_per_channel_power=per_power,
                selected_E=E,
                selected_H_code=H,
                points_nm=points,
                L2_and_scaled_curl_norms=norms(field),
                official_candidate_results=False,
                output_role="independent reference"
                if name == "REFERENCE"
                else "unqualified diagnostic until all Gates pass",
            )
            if name != "REFERENCE":
                difference = restore_p0_full_field(floquet, total - reference_total)
                errors = np.asarray(norms(difference))
                records[name].update(
                    full_FE_L2_relative=float(errors[0] / ref_norm[0]),
                    full_FE_scaled_curl_relative=float(errors[1] / ref_norm[1]),
                    scattered_FE_L2_relative=operation_relative(
                        errors[0], ref_sca_norm[0]
                    ),
                    scattered_scaled_curl_relative=operation_relative(
                        errors[1], ref_sca_norm[1]
                    ),
                    selected_E_relative=operation_relative(
                        np.linalg.norm(E - ref_E), np.linalg.norm(ref_E)
                    ),
                    selected_H_relative=operation_relative(
                        np.linalg.norm(H - ref_H), np.linalg.norm(ref_H)
                    ),
                )
        ref = records["REFERENCE"]
        reference_native_pass = bool(
            np.isfinite(ref["audit"]["independent_DOLFINx_total_native_relative"])
            and ref["audit"]["independent_DOLFINx_total_native_relative"] <= 1e-10
        )
        comparisons = {}
        for name in states:
            record = records[name]
            port_vector_relative = operation_relative(
                np.linalg.norm(
                    record["ordered_complex_port_vector"]
                    - ref["ordered_complex_port_vector"]
                ),
                np.linalg.norm(ref["ordered_complex_port_vector"]),
            )
            power_differences = {
                key: abs(record["port"][key] - ref["port"][key])
                for key in ("R_total", "T_total", "A_balance")
            }
            power_differences["A_volume"] = abs(
                record["volume"]["A_volume_total"] - ref["volume"]["A_volume_total"]
            )
            channel_difference = float(
                np.max(
                    np.abs(
                        np.asarray(record["ordered_per_channel_power"])
                        - ref["ordered_per_channel_power"]
                    )
                )
            )
            closure = abs(record["volume"]["energy_closure_error_port_volume"])
            field_pass = all(
                record[k] <= 1e-4
                for k in (
                    "full_FE_L2_relative",
                    "full_FE_scaled_curl_relative",
                    "selected_E_relative",
                    "selected_H_relative",
                )
            )
            passed = (
                reference_native_pass
                and record["audit"]["strict_pass"]
                and record["audit"]["recovery_relative"] <= 1e-10
                and record["audit"]["independent_DOLFINx_total_native_relative"] <= 1e-6
                and field_pass
            )
            passed &= (
                port_vector_relative <= 1e-4
                and all(v <= 1e-5 for v in power_differences.values())
                and channel_difference <= 1e-6
                and closure <= 1e-5
            )
            comparisons[name] = dict(
                status="SAME_DISCRETE_QUALIFIED" if passed else "NOT_QUALIFIED",
                equation_audit=record["audit"],
                full_FE_L2_relative=record["full_FE_L2_relative"],
                full_FE_scaled_curl_relative=record["full_FE_scaled_curl_relative"],
                selected_E_relative=record["selected_E_relative"],
                selected_H_relative=record["selected_H_relative"],
                scattered_FE_L2_relative=record["scattered_FE_L2_relative"],
                ordered_complex_ports_relative=port_vector_relative,
                power_absolute_differences=power_differences,
                max_channel_power_difference=channel_difference,
                energy_closure_absolute=closure,
            )
        result = dict(
            physical=physical,
            reference_norms=ref_norm,
            reference_scattered_norms=ref_sca_norm,
            reference_scattered_port_norm=float(np.linalg.norm(reference[packet.nt :])),
            background_port_norm=float(np.linalg.norm(packet.a["background_alpha"])),
            reference_native_pass=reference_native_pass,
            near_zero_absolute_threshold=1e-12,
            rows=records,
            reference_feedback=False,
            large_field_files_written=False,
        )
        if offline_diagnostic is not None:
            result["offline_diagnostic"] = diagnostic
        return result, comparisons
    finally:
        destroy_same_mesh_physical_action(bundle)
