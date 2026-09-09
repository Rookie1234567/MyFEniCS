"""Single frozen air-cell tensor diagnostic under the existing parent runner."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np


from src.solvers.physical_bubble_local import trace_checks as _trace_checks


def run_bubble_local_tensor(cfg,comm,binding_path,directory,*,sample,marker):
    from basix.ufl import element
    from dolfinx import fem,default_real_type
    from .physical_diagnosis_worker import save_packet
    from src.geometry.mesh_builder_3d import _stage4_axis_plan,_structured_hexa_mesh,_mark_cells
    from src.solvers.fullspace_same_mesh_hcurl_pmg import _n1e,_dof_transform
    from src.solvers.fullspace_v17_p3_oracle import compile_physical_diagnostic_volume
    from src.solvers.hcurl_assembly_time_condensation import _cell_integral_kernels,_tabulate_raw_tensor_class
    from src.solvers.hcurl_affine_isotropic_tensor import AffineIsotropicMaxwellTensorSpec,AffineIsotropicMaxwellTensorFactory
    from src.solvers.fullspace_same_mesh_hcurl_pmg_p6 import _apply_standard_row_transform,_apply_transpose_right_transform
    from src.solvers.physical_bubble_local import harmonic_bubble_check
    import basix
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    save=lambda name,facts:save_packet(directory,name,facts)
    binding=json.loads(Path(binding_path).read_text())
    authority=Path(binding['quadrature_record']['path'])
    if hashlib.sha256(authority.read_bytes()).hexdigest()!=binding['quadrature_record']['sha256']:
        raise ValueError('frozen fine quadrature authority hash differs')
    audit=json.loads(authority.read_text())['metrics'][0]['audit']['quadrature']
    quadrature=tuple({k:audit[name][k] for k in ('quadrature_degree','quadrature_rule')} for name in ('curl','mass'))
    if any(q!=binding['quadrature'][i] for i,q in enumerate(quadrature)):
        raise ValueError('frozen quadrature metadata differs')
    sample();plan=_stage4_axis_plan(cfg,comm.size)
    msh=_structured_hexa_mesh(comm,plan.x_values,plan.y_values,plan.z_values,
        preserve_input_partition=cfg.stage4_preserve_structured_input_partition)
    tags=_mark_cells(msh,cfg);candidates=[]
    for cell in tags.find(cfg.tags.air):
        xyz=np.asarray(msh.geometry.x[msh.geometry.dofmap[cell]],float)
        lower,upper=xyz.min(axis=0),xyz.max(axis=0);widths=upper-lower
        key=tuple(float(x) for x in np.concatenate([lower,upper]))
        candidates.append(dict(cell=int(cell),key=key,widths=widths,volume=float(np.prod(widths)),
            preferred=bool(np.allclose(widths,10.,rtol=0,atol=1e-12))))
    if not candidates:raise ValueError('no original air cell')
    preferred=[x for x in candidates if x['preferred']]
    chosen=min(preferred,key=lambda x:x['key']) if preferred else min(candidates,key=lambda x:(-x['volume'],x['key']))
    cell=chosen['cell'];xyz=np.asarray(msh.geometry.x[msh.geometry.dofmap[cell]],float)
    msh.topology.create_entities(1);msh.topology.create_entities(2);msh.topology.create_entity_permutations()
    cell_info=int(msh.topology.get_cell_permutation_info()[cell])
    save('bubble_cell_frozen',dict(selection_rule=binding['selection_rule'],selected=chosen,
        source=json.loads((directory.parent/'run_manifest.json').read_text())['source'],
        material_tag=int(cfg.tags.air),eps_r=complex(cfg.eps_r),mu_r=complex(cfg.mu_r),
        config=cfg.as_jsonable(),binding=binding,coordinates=xyz,cell_info=cell_info,
        candidate_count=len(candidates),frozen_before_tensor_or_rank=True))
    marker('bubble_cell_frozen',dict(key=chosen['key'],cell_info=cell_info))
    J=np.column_stack([xyz[1]-xyz[0],xyz[2]-xyz[0],xyz[4]-xyz[0]])
    if not np.allclose(J,np.diag(chosen['widths']),rtol=0,atol=1e-12):
        raise ValueError('selected cell is not positive axis-aligned reference mapping')
    sample();e4,e2=_n1e(4),_n1e(2)
    if e4.dim!=300 or e2.dim!=54 or len(e4.entity_dofs[3][0])!=108 or len(e2.entity_dofs[3][0])!=6:
        raise ValueError('fixed Basix dimensions changed')
    tf,tc=_dof_transform(e4,cell_info),_dof_transform(e2,cell_info)
    orientation=max(np.linalg.norm(tf.T@tf-np.eye(300)),np.linalg.norm(tc.T@tc-np.eye(54)))
    if orientation>1e-12:raise ValueError('actual Legendre orientation is not orthogonal')
    P0=basix.compute_interpolation_operator(e2,e4).astype(complex)
    R0=basix.compute_interpolation_operator(e4,e2).astype(complex)
    P=tf@P0@tc.T;R=tc@R0@tf.T
    sample();space=fem.functionspace(msh,element('N1curl',msh.basix_cell(),4,dtype=default_real_type))
    actual=space.element.basix_element
    element_identity=dict(FFCx_hash=int(actual.hash()),PR_Gram_hash=int(e4.hash()),
        FFCx_dim=int(actual.dim),PR_Gram_dim=int(e4.dim),
        FFCx_map=actual.map_type.name,PR_Gram_map=e4.map_type.name,
        FFCx_variant=actual.lagrange_variant.name,PR_Gram_variant=e4.lagrange_variant.name)
    save('bubble_element_identity',element_identity)
    if actual.hash()!=e4.hash():raise ValueError('FFCx and PR/Gram Basix element identities differ')
    setup=dict(mesh=msh,mesh_data=SimpleNamespace(mesh=msh,cell_tags=tags),spaces={4:space})
    compiled=compile_physical_diagnostic_volume(setup,cfg,4,volume_quadrature_metadata=quadrature)
    raw=_tabulate_raw_tensor_class(compiled,_cell_integral_kernels(compiled),np.ascontiguousarray(xyz.ravel()),
        tag=int(cfg.tags.air),dimension=300)
    if quadrature[0]!=quadrature[1] or quadrature[0]['quadrature_rule']!='default':
        raise ValueError('factory requires same frozen default quadrature for both components')
    spec=AffineIsotropicMaxwellTensorSpec(curl_coefficient=1/complex(cfg.mu_r),
        mass_coefficient_by_tag={int(cfg.tags.air):-cfg.k0**2*complex(cfg.eps_r)},quadrature_degree=quadrature[0]['quadrature_degree'])
    factory=AffineIsotropicMaxwellTensorFactory(e4,spec)
    reference=factory.tensor(tag=int(cfg.tags.air),widths=tuple(chosen['widths']))
    tensor_error=float(np.linalg.norm(raw-reference)/max(np.linalg.norm(raw),np.finfo(float).tiny))
    save('bubble_tensor_identity',dict(FFCx_A=raw,reference_Gram_A=reference,relative_error=tensor_error,
        limit=1e-10,quadrature=quadrature,element_identity=element_identity,orientation_orthogonality=float(orientation),
        factory_retained_bytes=sum(x.nbytes for x in (*factory.mass_components,*factory.curl_components))))
    if not np.isfinite(tensor_error) or tensor_error>1e-10:raise ValueError('physical cell tensor bridge failed')
    A=raw.copy();workspace=np.empty(A.size,float)
    _apply_standard_row_transform(space.element,A,cell_info,workspace)
    _apply_transpose_right_transform(space.element,A,cell_info,workspace)
    oriented_error=float(np.linalg.norm(A-tf@raw@tf.T)/np.linalg.norm(A))
    if oriented_error>1e-12:raise ValueError('actual tensor orientation differs')
    result=harmonic_bubble_check(A,P,R,e4.entity_dofs[3][0],save=save,sample=sample)
    canonical_delta=tf.T@(result['W']-P);canonical_base=tf.T@P
    trace=_trace_checks(e4,canonical_delta,canonical_base,chosen['widths'])
    trace['boundary_dof_relative']=float(np.linalg.norm((result['W']-P)[:192])/np.linalg.norm(P))
    save('bubble_trace_orientation',dict(trace=trace,cell_info=cell_info,oriented_tensor_relative=oriented_error))
    if max(trace.values())>1e-12:raise ValueError('actual edge/face tangential trace changed')
    save('bubble_local_memory',dict(helper_array_payload=result['facts']['array_payload'],
        caller_named_arrays={name:int(value.nbytes) for name,value in dict(raw=raw,reference=reference,
            transform4=tf,transform2=tc,P_reference=P0,R_reference=R0,orientation_workspace=workspace,
            trace_delta=canonical_delta,trace_base=canonical_base).items()},
        factory_grams_bytes=sum(x.nbytes for x in (*factory.mass_components,*factory.curl_components)),
        resource_sample=sample(),scope='named arrays plus external parent RSS; hidden compiler/LAPACK scratch is only covered by external RSS'))
    save('bubble_local_summary',dict(status='LOCAL_TENSOR_PASS_NOT_GLOBAL_QUALIFICATION',selected=chosen,
        algebra=result['facts'],trace=trace,physical_tensor_relative=tensor_error,
        p4_global_matrix=0,p2_factor=0,H6=0,I4=0,outer=0,
        scope='one original air-cell tensor only; no new solver family enabled'))
    sample()
