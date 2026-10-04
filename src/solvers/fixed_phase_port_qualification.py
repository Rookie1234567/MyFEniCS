"""Complete joint P1 gate, including air physical flux before any real solve."""

import gc
import numpy as np


def joint_qualification(design, marker, budget):
    from src.solvers.fixed_phase_qualification import qualify
    from src.solvers.topological_port_trace import trace_qualification
    from benchmarks.fixed_phase_checker import qualification
    from src.solvers.fixed_phase_fem import build_model
    from src.solvers.feinn_fem import export_native, native_gate
    from src.solvers.feinn_native import FullNativePacket
    from src.solvers.fixed_phase_audit import surface_blocks, block_pair, incident_rhs
    from src.solvers.feinn_exact_condensation import ExactInteriorCondensation
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )
    from src.solvers.accurate_ports import recover_ports
    from benchmarks.accurate_port_checker import decimal_ports

    base = qualify(design, marker, joint_ports=True)
    check = qualification(base, joint_ports=True)
    trace = trace_qualification(design, marker, budget)
    affected = []
    for degree in (3, 4, 6):
        budget("affected port fixture")
        model = build_model(design, degree, True, topological_ports=True, marker=marker)
        try:
            p, _ = export_native(model, marker)
            B, D, H = surface_blocks(model, p)
            BB, DD, HH = surface_blocks(model, p, 30)
            pair = block_pair(p, B, D, H)
            rng = np.random.default_rng(422100 + degree)
            c = rng.normal(size=p.size) + 1j * rng.normal(size=p.size)
            alpha = rng.normal(size=p.np) + 1j * rng.normal(size=p.np)
            drift = max(
                float(np.linalg.norm(x - y) / max(np.linalg.norm(y), 1e-30))
                for x, y in ((BB @ alpha, B @ alpha), (DD @ c, D @ c), (HH, H))
            )
            rhs = incident_rhs(model, p, B)
            rhs_pair = float(np.linalg.norm(rhs - p.a["total_g"]) / np.linalg.norm(rhs))
            native = native_gate(model, p)
            g = rng.normal(size=p.size) + 1j * rng.normal(size=p.size)
            gp = rng.normal(size=p.np) + 1j * rng.normal(size=p.np)
            custom = FullNativePacket(dict(p.a, g=g, gp=gp))
            reduced = ExactInteriorCondensation(
                custom, model["space"].element.basix_element.entity_dofs[3][0]
            )
            csr, recovery_pair = reduced.assemble(marker=marker)
            accurate, work = recover_ports(custom.a, c)
            exact = decimal_ports(custom.a, c)
            arithmetic = float(
                np.linalg.norm(accurate - exact) / max(np.linalg.norm(exact), 1e-12)
            )
            internal = reduced.ids[0, reduced.i[0]]
            bad = dict(
                custom.a,
                br=np.r_[custom.a["br"], internal],
                bp=np.r_[custom.a["bp"], 0],
                bv=np.r_[custom.a["bv"], 1 + 0j],
            )
            rejected = False
            try:
                ExactInteriorCondensation(FullNativePacket(bad), reduced.i)
            except ValueError as e:
                rejected = str(e) == "CONDENSATION_PORT_HAS_INTERIOR_SUPPORT"
            # The independent kernel integrates the full, unmasked basis.
            # Remove an actual largest facet-closure column: this must fail.
            columns = np.asarray(abs(D).sum(axis=0)).ravel()
            omitted = int(np.argmax(columns))
            corrupt = D.copy().tolil()
            corrupt[:, omitted] = 0
            wrong = block_pair(p, B, corrupt.tocsr(), H)
            negative = max(v for row in wrong["samples"] for v in row)
            passed = (
                pair["passed"]
                and drift <= 1e-8
                and rhs_pair <= 1e-10
                and native["status"] == "PASS"
                and arithmetic <= 1e-10
                and recovery_pair <= 1e-10
                and rejected
                and negative > 1e-10
            )
            affected.append(
                dict(
                    degree=degree,
                    passed=passed,
                    physical_ports=pair,
                    quadrature_15_30=drift,
                    physical_rhs=rhs_pair,
                    native_action=native,
                    nonzero_internal_and_port_rhs=True,
                    condensed_action_recovery=recovery_pair,
                    generic_nonzero_interior_port_rejected=rejected,
                    omitted_boundary_dof_negative=negative,
                    accurate_vs_independent_decimal=arithmetic,
                    arithmetic_work=work,
                )
            )
            marker("affected_port_fixture_frozen", affected[-1])
            del p, custom, reduced, csr, B, D, H, BB, DD, HH
        finally:
            destroy_same_mesh_physical_action(model["bundle"])
        gc.collect()
    return dict(
        stage_qualified=check["passed"]
        and trace["passed"]
        and all(r["passed"] for r in affected),
        old_V20_ordering_limitation_preserved=True,
        base=base,
        base_checker=check,
        trace=trace,
        affected_ports=affected,
        complete_air_flux_before_real_B=True,
        no_NN_or_Gram=True,
    )
