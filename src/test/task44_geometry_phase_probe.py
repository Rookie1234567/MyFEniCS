"""Owner-run actual mesh/mode/phase/codec prefix; no FE assembly or solve."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import sys


def run(directory):
    import numpy as np
    from src.io.sixlayer_input import resolve_sixlayer_input,build_sixlayer_config
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.geometry.sixlayer_mesh_audit import audit_sixlayer_mesh
    from src.common.modes_3d import outgoing_port_modes_3d
    from src.common.strict_json import atomic_json,snapshot
    from src.solvers.dtn_port_3d import (_mode_boundary_phase,_mode_projection_denominator,
        _mode_power_at_boundary,_incident_projection_onto_top_mode,_traction_vector)
    from src.runners.sixlayer_case import source_identity
    root=Path(__file__).resolve().parents[2]
    out=Path(directory);out.mkdir(parents=True,exist_ok=False)
    facts={'schema':'sixlayer-geometry-phase-prefix.v1','PDE_assembly':False,'solve':False,'status':'RUNNING','cases':{}}
    primary=None
    try:
        facts['source']=source_identity()
        # Exercise genuine NumPy producer families through the actual codec.
        producer={'passed':np.bool_(True),'counts':[np.int32(144),np.uint64(2**63+1)],
                  'relative':np.float64(1e-16),'phase':np.complex128(1+2j),'zero':None,
                  'nested':({'values':[np.float32(0),np.bool_(False)]},)}
        atomic_json(out/'codec_prefix.json',producer)
        for forbidden in (np.array(1),np.zeros(10),float('nan'),complex(1,float('inf'))):
            try:snapshot(forbidden)
            except (ValueError,TypeError):pass
            else:raise AssertionError('strict codec accepted unbounded array/nonfinite')
        for name in 'ABCD':
            _,resolved=resolve_sixlayer_input(root/'input/task44_sixlayer'/f'{name}.dat')
            cfg=build_sixlayer_config(resolved)
            mesh=build_airbox_mesh_3d(cfg,out/name)
            audit=audit_sixlayer_mesh(mesh,resolved['mesh_plan'])
            modes=outgoing_port_modes_3d(cfg)
            expected=4*(2*cfg.diffraction_order_max_m+1)*(2*cfg.diffraction_order_max_n+1)
            if len(modes)!=expected:raise RuntimeError('complete actual lattice')
            if len({(m.side,m.m,m.n,m.polarization) for m in modes})!=expected:raise RuntimeError('duplicate mode')
            if any(not np.isfinite(m.electric_tangential_norm_sq) or m.electric_tangential_norm_sq<=0 for m in modes):
                raise RuntimeError('degenerate/nonfinite tangential mode')
            global_cfg=replace(cfg,dtn_phase_gauge='global_z')
            errors=[];power_errors=[];incident_errors=[]
            # Same physical boundary field under coordinate change, not a PDE
            # accuracy claim. Restrict global representation to safe magnitude;
            # centered basis itself is checked for every retained mode.
            for mode in modes:
                if _mode_boundary_phase(mode,cfg)!=1 or _mode_projection_denominator(mode,cfg)<=0:
                    raise RuntimeError('boundary-plane basis')
                phase=_mode_boundary_phase(mode,global_cfg)
                if not 1e-12<abs(phase)<1e12:continue
                v=np.asarray([.3+.4j,-.2+.5j],dtype=np.complex128)
                traction=_traction_vector(mode,cfg)
                cp=-np.dot(traction[:2],v);cg=cp*phase
                ep=np.dot(mode.e_vector[:2],v)
                dp=-np.conj(ep)/_mode_projection_denominator(mode,cfg)
                dg=-np.conj(ep*phase)/_mode_projection_denominator(mode,global_cfg)
                ap=.2-.7j;ag=ap/phase;x=.4+.1j
                errors.extend([abs(cg*ag-cp*ap)/max(1,abs(cp*ap)),
                    abs((dg*x+ag)*phase-(dp*x+ap))/max(1,abs(dp*x+ap))])
                if mode.propagating:
                    pp=_mode_power_at_boundary(mode,cfg,ap);pg=_mode_power_at_boundary(mode,global_cfg,ag)
                    power_errors.append(abs(pp-pg)/max(1,abs(pp)))
                if mode.side=='top' and mode.m==mode.n==0:
                    ip=_incident_projection_onto_top_mode(mode,cfg)
                    ig=_incident_projection_onto_top_mode(mode,global_cfg)
                    incident_errors.append(abs(ig*phase-ip)/max(1,abs(ip)))
            measured={'basis_change_max_error':max(errors),'propagating_power_max_error':max(power_errors),
                      'incident_phase_once_max_error':max(incident_errors)}
            facts['cases'][name]={'actual_mesh':audit,'actual_modes':len(modes),
                                 'propagating_modes':sum(m.propagating for m in modes),'errors':measured}
            atomic_json(out/'result.json',facts)
            if any(not np.isfinite(x) or x>1e-12 for x in measured.values()):raise RuntimeError('phase-change oracle')
            del mesh,modes
        if source_identity()!=facts['source']:raise RuntimeError('source drift during prefix')
        facts['status']='ACTUAL_GEOMETRY_MODE_PHASE_CODEC_PREFIX_PASS_NOT_PDE'
    except BaseException as exc:primary=exc;facts.update(status='FAILED_NOT_PDE',error=repr(exc));raise
    finally:
        try:atomic_json(out/'result.json',facts)
        except BaseException as exc:
            if primary is not None:primary.add_note('prefix publication: '+repr(exc))
            else:raise
    return facts

if __name__=='__main__':run(sys.argv[1])
