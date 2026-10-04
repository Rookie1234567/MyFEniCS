"""One deterministic FE lifecycle, complete fields and release-before-physics."""

import gc
from time import perf_counter
import numpy as np

from benchmarks.fixed_phase_checker import solved
from src.solvers.fixed_phase_fem import build_model
from src.solvers.fixed_phase_audit import (
    PhysicalVolumeAudit,
    surface_blocks,
    block_pair,
    incident_rhs,
)
from src.solvers.feinn_exact_condensation import ExactInteriorCondensation, capacity
from src.solvers.feinn_discretization_audit import atomic_npz
from src.solvers.feinn_riesz import rss_bytes

ROLES = dict(
    O3=("G0", 3, False), E3=("G0", 3, True), E4=("G0", 4, True), O6=("GX560", 6, False)
)


def reference(design, role, artifact, marker, check_budget, *, accurate_ports=False,
              reuse_binding=None):
    from src.solvers.feinn_fem import export_native, native_gate
    from src.solvers.feinn_reference import exact_solve
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )
    from src.runners.fixed_phase_campaign import write

    mesh, degree, phase = ROLES[role]
    frozen = design["models"][mesh]
    old_packet = None
    if reuse_binding is not None:
        from src.runners.fixed_phase_campaign import sha
        from src.solvers.feinn_native import load_native
        for item in reuse_binding["files"].values():
            if sha(item["path"]) != item["sha256"]:
                raise ValueError("REUSED_BODY_FROZEN_HASH_CHANGED")
        old_packet = load_native(reuse_binding["files"]["native"]["path"])
    pre = capacity(int(np.prod(frozen["geometry"]["cells"])), degree,
                   classes=len(old_packet.a["F"]) if old_packet else 48, ports=340)
    marker("initial_derived_capacity", pre)
    if pre["allocation_upper_bytes"] + rss_bytes() >= 12 * 2**30:
        raise RuntimeError("REFERENCE_CAPACITY_REJECTED_BEFORE_ARRAYS")
    check_budget("build physical space")
    model = build_model(frozen, degree, phase, marker=marker,
                        topological_ports=accurate_ports,operators=reuse_binding is None)
    try:
        port_delta = None
        if old_packet is not None:
            from src.solvers.fixed_phase_port_recovery import rebuild_ports,verify_reused_model
            from src.solvers.feinn_native import packet_hashes
            verify_reused_model(model,reuse_binding)
            packet,port_delta = rebuild_ports(model,old_packet,marker)
            identity = dict(model["record"],packet_hashes=packet_hashes(packet),
                            reused_body=reuse_binding)
            native = dict(status="PASS",scope="hash-bound unchanged V20 F/MPC; independent new physical volume action follows",
                          reused_qualified_body=True)
            del old_packet
        else:
            packet,identity = export_native(model,marker)
            if accurate_ports:
                from src.solvers.accurate_ports import recover_ports
                from src.solvers.feinn_native import FullNativePacket,packet_hashes
                bg,_ = recover_ports(packet.a,packet.a["background"],gp=np.zeros_like(packet.a["gp"]))
                a = dict(packet.a,background_alpha=bg,
                         g=packet.a["total_g"]-packet.volume(packet.a["background"])-packet.B(bg))
                packet = FullNativePacket(a)
                identity["packet_hashes"] = packet_hashes(packet)
            native = native_gate(model,packet)
        expected = (
            3 * np.prod(frozen["geometry"]["cells"]) * degree**3
            + 2 * np.prod(frozen["geometry"]["cells"][:2]) * degree**2
        )
        if (
            packet.size != expected
            or packet.np != 340
            or not identity["nonseparable_y_z_witness"]
        ):
            raise ValueError("REAL_MODEL_IDENTITY_NOT_QUALIFIED")
        if native["status"] != "PASS":
            raise ValueError("NATIVE_FULL_SPACE_ACTION_NOT_QUALIFIED")
        independent = PhysicalVolumeAudit(model, packet)
        volume = independent.check()
        marker("independent_physical_volume", volume)
        B, D, H = surface_blocks(model, packet)
        port_pair = block_pair(packet, B, D, H)
        rhs = incident_rhs(model, packet, B)
        rhs_pair = float(
            np.linalg.norm(rhs - packet.a["total_g"]) / np.linalg.norm(rhs)
        )
        if not volume["passed"] or not port_pair["passed"] or rhs_pair > 1e-10:
            raise ValueError("INDEPENDENT_PHYSICAL_FORM_NOT_QUALIFIED")
        native_path = artifact / "native.npz"
        atomic_npz(native_path, **packet.a)
        write(artifact / "identity.json", identity)
        check_budget("exact condensation")
        start = perf_counter()
        reduced = ExactInteriorCondensation(
            packet, model["space"].element.basix_element.entity_dofs[3][0]
        )
        from src.solvers.fixed_phase_port_coordinates import BoundaryPortCondensation
        from src.solvers.dtn_port_3d import _mode_boundary_phase

        reduced = BoundaryPortCondensation(
            reduced,
            [
                _mode_boundary_phase(mode, model["cfg"])
                for mode in model["bundle"]["modes"]
            ],
            artifact,
        )
        condensation_setup = perf_counter() - start
        plan = capacity(packet.nc, degree, classes=len(packet.a["F"]), ports=340)

        def assemble(m, p, mark, current=reduced):
            return current.assemble(m, p, mark)

        state_path = artifact / "field_state.npz"

        def save(c, a, record):
            atomic_npz(
                state_path,
                c_scattered=c,
                c_total=c + packet.a["background"],
                alpha_scattered=a,
                alpha_total=a + packet.a["background_alpha"],
                background=packet.a["background"],
                background_alpha=packet.a["background_alpha"],
                masters=packet.a["masters"],
            )

        options = dict(reduced_system=reduced,assembler=assemble,
                       allocation_upper_bytes=plan["allocation_upper_bytes"],
                       check_budget=check_budget,save_packet=save,save_unqualified_recovery=True)
        if accurate_ports:
            from src.solvers.accurate_ports import recover_ports,actual_vector_audit
            from benchmarks.accurate_port_checker import decimal_ports

            def raw_save(c,a,record):
                atomic_npz(artifact/"raw_lu_recovery.npz",c_scattered=c,alpha_lu_raw=a,
                           alpha_old_backsub=packet.alpha(c))

            def final(c,raw):
                alpha,work = recover_ports(packet.a,c)
                atomic_npz(artifact/"port_recovery_vectors.npz",alpha_lu_raw=raw,
                           alpha_old_backsub=packet.alpha(c),alpha_recovered=alpha)
                return alpha,work
            options.update(residual_tolerance=1e-10 if role=="O6" else 1e-6,
                           save_raw_recovery=raw_save,final_port_recovery=final,
                           independent_port_recovery=lambda c:decimal_ports(packet.a,c),
                           full_equation_audit=lambda c,a:actual_vector_audit(packet,c,a))

        c, direct = exact_solve(
            model,
            packet,
            artifact,
            marker,
            audit_options=options,
        )
        del reduced, assemble
        gc.collect()
        alpha = (recover_ports(packet.a,c)[0] if accurate_ports else packet.alpha(c))
        audit = actual_vector_audit(packet,c,alpha) if accurate_ports else packet.audit(c)
        total = c + packet.a["background"]
        atotal = alpha + packet.a["background_alpha"]
        independent_r = np.r_[
            independent.volume(total) + B @ atotal - rhs, -D @ total + H * atotal
        ]
        weak = float(np.linalg.norm(independent_r) / np.linalg.norm(rhs))
        full = dict(
            **{
                k: audit[k]
                for k in (
                    "native_relative",
                    "augmented_relative",
                    "original_total_augmented_relative",
                )
            },
            independent_physical_weak=weak,
            recovery=direct["original_port_recovery_relative"],
            channels=packet.np,
            full_FE_recovered=True,
        )
        checker = solved(full, reference=role == "O6")
        from src.solvers.fixed_phase_comparison import self_physics

        physics = self_physics(model, packet, c, alpha, artifact, marker, check_budget)
        result = dict(
            stage_qualified=checker["passed"],
            role=role,
            identity=identity,
            full_equation=full,
            checker=checker,
            native_action=native,
            independent_volume=volume,
            independent_ports=port_pair,
            independent_rhs_relative=rhs_pair,
            deterministic_direct=direct,
            condensation_setup_seconds=condensation_setup,
            capacity=plan,
            physics=physics,
            global_Maxwell_factor=True,
            direct_coordinates="exact beta=boundary_phase*alpha; raw equations audited",
            reference_role="REFERENCE_ONLY"
            if role == "O6"
            else "RESEARCH_DETERMINISTIC_FE_CONTROL",
            no_neural_network=True,
            Gram_factor_count=0,
            explicit_role_contract=dict(residual_tolerance=1e-10 if role=="O6" else 1e-6,
                                        recovery_tolerance=1e-10),
            topological_port_rebuild=port_delta,
            accurate_final_ports=accurate_ports,
            field_meaning=dict(
                c_scattered="independent envelope FE coefficients, or ordinary FE when phase=false",
                c_total="c_scattered+saved background in this same discrete space",
                alpha_scattered="affine port recovery of scattered coefficients",
                alpha_total="alpha_scattered+background port projection",
            ),
        )
        return result, dict(
            native=native_path,
            field=state_path,
            identity=artifact / "identity.json",
            condensed_csr=artifact / "condensed_csr_recovery.npz",
            boundary_coordinate_csr=artifact / "boundary_coordinate_csr.npz",
            observables=artifact / "observables.npz",
        )
    finally:
        destroy_same_mesh_physical_action(model["bundle"])
