"""Saved ambient coefficient defects partitioned by real macro entities.

This is a topology/array consumer, with no PDE action, matrix or factor.
Coefficient norms are diagnostics; they are not H(curl) error bounds.
"""
import numpy as np

NAMES=('macro_internal','x_face','y_face','z_face','macro_edge')


def entity_group(vertices,macro_axes):
    """Use exact physical support planes, never row IDs or amplitude cuts."""
    vertices=np.asarray(vertices)
    if vertices.ndim!=2 or vertices.shape[1]!=3 or len(vertices) not in (2,4):
        raise ValueError('edge/face vertex inventory')
    fixed=[a for a in range(3) if np.all(vertices[:,a]==vertices[0,a]) and
        np.any(np.asarray(macro_axes[a])==vertices[0,a])]
    if len(vertices)==2 and len(fixed)==2:return 4
    if len(fixed)==1:return 1+fixed[0]
    if not fixed:return 0
    raise ValueError('non-affine entity or ambiguous macro support')


def coefficient_partition(labels,slaves,residual,rhs,curl,mass):
    """Check exact coverage and recompute all complex group norms."""
    labels=np.asarray(labels);slaves=np.asarray(slaves,int)
    values=[np.asarray(v) for v in (residual,rhs,curl,mass)]
    if labels.ndim!=1 or any(v.shape!=labels.shape for v in values):raise ValueError('native partition shape')
    if len(np.unique(slaves))!=len(slaves) or np.any(slaves<0) or np.any(slaves>=len(labels)):raise ValueError('duplicate/bad slave inventory')
    mask=np.ones(len(labels),bool);mask[slaves]=False
    if np.any(labels[mask]<0) or np.any(labels[mask]>=len(NAMES)) or any(not np.all(np.isfinite(v)) for v in values):raise ValueError('missing/nonfinite native group')
    if any(np.any(v[slaves]!=0) for v in values):raise ValueError('canonical dual slave must be zero')
    norm=float(np.linalg.norm(values[0][mask]));den=float(np.linalg.norm(values[1][mask]));out={};squared=0.
    for i,name in enumerate(NAMES):
        rows=np.flatnonzero(mask&(labels==i));absolute=float(np.linalg.norm(values[0][rows]));squared+=absolute**2
        operation=float(np.linalg.norm(values[2][rows])+np.linalg.norm(values[3][rows]))
        out[name]=dict(rows=len(rows),absolute=absolute,original_ambient_rhs_relative=absolute/max(den,1e-30),
            curl_mass_operation=operation,operation_relative=absolute/max(operation,1e-30))
    identity=abs(squared-norm**2)/max(norm**2,1e-30)
    if identity>1e-12:raise ValueError('disjoint complex norm identity')
    return dict(groups=out,ambient_absolute=norm,ambient_rhs_norm=den,ambient_relative=norm/max(den,1e-30),
        norm_sum_identity=identity,slave_rows=len(slaves),canonical_independent_rows=int(mask.sum()),
        coefficient_diagnostic_not_physical_error_bound=True)


def saved_partitions(states,folder,journal,scope):
    from .phase_notch_hp import restore_record
    from .phase_notch_hp_fields import mesh_bounds
    from .scattering_anchor import save_arrays
    from .scattering_anchor_checks import checked_arrays
    from src.runners.task042_shared import write_json
    import basix
    with journal.measured('saved_ambient_entity_partition_topology_only'):
        parent=states['H2'];_,setup,_,field=restore_record(parent,journal,scope=scope)
        V=field.function_space;el=V.element.basix_element;bounds=mesh_bounds(V)
        # H2 is the frozen r2 refinement. Every second physical fine plane
        # is a macro plane; exact native coordinates and cell order persist.
        axes=[np.unique(bounds[:,:,a])[::2] for a in range(3)]
        labels=np.full(V.dofmap.index_map.size_local,-1,np.int8)
        mapping=checked_arrays(parent['trace_mapping']);slaves=mapping['slaves'].copy();internal=mapping['internal_rows'].copy()
        labels[internal]=0;del mapping
        ref=basix.cell.geometry(basix.CellType.hexahedron);top=basix.cell.topology(basix.CellType.hexahedron)
        for c,(lo,hi) in enumerate(bounds):
            rows=V.dofmap.cell_dofs(c)
            # Direct endpoint selection avoids roundoff from lo+(hi-lo).
            xyz=np.where(ref==0,lo,hi)
            for d in (1,2):
                for e,vertices in enumerate(top[d]):
                    ids=rows[el.entity_dofs[d][e]];group=entity_group(xyz[vertices],axes)
                    previous=labels[ids]
                    if np.any((previous!=-1)&(previous!=group)):raise ValueError('shared entity owner category mismatch')
                    labels[ids]=group
        master=np.ones(len(labels),bool);master[slaves]=False
        if np.any(labels[master]<0) or not np.array_equal(np.flatnonzero(master&(labels==0)),np.sort(internal)):
            raise ValueError('native entity/internal coverage mismatch')
        counts={name:int(np.count_nonzero(master&(labels==i))) for i,name in enumerate(NAMES)}
        expected=dict(macro_internal=696960,x_face=42240,y_face=42240,z_face=46464,macro_edge=6144)
        if counts!=expected:raise ValueError('actual canonical micro/macro entity inventory '+str(counts))
        inventory=save_arrays(folder/'ambient_entity_partition.npz',group=labels,slaves=slaves,
            macro_x=axes[0],macro_y=axes[1],macro_z=axes[2])
        del field,setup,V
    out={}
    for role in ('H2','FX','FXY'):
        if role not in states:continue
        r=states[role];receipt=r['independent']['ambient_original']['arrays'];a=checked_arrays(receipt)
        result=coefficient_partition(labels,slaves,a['residual'],a['rhs'],a['volume_curl'],a['volume_mass'])
        raw={'residual_'+name:a['residual'][np.flatnonzero(master&(labels==i))] for i,name in enumerate(NAMES)}
        packet=save_arrays(folder/(role+'_ambient_entity_defects.npz'),**raw)
        result.update(raw_complex=packet,parent_original=receipt,topology_inventory=inventory,
            omitted_z_face_and_macro_edge_reported_separately=True,new_actions=0,new_factors=0)
        out[role]=result;write_json(folder/(role+'_ambient_entity_defects.json'),result)
        del a,raw
    return dict(inventory=inventory,actual_counts=counts,states=out)
