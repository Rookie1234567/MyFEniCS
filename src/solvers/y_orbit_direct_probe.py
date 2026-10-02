"""X-only fresh direct two-cell calibration, under the existing supervisor.

Every original FE channel and physical alias stays. Fresh primary/literal,
complete original contribution and shared-owner gates finish before factors.
"""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import hashlib
import sys
import numpy as np
from scipy import sparse

SCHEMA='task40extra.y-orbit-direct-profile-probe.v1'


def run_direct_quotient_probe(input_path,*,direct_profile,event,save_array,allocation_gate,run_directory,stage):
 from mpi4py import MPI
 from petsc4py import PETSc
 from .task40extra_y_orbit_reference import pilot_config,collect_y_orbit_entities,FullOriginalAction,solve_notched_fgmres,SEED,LIMITS
 from .y_orbit_direct_profile import direct_profile_metadata,build_direct_profile_config
 from .y_orbit_direct_carrier_qualification import build_fresh_direct_carriers
 from .y_orbit_direct_operator_qualification import (audit_direct_original_cell_contributions,export_direct_volume_source)
 from .y_orbit_shared_transform_evidence import SharedTransformEvidence
 from .y_orbit_transform_bank import RunLocalTransformBank
 from .y_orbit_two_cell_inverse import StreamedFullYLayout,FourBranchFactors,CompleteTwoCellInverse
 from .y_orbit_two_cell_block_audit import TwoCellBranchCoordinates,TwoCellBlockProvider
 from .y_orbit_quotient_condensed import build_quotient_condensed
 from .y_orbit_condensed_adapter import trace_layout_coordinates
 from .y_orbit_centered_evidence import (original_packet,recovered_field_and_modes,require_output_packet,
     interior_only_rhs,fixture_interior_positions,save_mpc_inventory,save_centered_port_inventory,SOURCES)
 from .y_orbit_two_cell_inverse_probe import _original_augmented_packet,_check_original
 from .y_orbit_sparse_probe import _notch_supported_rhs
 from .y_orbit_sparse_reference import _gate,sparse_hash,csr_audit,sampled_right_pc_defect
 from .y_orbit_two_cell_audit import _save_csr
 from .fullspace_dtn_action import build_dynamic_mode_inventory,_jsonable
 from .dtn_boundary_plane_qualification import carrier_numeric_identity
 from .fullspace_same_mesh_hcurl_pmg_physical import _build_split_volume_action,build_physical_rhs
 from .fullspace_physical_action import FullspacePhysicalAction
 from src.geometry.mesh_builder_3d import _mark_cells,_rectangular_air_void_audit
 if direct_profile!='X' or stage not in ('prefactor','solve'):raise ValueError('only explicit directX prefactor/solve is enabled')
 metadata=direct_profile_metadata(direct_profile)
 base_cfg,_,input_sha=pilot_config(input_path,azimuth_deg=5.)
 cfg=build_direct_profile_config(base_cfg,direct_profile)
 bank=RunLocalTransformBank(mapping_limit=LIMITS['mapping'])
 descriptors={}
 root=Path(run_directory).resolve()
 def save(name,value):
  descriptor=save_array(name,value);descriptors[name]=descriptor;return descriptor
 def load(name):
  descriptor=descriptors[name];path=(root/descriptor['path']).resolve()
  if not path.is_relative_to(root):raise ValueError('direct current artifact path escapes run')
  _gate(allocation_gate,'direct_saved_witness_'+name,payload=descriptor['payload_bytes'],workspace=1<<20)
  digest=hashlib.sha256()
  with path.open('rb') as stream:
   for chunk in iter(lambda:stream.read(1<<20),b''):digest.update(chunk)
  if digest.hexdigest()!=descriptor['file_sha256']:raise ValueError('direct current artifact file/source binding differs')
  value=np.load(path,allow_pickle=False,mmap_mode='r')
  if (list(value.shape)!=descriptor['shape'] or str(value.dtype)!=descriptor['dtype'] or value.nbytes!=descriptor['payload_bytes']
      or value.dtype.hasobject or value.flags.writeable):raise ValueError('saved direct witness shape/dtype/readonly differs')
  return value
 def load_csr(prefix,shape):
  matrix=sparse.csr_matrix((load(prefix+'_data'),load(prefix+'_indices'),load(prefix+'_indptr')),shape=shape,copy=False)
  csr_audit(matrix,petsc_index_dtype=PETSc.IntType);return matrix
 evidence=SharedTransformEvidence(bank,save_array=save,event=event,allocation_gate=allocation_gate,
                                  mapping_limit=LIMITS['mapping'],direct_profile=direct_profile)
 evidence.snapshot('before_collect')
 def entity_callback(role,entities,setup,assembly_cfg,axes,bundle):
  evidence.named.update(entities.named_backing_arrays(role));evidence.snapshot(role+'_after_collect')
  context=_jsonable(bundle['dtn_action'].carrier.assembly_context)
  evidence.compare_streamed(role,entities,space=setup['spaces'][4],floquet=setup['floquets'][4],axes=axes,
                            frozen_context=context,load_array=load)
  evidence.snapshot(role+'_layout_before_build' if role!='full' else 'full_after_streamed_control_release')
 fresh=None;factors=inverse=action0=action1=notched=None
 sectors=[];providers={};provider_records={};matrices={};blocks=[];report={}
 layout=original=coords=trace=condensed=provider=matrix=local=bundle=entities=sector=value=ids=array=None
 try:
  fresh=build_fresh_direct_carriers(cfg,direct_profile=direct_profile,run_directory=root,save_array=save,
      allocation_gate=allocation_gate,event=event,shared_template_bank=bank,
      entity_callback=entity_callback,layout_callback=evidence.add_layout)
  original=fresh.global_bundle;setup=original['setup'];full_entities=fresh.global_entities
  layout=StreamedFullYLayout(full_entities,cfg,direct_profile=direct_profile)
  evidence.named['full.cell_dft']=layout.cell_dft
  save('independent_storage_rows',layout.independent);save_mpc_inventory(original,layout,save)
  interior=fixture_interior_positions(setup['spaces'][4],layout,direct_profile=direct_profile)
  save('actual_interior_positions',interior)
  save_centered_port_inventory(original,layout,save,allocation_gate=allocation_gate)
  original_H=np.asarray([entry.normalization_h for entry in original['dtn_action'].carrier.entries])
  inventory=fresh.global_mode_inventory
  if any(mode is not inventory[0][i] for i,mode in enumerate(original['modes'])):raise ValueError('actual fresh original mode identities differ')
  save('port_original_H',original_H)
  save('port_q_labels',np.asarray([int(mode.n)%metadata.ny for mode in inventory[0]],dtype=PETSc.IntType))
  save('port_factor_coordinate_scale',1/np.sqrt(original_H))
  for b in range(metadata.replication_count):
   local=fresh.local_bundles[b];context=local['quotient_context'];local_layout=fresh.local_layouts[b]
   condensed=build_quotient_condensed(local,global_mode_inventory=inventory,global_mode_indices=context.original_mode_indices,
       qbase=b,allocation_gate=allocation_gate,direct_profile=direct_profile)
   sector={'context':context,'setup':local['setup'],'bundle':local,'condensed':condensed,
           'layout':local_layout,'transport':fresh.transports[b]};sectors.append(sector)
   trace=trace_layout_coordinates(local_layout,condensed.system,allocation_gate=allocation_gate)
   coords=TwoCellBranchCoordinates(trace,condensed,context,global_original_H=original_H,
       allocation_gate=allocation_gate,index_dtype=PETSc.IntType,direct_profile=direct_profile)
   sector['coordinates']=coords;provider=TwoCellBlockProvider(condensed,coords,allocation_gate=allocation_gate)
   providers[b]=provider;provider_records[b]={}
   for p in (0,1):
    for q in (0,1):
     matrix=provider.block(p,q);prefix=f'direct_twist_{b}_block_{p}_{q}'
     _save_csr(save,prefix,matrix)
     item={'twist':b,'p':p,'q':q,'global_p':context.global_q_indices[p],'global_q':context.global_q_indices[q],
           'shape':list(matrix.shape),'nnz':int(matrix.nnz),'CSR_sha256':sparse_hash(matrix),'csr_prefix':prefix}
     provider_records[b][(p,q)]=item
     if p==q:
      actual_q=context.global_q_indices[q];matrices[actual_q]=matrix
      _save_csr(save,f'q_{actual_q}_S',matrix)
      blocks.append({'q':actual_q,'shape':list(matrix.shape),'nnz':int(matrix.nnz),'CSR_sha256':sparse_hash(matrix),
                    'csr_prefix':f'q_{actual_q}_S'})
      for part in ('data','indices','indptr'):evidence.named[f'q_{actual_q}_S.{part}']=getattr(matrix,part)
   for part in ('data','indices','indptr'):evidence.named[f'twist_{b}_Qt.{part}']=getattr(coords.qt,part)
   for name,array in trace.items():
    if isinstance(array,np.ndarray):evidence.named[f'twist_{b}_trace.{name}']=array
    elif sparse.issparse(array):
     for part in ('data','indices','indptr'):evidence.named[f'twist_{b}_trace.{name}.{part}']=getattr(array,part)
   for name,array in (('independent_storage_rows',condensed.independent_original_rows),
       ('trace_original_rows',condensed.trace_original_rows),('interior_original_rows',condensed.interior_original_rows),
       ('slave_storage_rows',np.asarray(local['setup']['floquets'][4].mpc.slaves))):
    save(f'twist_{b}_'+name,array)
    if name!='slave_storage_rows':evidence.named[f'twist_{b}_recovery.{name}']=array
   evidence.named[f'twist_{b}_ports.scale']=coords.scale
   for branch,ids in enumerate(coords.aliases):evidence.named[f'twist_{b}_ports.alias_{branch}']=ids
   save(f'twist_{b}_original_H',np.asarray([entry.normalization_h for entry in local['dtn_action'].carrier.entries]))
  blocks.sort(key=lambda item:item['q'])
  if [item['q'] for item in blocks]!=list(range(metadata.ny)):raise ValueError('every actualq must have a complete diagonalblock')
  operator=audit_direct_original_cell_contributions(original,{b:sector['condensed'] for b,sector in enumerate(sectors)},
      full_entities,{b:entities for b,entities in enumerate(fresh.local_entities)},fresh.transports,
      providers_by_twist=providers,provider_block_records_by_twist=provider_records,
      allocation_gate=allocation_gate,save_array=save,load_array=load,load_csr=load_csr,event=event,direct_profile=direct_profile)
  def same_live_carriers(boundary):
   actual={'global':carrier_numeric_identity(original['dtn_action'].carrier),
           'local':[carrier_numeric_identity(bundle['dtn_action'].carrier) for bundle in fresh.local_bundles]}
   expected={'global':fresh.qualification_receipt['global_carrier_identity_before'],
             'local':fresh.qualification_receipt['local_carrier_identities']}
   event('direct_same_live_carrier_identity',{'boundary':boundary,'actual':actual,'expected':expected,
                                           'unchanged':actual==expected})
   if actual!=expected:raise ValueError('same live original/sector carrier changed at '+boundary)
   return actual
  pre_factor_carriers=same_live_carriers('before_all_q_factors')
  bank.seal();evidence.snapshot('all_sectors_retained_before_factor');shared=evidence.result()
  event('shared_complete_equivalence_before_any_factor',shared)
  event('direct_complete_original_qualification_before_any_factor',{'operator_receipt':operator,
       'fresh_carrier_receipt':fresh.qualification_receipt,'input_blocks':blocks,'factor_count':0})
  report={'schema':SCHEMA,'direct_profile':direct_profile,'profile':_jsonable(metadata.identity()),
      'physical_config':_jsonable(cfg.as_jsonable()),'input_sha256':input_sha,'stage':stage,'prefactor_only':stage=='prefactor',
      'degree':4,'physical_mode_count':532,'physical_generator_manifest_sha256':inventory[2],
      'fresh_carrier_qualification':fresh.qualification_receipt,'original_operator_qualification':operator,
      'same_live_carrier_identity_before_factor':pre_factor_carriers,
      'shared_transforms':True,'shared_transform_equivalence':shared,'reformed_blocks':blocks,
      'direct_provider_blocks':[provider_records[b][(p,q)] for b in providers for p in (0,1) for q in (0,1)],
      'layout':layout.audit,'factor_count':0,'PDE_solved':False,'official_results':False,
      'scope_flags':{'full_layout_entity_stream':True,'fresh_global_and_local_carriers':True,'snapshots_reused':False,
          'candidate_full_Ny_CSR_created':False,'candidate_full_F_created':False,'candidate_full_Q_created':False,
          'candidate_global_FE_square_matrix_created':False,'performance_or_target_capacity_claim':False}}
  if stage=='prefactor':return {**report,'status':'QUOTIENT_PREFACTOR_COMPARE_PASS',
      'same_live_carrier_identity_at_exit':same_live_carriers('before_successful_exit')}
  factors=FourBranchFactors(matrices,allocation_gate=allocation_gate,event=event,save_array=save,direct_profile=direct_profile)
  inverse=CompleteTwoCellInverse(sectors,layout,factors,allocation_gate=allocation_gate,direct_profile=direct_profile)
  action0=FullOriginalAction(original['physical_action'],layout)
  manufactured=[]
  for q in range(metadata.ny):
   modal=np.zeros(metadata.independent_rows,complex);j=np.arange(metadata.rows_per_q)
   modal[q*metadata.rows_per_q:(q+1)*metadata.rows_per_q]=np.cos(.31*j)+1j*np.sin(.47*j)
   f=full_entities.transform(layout._dft(modal,adjoint=False),direction='dual_from_canonical')
   g=np.zeros(532,complex);ids=np.flatnonzero(np.asarray([int(mode.n)%metadata.ny for mode in inventory[0]])==q)
   j=np.arange(len(ids));g[ids]=np.sqrt(original_H[ids])*(np.cos(.17*j)+1j*np.sin(.43*j))
   x,alpha=inverse.apply_augmented(f,g);label=f'aug_q_{q}'
   for name,array in (('FE_rhs',f),('port_rhs',g),('solution',x)):save(label+'_'+name,array)
   manufactured.append({'q':q,**_original_augmented_packet(original,layout,f,g,x,alpha,label=label,save=save,event=event)})
  rng=np.random.default_rng(SEED);generic=rng.standard_normal(metadata.independent_rows)+1j*rng.standard_normal(metadata.independent_rows)
  if np.min(layout.modal_norms(generic,dual=True))/np.linalg.norm(layout.modal_norms(generic,dual=True))<LIMITS['excitation']:
   raise ValueError('complete generic direct FE load must excite allq')
  _gate(allocation_gate,'direct_full_original_physical_RHS',payload=4*metadata.storage_rows*16,workspace=128<<20)
  physical_storage,physical_facts=build_physical_rhs(original)
  try:physical=physical_storage.array[layout.independent].copy()
  finally:physical_storage.destroy()
  box=tuple(value*(7/135) for value in (25,33.5,6.25,18.75,40,80))
  notch_cfg=replace(cfg,case_name='y_orbit_direct_X_p4_notch',air_void_box_nm=box,geometry_identity=cfg.geometry_identity+'.notch')
  tags=_mark_cells(setup['mesh'],notch_cfg);changed=np.flatnonzero(tags.values!=setup['mesh_data'].cell_tags.values)
  if len(changed)!=2:raise ValueError('directX keeps exactly the same physical two-cell notch')
  supported,support_facts=_notch_supported_rhs(setup['spaces'][4],layout,changed)
  loads={'generic':generic,'interior_only':interior_only_rhs(setup['spaces'][4],layout,direct_profile=direct_profile),
         'physical':physical,'notch_supported':supported}
  def output_save(name,array):
   if isinstance(array,(list,tuple)):
    if not name.endswith('_direct_plane_outgoing_power_diagnostic') or len(array)!=532:raise TypeError('only bounded532 knownpowerlist conversion is admitted')
    _gate(allocation_gate,'direct_known_power_list',payload=532*8,workspace=1<<20);array=np.asarray(array,dtype=float)
   return save(name,array)
  regular={}
  for label in SOURCES:
   rhs=loads[label];save(label+'_rhs',rhs);x=inverse.apply_array(rhs);prefix='regular_'+label;save(prefix+'_solution',x)
   packet=original_packet(original,layout,rhs,x,label=prefix,save=save,alpha=inverse.last_port_solution.copy());_check_original(packet)
   packet['outputs']=recovered_field_and_modes(original,layout,x,physical=label=='physical',label=prefix,save=output_save)
   require_output_packet(packet['outputs'],label=prefix,event=event);regular[label]=packet
  mesh_data=SimpleNamespace(**vars(setup['mesh_data']));mesh_data.cell_tags=tags
  mesh_data.rectangular_air_void_audit=_rectangular_air_void_audit(setup['mesh'],tags,notch_cfg)
  _gate(allocation_gate,'direct_notch_original_volume_constructor',payload=16<<20,workspace=128<<20)
  volume1=_build_split_volume_action(mesh_data,notch_cfg,setup['spaces'][4],setup['floquets'][4],jit_options={})
  notched=FullspacePhysicalAction(volume1,original['dtn_action'],owns_dtn=False);action1=FullOriginalAction(notched,layout)
  notch_bundle={**original,'setup':{**setup,'mesh_data':mesh_data},'cfg':notch_cfg,'mesh_data':mesh_data,'volume_action':volume1,'physical_action':notched,'action':notched}
  notch_source=export_direct_volume_source(notch_bundle,full_entities,allocation_gate=allocation_gate,
                                        save_array=save,load_array=load,role='notch',direct_profile=direct_profile,entity_config=cfg)
  samples=[]
  for q in range(metadata.ny):
   modal=np.zeros(metadata.independent_rows,complex);j=np.arange(metadata.rows_per_q)
   modal[q*metadata.rows_per_q:(q+1)*metadata.rows_per_q]=np.cos(.37*j)+1j*np.sin(.23*j)
   x=layout.primal_from_modal(modal);delta=layout.dual_to_modal(action1.apply(x)-action0.apply(x));total=float(np.linalg.norm(delta))
   delta[q*metadata.rows_per_q:(q+1)*metadata.rows_per_q]=0
   samples.append({'source_q':q,'delta_dual_norm':total,'off_q_delta_dual_norm':float(np.linalg.norm(delta))})
  coupling=float(np.sqrt(sum(item['off_q_delta_dual_norm']**2 for item in samples)/sum(item['delta_dual_norm']**2 for item in samples)))
  if not np.isfinite(coupling) or coupling<1e-8:raise ValueError('direct actual full3D notch must coupleq')
  notch={};defects={}
  for label in SOURCES:
   rhs=loads[label];defects[label]=sampled_right_pc_defect(action0,action1,inverse,rhs)
   _gate(allocation_gate,'direct_original_full3D_FGMRES_vectors',payload=96*metadata.independent_rows*16,
         workspace=32<<20,restart=32,max_iterations=128,all_FE_rows=metadata.independent_rows)
   x,krylov=solve_notched_fgmres(action1,inverse,rhs);prefix='notch_'+label;save(prefix+'_solution',x)
   packet=original_packet(notch_bundle,layout,rhs,x,label=prefix,save=save);_check_original(packet);packet.update(krylov)
   if packet['reason']<=0:raise ValueError('direct original notch FGMRES must positively converge')
   norms=np.asarray(layout.modal_norms(x,dual=False));packet['nonzero_q_primal_relative']=float(np.linalg.norm(norms[1:])/np.linalg.norm(norms))
   if label=='physical' and packet['nonzero_q_primal_relative']<=1e-12:raise ValueError('physical original notch must have nonzero transverseq')
   packet['outputs']=recovered_field_and_modes(notch_bundle,layout,x,physical=label=='physical',label=prefix,save=output_save)
   require_output_packet(packet['outputs'],label=prefix,event=event);notch[label]=packet
  exit_carriers=same_live_carriers('before_successful_exit')
  evidence.snapshot('apply_recovery_complete')
  return {**report,'status':'QUOTIENT_FULL3D_INVERSE_PROBE_PASS','factor_count':metadata.ny,'PDE_solved':True,
      'factor':factors.audit,'same_live_carrier_identity_at_exit':exit_carriers,'augmented_controls':manufactured,'regular_sources':regular,'notched_sources':notch,
      'physical_rhs_facts':physical_facts,'changed_cells':changed.tolist(),'notch_config':_jsonable(notch_cfg.as_jsonable()),
      'notch_original_volume_source':notch_source,'notch_supported_RHS':support_facts,
      'sampled_notch_q_coupling':samples,'sampled_notch_off_q_delta_relative':coupling,'sampled_right_PC_defect':defects,
      'PC_defect_is_norm_bound':False,'target_geometry_accuracy':False,'no_2TB_or_48h_claim':True}
 finally:
  if action1 is not None:action1.close()
  if action0 is not None:action0.close()
  if factors is not None:factors.destroy()
  for sector in reversed(sectors):sector['condensed'].destroy()
  if notched is not None:notched.destroy()
  anchors=evidence.owner_weak_anchors();evidence.named.clear()
  sectors.clear();providers.clear();provider_records.clear();matrices.clear()
  if fresh is not None:fresh.destroy()
  fresh=full_entities=layout=original=coords=trace=condensed=provider=matrix=local=bundle=entities=sector=value=ids=array=None
  factors=inverse=action0=action1=notched=local_layout=setup=array=None
  active_error=sys.exc_info()[0]
  if active_error is None:evidence.cleanup(anchors)
  else:evidence.failure_cleanup(anchors,active_error.__name__)
