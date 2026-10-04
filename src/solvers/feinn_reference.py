"""Independent original augmented authority, imported only after routes freeze."""

import ctypes
import gc
from time import perf_counter

import numpy as np
from scipy import sparse

from src.solvers.feinn_native import load_native
from src.solvers.feinn_riesz import rss_bytes
from src.solvers.neural_fe_action_packet import array_hash


def candidate_policy(numerical_pass, *, reference_exposed=False):
    """A tagged fit cannot be promoted by a numerical field comparison."""
    return dict(
        numerical_reconstruction_pass=bool(numerical_pass),
        pde_only_solver_qualified=bool(numerical_pass and not reference_exposed),
        official_candidate_results=bool(numerical_pass and not reference_exposed),
        reference_used_for_training=bool(reference_exposed),
        pde_only_solve=not reference_exposed,
        production_initialization_allowed=not reference_exposed,
    )


def original_augmented_matrix(model, packet, marker=lambda *_: None):
    """Independent DOLFINx assembly of V; preserve original unnormalized ports."""
    import dolfinx_mpc
    from dolfinx import fem

    marker("authority_form_begin", {})
    compiled = fem.form(model["bundle"]["volume_action"].bilinear_form)
    marker("authority_form_end", {})
    marker("authority_MPC_assembly_begin", {})
    matrix = dolfinx_mpc.assemble_matrix(compiled, model["floquet"].mpc)
    marker("authority_MPC_assembly_end", {})
    try:
        marker("authority_Mat_assemble_begin", {})
        matrix.assemble()
        marker("authority_Mat_assemble_end", {})
        marker("authority_CSR_conversion_begin", {})
        p, i, x = matrix.getValuesCSR()
        full = sparse.csr_matrix((x.copy(), i.copy(), p.copy()), shape=matrix.getSize())
    finally:
        matrix.destroy()
    ids = packet.a["masters"]
    V = full[ids, :][:, ids].tocsr()
    marker("authority_CSR_conversion_end", {})
    a = packet.a
    B = sparse.coo_matrix(
        (a["bv"], (a["br"], a["bp"])), shape=(packet.size, packet.np)
    ).tocsr()
    D = sparse.coo_matrix(
        (a["dv"], (a["dp"], a["dr"])), shape=(packet.np, packet.size)
    ).tocsr()
    marker("authority_port_join_begin", {})
    augmented = sparse.bmat([[V, B], [-D, sparse.diags(a["H"])]], format="csr")
    augmented.eliminate_zeros()
    augmented.sort_indices()
    marker("authority_port_join_end", {})
    rng = np.random.default_rng(421003)
    c = rng.standard_normal(packet.size) + 1j * rng.standard_normal(packet.size)
    alpha = rng.standard_normal(packet.np) + 1j * rng.standard_normal(packet.np)
    original = np.r_[packet.volume(c) + packet.B(alpha), -packet.D(c) + a["H"] * alpha]
    difference = np.linalg.norm(
        augmented @ np.r_[c, alpha] - original
    ) / np.linalg.norm(original)
    if difference > 1e-10:
        raise ValueError(f"independent augmented CSR/action mismatch {difference}")
    return augmented, float(difference)


def exact_solve(model, packet, artifact, marker, *, audit_options=None):
    """Reference-only MUMPS with symbolic capacity, destruction before physics."""
    from mpi4py import MPI
    from petsc4py import PETSc
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor

    start = perf_counter()
    # Only the separately reviewed authority audit supplies these hooks.
    # Existing callers retain their historical lifecycle and packet schema.
    check_budget = (audit_options or {}).get("check_budget", lambda *_: None)
    tolerance = (audit_options or {}).get("residual_tolerance", 1e-10)
    final_ports = (audit_options or {}).get("final_port_recovery")
    actual_audit = (audit_options or {}).get("full_equation_audit", lambda c,a: packet.audit(c))
    check_budget("reference assembly")
    reduced = (audit_options or {}).get("reduced_system")
    n = len(reduced.rhs) if reduced is not None else packet.size + packet.np
    nnz_upper = (
        packet.nc * packet.dim**2
        + len(packet.a["bv"])
        + len(packet.a["dv"])
        + packet.np
    )
    if reduced is not None:
        nnz_upper = (
            packet.nc * len(reduced.t) ** 2
            + len(packet.a["bv"])
            + len(packet.a["dv"])
            + packet.np
        )
    allocation = (audit_options or {}).get(
        "allocation_upper_bytes", nnz_upper * 80 + 512 * 2**20
    )
    pre = dict(
        kind="derived reference assembly/conversion reserve, not RSS",
        rows=n,
        upper_triplets=nnz_upper,
        allocation_upper_bytes=allocation,
        own_rss_bytes=rss_bytes(),
        planning_cap_bytes=12 * 2**30,
    )
    marker("reference_pre_assembly_capacity", pre)
    if rss_bytes() + allocation >= 12 * 2**30:
        raise RuntimeError("REFERENCE_RESOURCE_BLOCKED_BEFORE_ASSEMBLY")
    assembler = (audit_options or {}).get("assembler", original_augmented_matrix)
    csr, pair = assembler(model, packet, marker)
    record = dict(
        role="independent reference ONLY",
        global_Maxwell_factor=True,
        training_fallback=False,
        preassembly=pre,
        rows=n,
        nnz=csr.nnz,
        independent_augmented_action_relative=pair,
        csr_payload_bytes=sum(v.nbytes for v in (csr.indptr, csr.indices, csr.data)),
        CSR_hashes={
            k: array_hash(v)
            for k, v in [
                ("indptr", csr.indptr),
                ("indices", csr.indices),
                ("data", csr.data),
            ]
        },
    )
    marker("reference_PETSc_conversion_begin", {})
    matrix = PETSc.Mat().createAIJ(
        size=csr.shape,
        csr=(
            csr.indptr.astype(PETSc.IntType),
            csr.indices.astype(PETSc.IntType),
            csr.data,
        ),
        comm=MPI.COMM_WORLD,
    )
    matrix.assemble()
    marker("reference_PETSc_conversion_end", {})
    del csr
    gc.collect()
    record["assembly_and_pair_seconds"] = perf_counter() - start
    factor = None
    b = x = residual = None
    try:
        check_budget("reference symbolic")
        factor = _MumpsFactor(matrix)
        t = perf_counter()
        marker("reference_symbolic_begin", {})
        factor.symbolic(matrix)
        info = factor.info((21, 22, 29))
        record["symbolic_info"] = info
        if audit_options is not None:
            memory_mb = int(info["infog"]["17"])
            if memory_mb <= 0:
                raise RuntimeError(
                    "P4_REFERENCE_RESOURCE_BLOCKED_SYMBOLIC_ESTIMATE_UNAVAILABLE"
                )
            record["symbolic_memory_settings"] = factor.symbolic_memory_settings()
            record["symbolic_estimate_meaning"] = (
                "MUMPS INFOG(16)/(17): estimated factorization working memory maximum/sum over processes in decimal MB; MPI1; INFOG(17) plus independent conversion/workspace reserve"
            )
            record["reference_role"] = "REFERENCE_ONLY"
        estimate = (int(info["infog"]["17"]) + 1) * 1_000_000
        conversion_reserve = record["nnz"] * 32 + 128 * n + 256 * 2**20
        record.update(
            symbolic_seconds=perf_counter() - t,
            estimated_factor_bytes=estimate,
            conversion_and_workspace_reserve_bytes=conversion_reserve,
            rss_after_symbolic_bytes=rss_bytes(),
        )
        marker("reference_symbolic_capacity", record)
        if estimate <= 0 or rss_bytes() + estimate + conversion_reserve >= 12 * 2**30:
            raise RuntimeError("REFERENCE_RESOURCE_BLOCKED_AFTER_SYMBOLIC")
        factor.set_memory_limit_mb(
            int((12 * 2**30 - rss_bytes() - conversion_reserve) // 1_000_000)
        )
        if audit_options is not None:
            record["numeric_memory_limit_decimal_MB"] = factor.get_icntl(23)
            record["symbolic_estimate_source"] = (
                "https://www.mcs.anl.gov/petsc/petsc-3.10/src/mat/impls/aij/mpi/mumps/mumps.c.html"
            )
        check_budget("reference numeric")
        t = perf_counter()
        marker("reference_numeric_begin", {})
        factor.numeric(matrix)
        record.update(
            numeric_seconds=perf_counter() - t, numeric_info=factor.info((21, 22, 29))
        )
        marker("reference_numeric", record)
        check_budget("reference solve")
        b = matrix.createVecLeft()
        b.array[:] = (
            reduced.rhs if reduced is not None else np.r_[packet.a["g"], packet.a["gp"]]
        )
        x = matrix.createVecRight()
        t = perf_counter()
        marker("reference_solve_begin", {})
        factor.solve(b, x)
        residual = matrix.createVecLeft()
        matrix.mult(x, residual)
        residual.axpy(-1, b)
        relative = residual.norm() / b.norm()
        record.update(
            solve_seconds=perf_counter() - t,
            original_augmented_relative=relative,
            rss_with_numeric_factor_bytes=rss_bytes(),
        )
        if (relative > tolerance and final_ports is None) or not np.isfinite(x.array).all():
            raise RuntimeError(f"INDEPENDENT_REFERENCE_RESIDUAL_FAILED: {relative}")
        if reduced is None:
            c = x.array[: packet.size].copy()
            alpha = x.array[packet.size :].copy()
        else:
            c, alpha = reduced.recover(x.array)
            record.update(
                exact_static_condensation=True,
                recovered_independent_complex_FE=packet.size,
                condensed_rows=n,
                local_interior_factors="exact reference-only; no training use",
            )
        if final_ports is not None:
            audit_options["save_raw_recovery"](c,alpha,record)
            raw_alpha = alpha.copy()
            alpha, recovery_record = final_ports(c,raw_alpha)
            record["accurate_final_port_recovery"] = recovery_record
            record["raw_LU_vs_accurate_port_relative"] = float(
                np.linalg.norm(alpha-raw_alpha)/max(np.linalg.norm(raw_alpha),1e-12))
            metrics = ("native_relative","augmented_relative","original_total_augmented_relative")
            current = max(actual_audit(c,alpha)[k] for k in metrics)
            improvements = [dict(iteration=0,full_true_relative=current,accepted=True)]
            for iteration in range(1,4):
                if current<=tolerance:
                    break
                check_budget("same held factor full-residual correction")
                body = packet.a["g"]-packet.volume(c)-packet.B(alpha)
                port = packet.a["gp"]+packet.D(c)-packet.a["H"]*alpha
                rhs,ui = reduced.correction_rhs(body,port)
                b.array[:] = rhs
                factor.solve(b,x)
                dc,_ = reduced.recover_correction(x.array,ui)
                trial = c+dc
                trial_alpha,work = final_ports(trial,raw_alpha)
                value = max(actual_audit(trial,trial_alpha)[k] for k in metrics)
                accepted = np.isfinite(value) and value<current
                improvements.append(dict(iteration=iteration,full_true_relative=value,accepted=bool(accepted)))
                marker("held_factor_true_residual_correction",improvements[-1])
                if not accepted:
                    # Persist the last accepted vector again; a rejected trial
                    # must not become the published recovery checkpoint.
                    alpha,recovery_record = final_ports(c,raw_alpha)
                    break
                c,alpha,current = trial,trial_alpha,value
                recovery_record = work
            record["same_factor_full_residual_corrections"] = improvements
            record["accurate_final_port_recovery"] = recovery_record
        if (audit_options or {}).get('save_unqualified_recovery',False):
            # Preserve a real recovered state even when a later strict gate
            # fails; this is explicitly unqualified until all audits finish.
            audit_options['save_packet'](c,alpha,record)
            record['unqualified_recovery_saved_before_checks']=True
        recovered = (audit_options["independent_port_recovery"](c)
                     if final_ports is not None else packet.alpha(c))
        record["original_port_recovery_relative"] = float(
            np.linalg.norm(recovered - alpha) / max(np.linalg.norm(alpha), 1e-12)
        )
        if record["original_port_recovery_relative"] > 1e-10:
            raise RuntimeError("REFERENCE_PORT_RECOVERY_FAILED")
        record["original_full_equation_audit"] = actual_audit(c,alpha)
        if reduced is not None:
            record["condensed_augmented_relative"] = record[
                "original_augmented_relative"
            ]
            record["original_augmented_relative"] = record[
                "original_full_equation_audit"
            ]["augmented_relative"]
        if (
            max(
                record["original_full_equation_audit"][k]
                for k in (
                    "native_relative",
                    "augmented_relative",
                    "original_total_augmented_relative",
                )
            )
            > tolerance
        ):
            raise RuntimeError("REFERENCE_NATIVE_RESIDUAL_FAILED")
        if audit_options is None:
            np.savez(artifact / "reference_state.npz", c=c, alpha=alpha)
        else:
            audit_options["save_packet"](c, alpha, record)
            record["minimal_recovery_packet_saved_before_factor_release"] = True
    finally:
        record["rss_before_release_bytes"] = rss_bytes()
        if factor is not None:
            factor.destroy()
        for obj in (b, x, residual, matrix):
            if obj is not None:
                obj.destroy()
        del factor, b, x, residual, matrix
        gc.collect()
        ctypes.CDLL(None).malloc_trim(0)
        record.update(
            rss_after_release_bytes=rss_bytes(),
            factor_released=True,
            matrix_released=True,
            total_reference_setup_solve_seconds=perf_counter() - start,
        )
        marker("reference_release_before_postprocessing", record)
    if record["rss_after_release_bytes"] >= record["rss_before_release_bytes"]:
        raise RuntimeError("REFERENCE_RELEASE_RSS_NOT_CONFIRMED")
    return c, record


def field_physics(
    model, packet, reference, states, artifact, marker, *, diagnostic_only=False
):
    import ufl
    from dolfinx import fem
    from src.common.modes_3d import incident_power_3d
    from src.postprocessing.rta_3d import compute_volume_absorption_3d
    from src.solvers.dtn_port_3d import (
        _port_power_metrics,
        _mode_power_at_boundary,
        _mode_boundary_phase,
        _mode_carries_outward_power,
        _outgoing_projection,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field
    from src.solvers.learned_coarse_inverse import native_numpy_apply

    cfg, data, floquet = model["cfg"], model["data"], model["floquet"]
    modes = model["bundle"]["modes"]
    inc = model["bundle"]["incident_projections"]
    native = native_numpy_apply(model["bundle"])
    dx = ufl.Measure("dx", domain=data.mesh, metadata={"quadrature_degree": 15})
    incident_scale = np.sqrt(
        np.prod([b - a for a, b in json_design_bounds(packet, model)])
    )

    def field(c):
        return restore_p0_full_field(floquet, packet.storage(c))

    def norms(E):
        forms = [
            ufl.inner(E, E) * dx,
            ufl.inner(ufl.curl(E), ufl.curl(E)) / cfg.k0**2 * dx,
        ]
        return np.asarray(
            [np.sqrt(max(0, fem.assemble_scalar(fem.form(f)).real)) for f in forms]
        )

    ref_total, ref_scat = field(packet.a["background"] + reference), field(reference)
    ref_norms, ref_scat_norms = norms(ref_total), norms(ref_scat)
    # Predeclared representative cell centers: substrate, air, block, notch, top.
    points = np.array(
        [
            [-4.375, -3.125, -0.625],
            [-4.375, -3.125, 0.625],
            [-1.875, -0.625, 3.125],
            [0.625, -0.625, 3.125],
            [1.875, 3.125, 6.875],
            [-0.625, -1.875, 8.125],
        ]
    )
    cells = np.argmin(
        np.linalg.norm(model["centers"][:, None, :] - points[None, :, :], axis=2),
        axis=0,
    ).astype(np.int32)
    if np.max(np.linalg.norm(model["centers"][cells] - points, axis=1)) > 1e-12:
        raise ValueError("selected complex E/H must be predeclared cell centers")

    def samples(E):
        H = fem.Expression(
            ufl.curl(E) / (1j * cfg.k0 * cfg.mu_r), np.array([[0.5, 0.5, 0.5]])
        )
        return E.eval(points, cells), np.asarray(H.eval(data.mesh, cells)).reshape(
            len(cells), 3
        )

    refE, refH = samples(ref_total)
    refSE, refSH = samples(ref_scat)
    records = {}

    def error(diff, scale, natural):
        absolute = float(np.linalg.norm(diff))
        denominator = float(max(np.linalg.norm(scale), 1e-12 * natural))
        return dict(
            absolute=absolute, denominator=denominator, relative=absolute / denominator
        )

    for name, c in {"REFERENCE": reference, **states}.items():
        start = perf_counter()
        total = packet.a["background"] + c
        E, SE = field(total), field(c)
        alpha, sc_alpha = (
            packet.a["background_alpha"] + packet.alpha(c),
            packet.alpha(c),
        )
        port = _port_power_metrics(cfg, list(modes), alpha, list(inc))
        volume = compute_volume_absorption_3d(
            data,
            cfg,
            E,
            artifact / ("diagnostic_" + name.lower()),
            incident_power=incident_power_3d(cfg),
            port_metrics=port,
        )
        es, hs = samples(E)
        ses, shs = samples(SE)
        outgoing = np.asarray(
            [
                _outgoing_projection(z, i, mode.side)
                for mode, z, i in zip(modes, alpha, inc, strict=True)
            ],
            dtype=np.complex128,
        )
        boundary_outgoing = outgoing * np.asarray(
            [_mode_boundary_phase(mode, cfg) for mode in modes]
        )
        powers = np.asarray(
            [
                _mode_power_at_boundary(m, cfg, _outgoing_projection(z, i, m.side))
                / incident_power_3d(cfg)
                if _mode_carries_outward_power(m)
                else 0.0
                for m, z, i in zip(modes, alpha, inc, strict=True)
            ]
        )
        audit = packet.audit(c)
        audit["independent_DOLFINx_total_native_relative"] = float(
            np.linalg.norm(
                native(packet.storage(total))[packet.a["masters"]] - packet.a["total_g"]
            )
            / np.linalg.norm(packet.a["total_g"])
        )
        value = dict(
            audit=audit,
            port=port,
            volume=volume,
            points_nm=points,
            selected_total_E=es,
            selected_total_H_code=hs,
            selected_scattered_E=ses,
            selected_scattered_H_code=shs,
            ordered_complex_total_channels=alpha,
            ordered_complex_outgoing_channels=outgoing,
            ordered_complex_boundary_outgoing_channels=boundary_outgoing,
            total_channel_coefficient_meaning="original FE tangential projection including known incident field",
            outgoing_channel_coefficient_meaning="outgoing modal coefficient before boundary phase; known incident top projection subtracted",
            ordered_complex_scattered_channels=sc_alpha,
            ordered_per_channel_power=powers,
            total_L2_scaled_curl_norms=norms(E),
            scattered_L2_scaled_curl_norms=norms(SE),
            official_candidate_results=False,
            output_role="independent authority"
            if name == "REFERENCE"
            else "diagnostic until every Gate passes",
        )
        if name != "REFERENCE":
            differences = norms(field(c - reference))
            errors = {}
            for j, key in enumerate(("L2", "scaled_curl")):
                errors["total_" + key] = error(
                    differences[j], ref_norms[j], incident_scale
                )
                errors["scattered_" + key] = error(
                    differences[j], ref_scat_norms[j], incident_scale
                )
            for key, diff, scale in [
                ("selected_total_E", es - refE, refE),
                ("selected_total_H", hs - refH, refH),
                ("selected_scattered_E", ses - refSE, refSE),
                ("selected_scattered_H", shs - refSH, refSH),
            ]:
                errors[key] = error(diff, scale, 1)
                for point in range(len(points)):
                    errors[key + "_point_" + str(point)] = error(
                        diff[point], scale[point], 1
                    )
            value["field_errors"] = errors
        value["postprocess_seconds"] = perf_counter() - start
        records[name] = value
        marker(
            "physics_" + name,
            dict(native=audit["native_relative"], seconds=value["postprocess_seconds"]),
        )
    ref = records["REFERENCE"]
    reference_pass = (
        max(
            ref["audit"][k]
            for k in (
                "native_relative",
                "augmented_relative",
                "independent_DOLFINx_total_native_relative",
            )
        )
        <= 1e-10
    )
    reference_energy_closure = abs(
        ref["port"]["R_total"]
        + ref["port"]["T_total"]
        + ref["volume"]["A_volume_total"]
        - 1
    )
    reference_absorption_gap = abs(
        ref["port"]["A_balance"] - ref["volume"]["A_volume_total"]
    )
    reference_pass = bool(
        reference_pass
        and max(reference_energy_closure, reference_absorption_gap) <= 1e-5
    )
    comparisons = {}
    for name in states:
        record = records[name]
        errors = dict(record["field_errors"])
        errors["ordered_total_channels"] = error(
            record["ordered_complex_total_channels"]
            - ref["ordered_complex_total_channels"],
            ref["ordered_complex_total_channels"],
            1,
        )
        errors["ordered_outgoing_channels"] = error(
            record["ordered_complex_outgoing_channels"]
            - ref["ordered_complex_outgoing_channels"],
            ref["ordered_complex_outgoing_channels"],
            1,
        )
        errors["ordered_boundary_outgoing_channels"] = error(
            record["ordered_complex_boundary_outgoing_channels"]
            - ref["ordered_complex_boundary_outgoing_channels"],
            ref["ordered_complex_boundary_outgoing_channels"],
            1,
        )
        errors["ordered_scattered_channels"] = error(
            record["ordered_complex_scattered_channels"]
            - ref["ordered_complex_scattered_channels"],
            ref["ordered_complex_scattered_channels"],
            1,
        )
        deltas = {
            k: abs(record["port"][k] - ref["port"][k])
            for k in ("R_total", "T_total", "A_balance")
        }
        deltas["A_volume"] = abs(
            record["volume"]["A_volume_total"] - ref["volume"]["A_volume_total"]
        )
        closure = abs(
            record["port"]["R_total"]
            + record["port"]["T_total"]
            + record["volume"]["A_volume_total"]
            - 1
        )
        absorption = abs(
            record["port"]["A_balance"] - record["volume"]["A_volume_total"]
        )
        power_error = float(
            np.max(
                abs(
                    record["ordered_per_channel_power"]
                    - ref["ordered_per_channel_power"]
                )
            )
        )
        passed = (
            reference_pass
            and record["audit"]["strict_pass"]
            and record["audit"]["independent_DOLFINx_total_native_relative"] <= 1e-6
        )
        passed &= all(e["relative"] <= 1e-4 for e in errors.values())
        passed &= (
            all(x <= 1e-5 for x in deltas.values())
            and max(closure, absorption) <= 1e-5
            and power_error <= 1e-6
        )
        numerical_equation_pass = bool(
            record["audit"]["strict_pass"]
            and record["audit"]["independent_DOLFINx_total_native_relative"] <= 1e-6
        )
        field_reconstruction_pass = bool(
            all(e["relative"] <= 1e-4 for e in errors.values())
        )
        power_check_pass = bool(
            all(x <= 1e-5 for x in deltas.values())
            and max(closure, absorption) <= 1e-5
            and power_error <= 1e-6
        )
        policy = candidate_policy(passed, reference_exposed=diagnostic_only)
        record["official_candidate_results"] = policy["official_candidate_results"]
        if diagnostic_only:
            record.update(
                reference_used_for_training=True,
                pde_only_solve=False,
                production_initialization_allowed=False,
                data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY",
                pde_only_solver_qualified=False,
                numerical_equation_pass=numerical_equation_pass,
                field_reconstruction_pass=field_reconstruction_pass,
                power_check_pass=power_check_pass,
            )
        comparisons[name] = dict(
            status=(
                "SUPERVISED_DISCRETE_RECONSTRUCTION_PASS"
                if passed
                else "SUPERVISED_DISCRETE_RECONSTRUCTION_NOT_QUALIFIED"
            )
            if diagnostic_only
            else ("FEINN_DISCRETE_PASS" if passed else "FEINN_OPTIMIZATION_NEGATIVE"),
            errors=errors,
            power_absolute_differences=deltas,
            max_channel_power_absolute=power_error,
            energy_closure_absolute=closure,
            absorption_balance_volume_absolute=absorption,
            equation_audit=record["audit"],
            qualified=policy["pde_only_solver_qualified"],
            numerical_reconstruction_pass=policy["numerical_reconstruction_pass"],
            numerical_equation_pass=numerical_equation_pass,
            field_reconstruction_pass=field_reconstruction_pass,
            power_check_pass=power_check_pass,
            pde_only_solver_qualified=policy["pde_only_solver_qualified"],
            official_candidate_results=policy["official_candidate_results"],
            reference_used_for_training=policy["reference_used_for_training"],
            pde_only_solve=policy["pde_only_solve"],
            production_initialization_allowed=policy[
                "production_initialization_allowed"
            ],
        )
    return dict(
        reference_pass=reference_pass,
        reference_energy_closure_absolute=reference_energy_closure,
        reference_absorption_balance_volume_absolute=reference_absorption_gap,
        reference_norms=ref_norms,
        reference_scattered_norms=ref_scat_norms,
        natural_E_scale=incident_scale,
        records=records,
        ordered_incident_projection=inc,
        ordered_boundary_phase=np.asarray(
            [_mode_boundary_phase(mode, cfg) for mode in modes]
        ),
        mode_manifest_sha256=model["record"]["mode_manifest_sha256"],
    ), comparisons


def json_design_bounds(packet, model):
    return [[axis.min(), axis.max()] for axis in model["axes"]]


def validate_candidates(design, index, frozen, artifact, marker):
    from src.solvers.feinn_fem import build_model
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )
    from src.runners.feinn_workflow import sha

    packet = load_native(index["files"]["native"]["path"])
    states = {}
    for name, item in frozen.items():
        entry = item["files"]["checkpoint"]
        if sha(entry["path"]) != entry["sha256"]:
            raise ValueError("candidate changed after freeze")
        with np.load(entry["path"], allow_pickle=False) as data:
            states[name] = np.array(data["c"])
        if states[name].shape != (packet.size,) or not np.isfinite(states[name]).all():
            raise ValueError("invalid frozen full candidate")
    marker(
        "all_candidates_frozen_before_reference",
        {
            name: dict(checkpoint=x["files"]["checkpoint"], source_sha=x["source_sha"])
            for name, x in frozen.items()
        },
    )
    model = build_model(design, marker=marker)
    try:
        if (
            model["record"]["mesh_coordinates_sha256"]
            != index["result"]["identity"]["mesh_coordinates_sha256"]
            or model["record"]["mode_manifest_sha256"]
            != index["result"]["identity"]["mode_manifest_sha256"]
        ):
            raise ValueError("independent reference physical identity mismatch")
        reference, authority = exact_solve(model, packet, artifact, marker)
        physics, comparisons = field_physics(
            model, packet, reference, states, artifact, marker
        )
        result = dict(
            status="INDEPENDENT_REFERENCE_PASS"
            if physics["reference_pass"]
            else "REFERENCE_FAILED",
            reference=authority,
            physics=physics,
            comparisons=comparisons,
            all_candidates_frozen_before_reference=True,
            reference_feedback=False,
            candidate_sources={r: x["source_sha"] for r, x in frozen.items()},
        )
        return result, dict(reference=artifact / "reference_state.npz")
    finally:
        destroy_same_mesh_physical_action(model["bundle"])


def compare_frozen_without_solve(
    design, native_index, scaled_index, reference_index, scale_index, artifact, marker
):
    """Rebuild only local postprocessing objects; load the frozen V1 p3 state."""
    from src.solvers.feinn_fem import build_model
    from src.solvers.feinn_scaling import read_frozen_scale
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )
    from src.runners.feinn_workflow import sha

    if reference_index["result"]["status"] != "INDEPENDENT_REFERENCE_PASS":
        raise ValueError("V1 same-p3 reference was not qualified")
    packet = load_native(native_index["files"]["native"]["path"])
    G = sparse.load_npz(native_index["files"]["gram"]["path"])
    scaling = read_frozen_scale(scale_index["files"]["scale"]["path"], G)
    frozen = scaled_index["files"]["checkpoint"]
    previous = reference_index["files"]["reference"]
    for entry in (frozen, previous):
        if sha(entry["path"]) != entry["sha256"]:
            raise ValueError("candidate or reference changed after freeze")
    with np.load(frozen["path"], allow_pickle=False) as item:
        y = np.array(item["parameters"]).reshape(2, packet.size)
        c = np.array(item["c"])
    actual_c = scaling.to_c(y[0] + 1j * y[1])
    if not np.array_equal(c, actual_c):
        raise ValueError("scaled checkpoint c is not D*y")
    with np.load(previous["path"], allow_pickle=False) as item:
        reference = np.array(item["c"])
        reference_alpha = np.array(item["alpha"])
    if reference.shape != c.shape or reference_alpha.shape != (packet.np,):
        raise ValueError("same-p3 reference shape mismatch")
    marker(
        "v2_candidate_and_v1_reference_frozen",
        dict(
            scaled_checkpoint=frozen,
            reference_state=previous,
            scaled_source=scaled_index["source_sha"],
            V1_reference_source=reference_index["source_sha"],
            no_reference_solve=True,
        ),
    )
    model = build_model(design, marker=marker)
    try:
        identity = native_index["result"]["identity"]
        if (
            model["record"]["mesh_coordinates_sha256"]
            != identity["mesh_coordinates_sha256"]
            or model["record"]["mode_manifest_sha256"]
            != identity["mode_manifest_sha256"]
        ):
            raise ValueError("compare-only physical identity mismatch")
        alpha_mismatch = np.linalg.norm(
            packet.alpha(reference) - reference_alpha
        ) / max(np.linalg.norm(reference_alpha), 1e-12)
        if alpha_mismatch > 1e-10:
            raise ValueError("V1 reference saved port state differs")
        physics, comparisons = field_physics(
            model,
            packet,
            reference,
            {"FREE-FE-DUAL-GRAM-DIAG": c},
            artifact,
            marker,
        )
        result = dict(
            status="COMPARE_ONLY_COMPLETE"
            if physics["reference_pass"]
            else "REFERENCE_REUSE_FAILED",
            physics=physics,
            comparisons=comparisons,
            reused_reference=previous,
            reused_reference_source_sha=reference_index["source_sha"],
            reference_port_recovery_relative=float(alpha_mismatch),
            candidate_checkpoint=frozen,
            candidate_source_sha=scaled_index["source_sha"],
            candidate_c_equals_Dy=True,
            global_Maxwell_CSR_created=False,
            MUMPS_symbolic_numeric_solve_count=0,
            reference_recomputed=False,
            reference_state_loaded_only_after_candidate_freeze=True,
        )
        return result, {}
    finally:
        destroy_same_mesh_physical_action(model["bundle"])


def _region_field_errors(model, packet, reference, candidate):
    """Cell-integrated scattered errors, with both sides of each material jump."""
    import ufl
    from dolfinx import fem
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field

    from src.solvers.neural_fe_action_packet import array_hash

    mesh = model["data"].mesh
    tags = np.asarray(model["tags"])
    if len(tags) != len(model["centers"]) or set(np.unique(tags)) != {1, 2, 3}:
        raise ValueError("REGION_TAG_IDENTITY_FAILED")
    mesh.topology.create_connectivity(2, 3)
    links = mesh.topology.connectivity(2, 3)
    touching = set()
    for facet in range(mesh.topology.index_map(2).size_local):
        cells = links.links(facet)
        if len(cells) == 2 and tags[cells[0]] != tags[cells[1]]:
            touching.update(int(c) for c in cells)
    if not touching:
        raise ValueError("INTERFACE_NEAR_REGION_EMPTY")
    near = np.array(sorted(touching), dtype=np.int32)
    regions = dict(
        air=np.flatnonzero(tags == 1),
        substrate=np.flatnonzero(tags == 2),
        grating=np.flatnonzero(tags == 3),
        interface_near=near,
    )
    dg0 = fem.functionspace(mesh, ("DG", 0))
    ref = restore_p0_full_field(model["floquet"], packet.storage(reference))
    diff = restore_p0_full_field(
        model["floquet"], packet.storage(candidate - reference)
    )
    dx = ufl.Measure("dx", domain=mesh, metadata={"quadrature_degree": 15})
    incident_scale = np.sqrt(
        np.prod([b - a for a, b in json_design_bounds(packet, model)])
    )
    result = {}
    for name, cells in regions.items():
        indicator = fem.Function(dg0)
        indicator.x.array[:] = 0
        for cell in cells:
            indicator.x.array[dg0.dofmap.cell_dofs(int(cell))[0]] = 1
        values = []
        for expression in (
            lambda E: ufl.inner(E, E),
            lambda E: ufl.inner(ufl.curl(E), ufl.curl(E)) / model["cfg"].k0 ** 2,
        ):
            numerator = fem.assemble_scalar(
                fem.form(indicator * expression(diff) * dx)
            ).real
            denominator = fem.assemble_scalar(
                fem.form(indicator * expression(ref) * dx)
            ).real
            absolute = float(np.sqrt(max(0, numerator)))
            scale = float(
                max(
                    np.sqrt(max(0, denominator)),
                    1e-12 * incident_scale * np.sqrt(len(cells) / len(tags)),
                )
            )
            values.append(
                dict(
                    absolute=absolute,
                    reference_denominator=scale,
                    relative=absolute / scale,
                )
            )
        result[name] = dict(
            cells=int(len(cells)),
            cell_ids=np.asarray(cells, dtype=np.int32).tolist(),
            cell_ids_sha256=array_hash(np.asarray(cells, dtype=np.int32)),
            scattered_L2=values[0],
            scattered_scaled_curl=values[1],
        )
    return result


def compare_reference_fit_without_solve(
    design,
    native_index,
    reference_index,
    fit_index,
    reconstruct_index,
    artifact,
    marker,
    *,
    route="FEINN-REFERENCE-FIT-G",
):
    """Independent FE postprocessing of frozen supervised-fit coefficients only."""
    from src.solvers.feinn_error_geometry import reference_label
    from src.solvers.feinn_fem import build_model
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )
    from src.runners.feinn_workflow import sha

    packet = load_native(native_index["files"]["native"]["path"])
    reference, label = reference_label(
        native_index, reference_index, packet, used_for_training=True
    )
    frozen = fit_index["files"]["checkpoint"]
    rec = reconstruct_index["files"]["reconstructed"]
    for entry in (frozen, rec):
        if sha(entry["path"]) != entry["sha256"]:
            raise ValueError("FROZEN_RECONSTRUCTION_IDENTITY_FAILED")
    with np.load(frozen["path"], allow_pickle=False) as item:
        c = np.array(item["c"])
        if (
            not bool(item["reference_used_for_training"])
            or bool(item["pde_only_solve"])
            or bool(item["production_initialization_allowed"])
        ):
            raise ValueError("SUPERVISED_LABEL_POLICY_FAILED")
    with np.load(rec["path"], allow_pickle=False) as item:
        actual = np.array(item["c_q15"])
        q30 = np.array(item["c_q30"])
    reconstruction_relative = float(
        np.linalg.norm(actual - c) / max(np.linalg.norm(c), 1e-12)
    )
    q30_relative = float(
        np.linalg.norm(q30 - actual) / max(np.linalg.norm(actual), 1e-12)
    )
    if reconstruction_relative > 1e-12:
        raise ValueError("PARAMETERS_TO_COMPLETE_FE_COEFFICIENTS_FAILED")
    G = sparse.load_npz(native_index["files"]["gram"]["path"])
    d_ref = float(np.vdot(reference, G @ reference).real)
    error = c - reference
    G_error = float(np.sqrt(np.vdot(error, G @ error).real / d_ref))
    model = build_model(design, marker=marker)
    try:
        identity = native_index["result"]["identity"]
        if (
            model["record"]["mesh_coordinates_sha256"]
            != identity["mesh_coordinates_sha256"]
            or model["record"]["cell_tags_sha256"] != identity["cell_tags_sha256"]
            or model["record"]["mode_manifest_sha256"]
            != identity["mode_manifest_sha256"]
        ):
            raise ValueError("FIT_COMPARE_PHYSICAL_IDENTITY_FAILED")
        physics, comparisons = field_physics(
            model,
            packet,
            reference,
            {route: c},
            artifact,
            marker,
            diagnostic_only=True,
        )
        region = _region_field_errors(model, packet, reference, c)
        comp = comparisons[route]
        e_l2 = comp["errors"]["scattered_L2"]["relative"]
        e_curl = comp["errors"]["scattered_scaled_curl"]["relative"]
        if q30_relative > 1e-8:
            snapshot_category = "QUADRATURE_DRIFT"
        elif max(G_error, e_l2, e_curl) <= 1e-3:
            snapshot_category = "REPRESENTATION_WITNESS_POSITIVE"
        elif max(G_error, e_l2, e_curl) <= 1e-2:
            snapshot_category = "PARTIAL_REPRESENTATION_WITNESS"
        else:
            snapshot_category = "REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED"
        retained_only = fit_index["result"]["status"] in (
            "INTERRUPTED_FIT_ADAM500_RETAINED_SNAPSHOT",
            "INTERRUPTED_REPLAY_RETAINED_BOUNDARY",
        )
        category = (
            "INTERRUPTED_FIT_NO_FINAL_STATE" if retained_only else snapshot_category
        )
        if (
            comp["numerical_reconstruction_pass"]
            and snapshot_category != "QUADRATURE_DRIFT"
        ):
            supervised_reconstruction = "SUPERVISED_DISCRETE_RECONSTRUCTION_PASS"
        else:
            supervised_reconstruction = "NOT_QUALIFIED"
        result = dict(
            status=(
                "RETAINED_BOUNDARY_COMPARE_ONLY_COMPLETE"
                if route.endswith("ADAM500-REPLAY")
                else "RETAINED_ADAM500_COMPARE_ONLY_COMPLETE"
            )
            if retained_only
            else "REFERENCE_EXPOSED_COMPARE_ONLY_COMPLETE",
            category=category,
            snapshot_threshold_category=snapshot_category,
            final_fit_parameters_retained=not retained_only,
            supervised_reconstruction=supervised_reconstruction,
            G_field_error=G_error,
            d_ref=d_ref,
            parameters_to_saved_c_relative=reconstruction_relative,
            q30_to_q15_relative=q30_relative,
            quadrature_status="PASS" if q30_relative <= 1e-8 else "QUADRATURE_DRIFT",
            region_field_errors=region,
            physics=physics,
            comparisons=comparisons,
            label_identity=label,
            fit_checkpoint=frozen,
            reconstruction=rec,
            fit_source_sha=fit_index["result"].get(
                "original_fit_source_sha", fit_index["source_sha"]
            ),
            snapshot_registration_source_sha=fit_index["source_sha"],
            MUMPS_symbolic_numeric_solve_count=0,
            reference_recomputed=False,
            global_Maxwell_factor_created=False,
            reference_used_for_training=True,
            pde_only_solve=False,
            production_initialization_allowed=False,
            pde_only_solver_qualified=False,
            official_candidate_results=False,
            data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY",
        )
        marker(
            "reference_fit_compare_only",
            dict(
                category=category,
                G_error=G_error,
                scattered_L2=e_l2,
                scattered_scaled_curl=e_curl,
            ),
        )
        return result, {}
    finally:
        destroy_same_mesh_physical_action(model["bundle"])


def compare_residual_readout_without_solve(
    design, native, reference, candidate, reconstructed, previous, artifact, marker
):
    """T2 only: labelled physics plus the fixed-space G projection identity."""
    from src.solvers.feinn_restricted_residual import POLICY, ROUTE
    from src.runners.feinn_workflow import sha

    result, files = compare_reference_fit_without_solve(
        design,
        native,
        reference,
        candidate,
        reconstructed,
        artifact,
        marker,
        route=ROUTE,
    )
    entries = [
        candidate["files"]["checkpoint"],
        previous["files"]["checkpoint"],
        reference["files"]["reference"],
    ]
    vectors = []
    for entry in entries:
        if sha(entry["path"]) != entry["sha256"]:
            raise ValueError("T2_FIELD_IDENTITY_FAILED")
        with np.load(entry["path"], allow_pickle=False) as data:
            vectors.append(np.array(data["c"]))
    cR, cG, cref = vectors
    G = sparse.load_npz(native["files"]["gram"]["path"])
    d = result["d_ref"]
    energies = [
        float(np.vdot(v, G @ v).real / d) for v in (cR - cref, cG - cref, cR - cG)
    ]
    NE, NC = np.square(result["physics"]["reference_scattered_norms"])
    curl_weight = (2 * np.pi) ** 2
    comp = result["comparisons"][ROUTE]
    eL = comp["errors"]["scattered_L2"]["relative"]
    eC = comp["errors"]["scattered_scaled_curl"]["relative"]
    expected = (NE * eL**2 + curl_weight * NC * eC**2) / (NE + curl_weight * NC)
    result.update(
        norm_identity=dict(
            reference_L2_energy=float(NE),
            reference_scaled_curl_energy=float(NC),
            ell_nm=5,
            k0_per_nm=2 * np.pi / 5,
            ell_k0=2 * np.pi,
            G_reference_energy_from_FE=float(NE + curl_weight * NC),
            G_reference_energy_from_CSR=d,
            E_G_squared_from_FE=float(expected),
            E_G_squared_from_CSR=energies[0],
            relative_reference_energy_defect=abs(NE + curl_weight * NC - d) / d,
            absolute_error_squared_defect=abs(expected - energies[0]),
        ),
        V5_G_pythagorean=dict(
            new_error_squared=energies[0],
            V5_error_squared=energies[1],
            distance_to_V5_squared=energies[2],
            normalized_absolute_defect=abs(energies[0] - energies[1] - energies[2]),
        ),
        G_action_columns=5,
        native_action_columns=0,
        native_adjoint_columns=0,
        full_native_audits=2,
        independent_DOLFINx_actions_within_audits=2,
        Gram_factor_count=0,
        Gsolve_count=0,
        Maxwell_factor_count=0,
        **POLICY,
    )
    result["physics"]["records"][ROUTE].update(POLICY)
    result["comparisons"][ROUTE].update(POLICY)
    return result, files


def p_check(design, index, reference_index, artifact, marker):
    qualified = [
        name
        for name, item in reference_index["result"]["comparisons"].items()
        if item["qualified"]
    ]
    if not qualified:
        return dict(
            status="DISCRETIZATION_NOT_QUALIFIED",
            p4_reference="not_run",
            reason="No p3 candidate passed same-discrete equations, fields and power",
            target_5nm="not_run",
            target_0p7nm="not_run",
        ), {}
    import basix.ufl
    import ufl
    from dolfinx import fem
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.feinn_fem import build_model, export_native
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
        restore_p0_full_field,
    )
    from src.runners.feinn_workflow import budget

    if budget()["remaining_seconds"] < 3600:
        return dict(
            status="DISCRETIZATION_NOT_QUALIFIED",
            p4_reference="not_run",
            reason="Remaining first-round wall budget below one bounded p4 stage",
        ), {}
    packet3 = load_native(index["files"]["native"]["path"])
    with np.load(
        reference_index["files"]["reference"]["path"], allow_pickle=False
    ) as data:
        c3 = np.array(data["c"])
    model = build_model(design, degree=4, marker=marker)
    try:
        packet4, identity4 = export_native(model, marker)
        c4, authority4 = exact_solve(model, packet4, artifact, marker)
        space3 = fem.functionspace(
            model["data"].mesh, basix.ufl.element("N1curl", "hexahedron", 3)
        )
        if not np.array_equal(
            np.asarray(space3.dofmap.list, dtype=np.int64), packet3.a["cell_dofs"]
        ):
            raise ValueError("same geometry p3/p4 transfer native numbering mismatch")
        floquet3 = build_double_floquet_mpc(space3, model["data"], model["cfg"])
        E3 = restore_p0_full_field(
            floquet3, packet3.storage(packet3.a["background"] + c3)
        )
        S3 = restore_p0_full_field(floquet3, packet3.storage(c3))
        liftedE = fem.Function(model["space"])
        liftedE.interpolate(E3)
        liftedS = fem.Function(model["space"])
        liftedS.interpolate(S3)
        E4 = restore_p0_full_field(
            model["floquet"], packet4.storage(packet4.a["background"] + c4)
        )
        S4 = restore_p0_full_field(model["floquet"], packet4.storage(c4))
        dx = ufl.Measure(
            "dx", domain=model["data"].mesh, metadata={"quadrature_degree": 15}
        )
        k0 = model["cfg"].k0

        def norms(E):
            return np.asarray(
                [
                    np.sqrt(max(0, fem.assemble_scalar(fem.form(f)).real))
                    for f in (
                        ufl.inner(E, E) * dx,
                        ufl.inner(ufl.curl(E), ufl.curl(E)) / k0**2 * dx,
                    )
                ]
            )

        errors = {}
        for kind, left, right in [("total", liftedE, E4), ("scattered", liftedS, S4)]:
            diff = norms(left - right)
            scale = norms(right)
            for j, key in enumerate(("L2", "scaled_curl")):
                denominator = float(max(scale[j], 1e-12 * np.sqrt(750)))
                errors[kind + "_" + key] = dict(
                    absolute=float(diff[j]),
                    denominator=denominator,
                    relative=float(diff[j] / denominator),
                )
        alpha3 = packet3.a["background_alpha"] + packet3.alpha(c3)
        alpha4 = packet4.a["background_alpha"] + packet4.alpha(c4)
        if (
            model["record"]["mode_manifest_sha256"]
            != index["result"]["identity"]["mode_manifest_sha256"]
        ):
            raise ValueError("p4 changed complete ordered channel inventory")
        from src.solvers.dtn_port_3d import _outgoing_projection, _mode_boundary_phase

        inc3 = np.asarray(
            [
                complex(item["real"], item["imag"])
                for item in reference_index["result"]["physics"][
                    "ordered_incident_projection"
                ]
            ]
        )
        inc4 = np.asarray(model["bundle"]["incident_projections"])
        if np.linalg.norm(inc3 - inc4) > 1e-10 * max(np.linalg.norm(inc3), 1e-12):
            raise ValueError("p4 changed the physical incident channel projection")
        out3 = np.asarray(
            [
                _outgoing_projection(z, i, mode.side)
                for mode, z, i in zip(
                    model["bundle"]["modes"], alpha3, inc3, strict=True
                )
            ]
        )
        out4 = np.asarray(
            [
                _outgoing_projection(z, i, mode.side)
                for mode, z, i in zip(
                    model["bundle"]["modes"], alpha4, inc4, strict=True
                )
            ]
        )
        for name, left, right in [
            (
                "boundary_outgoing_channels",
                out3
                * np.asarray(
                    [
                        _mode_boundary_phase(m, model["cfg"])
                        for m in model["bundle"]["modes"]
                    ]
                ),
                out4
                * np.asarray(
                    [
                        _mode_boundary_phase(m, model["cfg"])
                        for m in model["bundle"]["modes"]
                    ]
                ),
            ),
            ("outgoing_channels", out3, out4),
            ("total_channels", alpha3, alpha4),
            ("scattered_channels", packet3.alpha(c3), packet4.alpha(c4)),
        ]:
            denominator = float(max(np.linalg.norm(right), 1e-12))
            absolute = float(np.linalg.norm(left - right))
            errors[name] = dict(
                absolute=absolute,
                denominator=denominator,
                relative=absolute / denominator,
            )
        points = np.array(
            [
                [-4.375, -3.125, -0.625],
                [-4.375, -3.125, 0.625],
                [-1.875, -0.625, 3.125],
                [0.625, -0.625, 3.125],
                [1.875, 3.125, 6.875],
                [-0.625, -1.875, 8.125],
            ]
        )
        cells = np.argmin(
            np.linalg.norm(model["centers"][:, None, :] - points[None, :, :], axis=2),
            axis=0,
        ).astype(np.int32)

        def samples(E):
            H = fem.Expression(ufl.curl(E) / (1j * k0), np.array([[0.5, 0.5, 0.5]]))
            return E.eval(points, cells), np.asarray(
                H.eval(model["data"].mesh, cells)
            ).reshape(-1, 3)

        for kind, left, right in [("total", liftedE, E4), ("scattered", liftedS, S4)]:
            for key, left_sample, right_sample in zip(
                ("selected_E", "selected_H"), samples(left), samples(right), strict=True
            ):
                absolute = float(np.linalg.norm(left_sample - right_sample))
                denominator = float(max(np.linalg.norm(right_sample), 1e-12))
                errors[kind + "_" + key] = dict(
                    absolute=absolute,
                    denominator=denominator,
                    relative=absolute / denominator,
                )
                for point in range(len(points)):
                    point_absolute = float(
                        np.linalg.norm(left_sample[point] - right_sample[point])
                    )
                    point_denominator = float(
                        max(np.linalg.norm(right_sample[point]), 1e-12)
                    )
                    errors[kind + "_" + key + "_point_" + str(point)] = dict(
                        absolute=point_absolute,
                        denominator=point_denominator,
                        relative=point_absolute / point_denominator,
                    )
        passed = all(v["relative"] <= 1e-3 for v in errors.values())
        np.savez(artifact / "p4_reference.npz", c=c4, alpha=alpha4)
        return dict(
            status="P4_CHECK_PASS_LIMITED_DISCRETE"
            if passed
            else "DISCRETIZATION_NOT_QUALIFIED",
            p4_reference="measured",
            qualified_p3_candidates=qualified,
            identity=identity4,
            reference=authority4,
            errors=errors,
            continuum_convergence_claim=False,
            target_5nm="not_run",
            target_0p7nm="not_run",
        ), dict(reference=artifact / "p4_reference.npz")
    finally:
        destroy_same_mesh_physical_action(model["bundle"])
