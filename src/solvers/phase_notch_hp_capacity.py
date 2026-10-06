"""Storage-layout-based preallocation bound, followed by unchanged symbolic gate.

No fine matrix is constructed by this reader. Native cells, exact unrounded
class keys and every boundary-cell DoF enter the graph/support count.
"""
from collections import Counter
import hashlib
import numpy as np


def storage_envelope(*,rows,native,cells,dimension,interior,raw_classes,oriented_classes,
                     graph_nnz,boundary_support_sum,boundary_cells,modes,
                     planning_limit_bytes=16*2**30,sampled_stop_bytes=24*2**30,extra_workspace_bytes=0,row_cap=80000):
    if not isinstance(row_cap,int) or row_cap<=0:raise ValueError('explicit assembly row cap')
    trace=dimension-interior
    components={
        'raw_exact_tensor_cache':raw_classes*dimension**2*16,
        'oriented_original_schur_LU_recovery_rhs_trace':oriented_classes*16*(dimension**2+trace**2+interior**2+2*trace*interior),
        'shared_internal_identity_and_one_class_temporary_workspace':8*interior**2+6*dimension**2*16,
        'four_csr_and_scaled_graph_value_index_copies':4*(graph_nnz*24+(rows+1)*8),
        'boundary_pair_carriers_and_production_cache_upper':3*boundary_support_sum*(modes//2)*48,
        'interior_port_terms_XiB_and_python_contribution_maps':boundary_cells*interior*(modes//2)*(3*16+160),
        'mesh_MPC_trace_maps_preallocation_compiler_allocator_reserve':2*2**30,
        'declared_extra_evaluation_cache_and_workspace':int(extra_workspace_bytes),
    }
    total=sum(components.values())
    return dict(assembly_components_bytes=components,planned_simultaneous_bytes=int(total),
        assembly_graph_nnz_upper=int(graph_nnz),native=native,cells=cells,
        raw_classes=int(raw_classes),oriented_classes=int(oriented_classes),rows=rows,
        boundary_support_master_sum=int(boundary_support_sum),boundary_cell_count=int(boundary_cells),
        admitted=0<rows<=row_cap and total<=planning_limit_bytes,limit_bytes=planning_limit_bytes,assembly_row_cap=row_cap,
        status='ASSEMBLY_ONLY_PENDING_SYMBOLIC_NUMERIC_ADMISSION',
        numeric_rule=f'live whole-tree RSS + 2*max(INFOG16,17)*decimal MB + 2GiB reserve <={planning_limit_bytes}B',
        dense_bound_not_numeric_admission=True,floating_internal_port_entries_retained=True,
        sampled_stop_bytes=sampled_stop_bytes,
        uncertainty='engineering preallocation bound, followed by live symbolic gate and declared sampled tree stop')


def assembly_capacity(setup,cfg,journal,expected,*,planning_limit_bytes=16*2**30,sampled_stop_bytes=24*2**30,extra_workspace_bytes=0,row_cap=80000):
    from .hcurl_assembly_time_condensation import _canonical_axis_aligned_coordinates
    V=setup['spaces'][cfg.nedelec_degree];mesh=setup['mesh'];nc=mesh.topology.index_map(3).size_local
    dim=V.element.space_dimension;ip=np.asarray(V.element.basix_element.entity_dofs[3][0],int)
    tp=np.setdiff1d(np.arange(dim),ip);mpc=setup['floquets'][cfg.nedelec_degree].mpc
    n=V.dofmap.index_map.size_local;master=np.arange(n,dtype=np.int64)
    coefficients,offsets=mpc.coefficients()
    for s in mpc.slaves:
        if int(offsets[s+1]-offsets[s])!=1:raise ValueError('capacity requires actual single-master Floquet links')
        links=mpc.masters.links(int(s))
        if len(links)!=1 or not np.isfinite(coefficients[offsets[s]]):raise ValueError('capacity finite MPC')
        master[s]=links[0]
    if not np.array_equal(master[master],master):raise ValueError('capacity nested slave/master mapping')
    ni=nc*len(ip);nt=n-ni-len(mpc.slaves);nm=expected['complete_modes'];rows=nt+nm
    facts=dict(native=n,independent=n-len(mpc.slaves),trace=nt,internal=ni,cells=nc,rows=rows)
    for k in ('independent','trace','internal','cells','rows'):
        if k in expected and facts[k]!=expected[k]:raise ValueError('actual degree/three-axis topology differs: '+k)
    mesh.topology.create_entity_permutations();perms=mesh.topology.get_cell_permutation_info()
    tags=setup['mesh_data'].cell_tags.values;raw=set();oriented=set();cell_rows=[];incident={}
    for c in range(nc):
        _,widths=_canonical_axis_aligned_coordinates(mesh,c,tolerance=1e-11,geometry_identity_policy='raw_unrounded')
        key=(int(tags[c]),*widths);raw.add(key);oriented.add((*key,int(perms[c])))
        rr=np.unique(master[V.dofmap.cell_dofs(c)[tp]]);cell_rows.append(rr)
        for r in rr:incident.setdefault(int(r),[]).append(c)
    if len(incident)!=nt:raise ValueError('trace graph row completeness')
    multiplicity=Counter(tuple(cs) for cs in incident.values())
    graph=sum(count*len(np.unique(np.concatenate([cell_rows[c] for c in cs]))) for cs,count in multiplicity.items())
    mesh.topology.create_connectivity(2,3);links=mesh.topology.connectivity(2,3)
    boundary=[];full=[];traces=[]
    for tag in (cfg.tags.z_min,cfg.tags.z_max):
        group=sorted({int(c) for f in setup['mesh_data'].facet_tags.find(tag) for c in links.links(f)})
        boundary.extend(group);full.append(np.unique(np.concatenate([master[V.dofmap.cell_dofs(c)] for c in group])))
        traces.append(np.unique(np.concatenate([cell_rows[c] for c in group])))
    # Exact support-safe structural count; this includes all floating internal
    # functional terms and all Hhat entries, irrespective of their magnitude.
    graph+=(len(traces[0])+len(traces[1]))*nm+nm**2
    result=storage_envelope(rows=rows,native=n,cells=nc,dimension=dim,interior=len(ip),
        raw_classes=len(raw),oriented_classes=len(oriented),graph_nnz=graph,
        boundary_support_sum=sum(map(len,full)),boundary_cells=len(set(boundary)),modes=nm,
        planning_limit_bytes=planning_limit_bytes,sampled_stop_bytes=sampled_stop_bytes,extra_workspace_bytes=extra_workspace_bytes,row_cap=row_cap)
    result.update(facts,exact_unrounded_class_keys_sha256=hashlib.sha256(repr(sorted(oriented)).encode()).hexdigest(),
        class_identity='actual material tag + raw float64 widths + original DOF permutation; no approximate merges',
        boundary_master_support_sha256=[hashlib.sha256(x.tobytes()).hexdigest() for x in full],
        graph_count_method='cell-incidence row-support equivalence, same complete support as original PETSc preallocator',
        cell_schur_contribution_nnz_upper=nc*len(tp)**2)
    journal.event('three_axis_actual_graph_assembly_capacity',**result)
    return result
