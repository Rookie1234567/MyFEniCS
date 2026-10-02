"""Strict reviewed Step0-to-directX source/ABI identity; metadata only."""
from __future__ import annotations
import hashlib
import json
import ast
from pathlib import Path
import re

STEP0_HEAD='3570347cbd1faf7149611146b8f0f1bdd71f19e6'
STEP0_RUN='y_orbit_quotient_p4_phi5_shared_transform_attempt1'
STEP0_REPORT_SHA='810681910e60419a0c8ab038a6bf3c77541e05cd969b0dfc00abcf8626cc9c9b'
STEP0_CHECKER_SHA='5c83b79d55058bfd7b5b488c38cc840148eb13a15fdf97be61a312b53b794905'
STEP0_PROVENANCE_SHA='26779fff21877fbd5c5261eda40e55b5ce04a70ead9e7b044a3f034cbdbdedf0'
STEP0_SOURCE_SHA='81b1a3f526679d38e29a5e59124943a1f1dc4248356fec6ee8aa2b0e3ed28fce'
SCHEMA='task40extra.step0-to-directX-source-contract.v1'
ALLOWED_PATHS=frozenset({
 'src/solvers/y_orbit_direct_profile.py','src/solvers/y_orbit_quotient_context.py',
 'src/solvers/y_orbit_two_cell_transport.py','src/solvers/y_orbit_quotient_condensed.py',
 'src/solvers/y_orbit_two_cell_block_audit.py','src/solvers/y_orbit_two_cell_inverse.py',
 'src/solvers/dtn_boundary_plane_qualification.py','src/solvers/y_orbit_quotient_raw_qualification.py',
 'src/solvers/y_orbit_raw_packet_spool.py','src/solvers/y_orbit_centered_evidence.py',
 'src/solvers/y_orbit_shared_transform_evidence.py','src/solvers/y_orbit_direct_carrier_qualification.py',
 'src/solvers/y_orbit_direct_operator_qualification.py','src/solvers/y_orbit_direct_probe.py',
 'benchmarks/run_y_orbit_quotient_probe.py','benchmarks/check_y_orbit_quotient_probe.py',
 'benchmarks/check_y_orbit_direct_probe.py','benchmarks/y_orbit_direct_source_contract.py',
 'src/test/test_y_orbit_direct_profile.py','src/test/test_y_orbit_direct_carrier_metadata.py',
 'src/test/test_y_orbit_direct_operator_metadata.py','src/test/test_y_orbit_direct_pipeline_metadata.py',
 'src/test/test_y_orbit_quotient_raw_qualification.py','src/test/test_y_orbit_raw_packet_spool.py',
 'src/solvers/y_orbit_raw_observer_admission.py','src/test/test_y_orbit_direct_raw_observer_metadata.py',
 'src/test/test_y_orbit_raw_observer_source_contract.py',
 'src/test/test_y_orbit_direct_budget_metadata.py','src/test/test_y_orbit_direct_descriptor_metadata.py',
 'src/solvers/fullspace_dtn_action.py','src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py',
 'src/solvers/dtn_boundary_phase_gauge.py',
 'src/test/test_y_orbit_direct_event_stream_metadata.py',
 'src/test/test_y_orbit_direct_XZ_budget_metadata.py',
 'src/test/test_y_orbit_direct_XZ_checker_metadata.py',
 'src/test/test_y_orbit_direct_XZ_solver_metadata.py',
 'src/test/test_y_orbit_direct_XZ_interior_metadata.py',
 'src/test/test_y_orbit_direct_XZ_coverage_metadata.py',
 'src/test/test_y_orbit_direct_Y_runtime_metadata.py',
 'src/test/test_y_orbit_direct_Y_solver_metadata.py',
 'src/test/test_y_orbit_direct_Y_checker_metadata.py',
 'src/test/test_y_orbit_quotient_probe_metadata.py',
 'src/test/test_y_orbit_direct_Y_H_normalization_metadata.py',
})
ENV_FIELDS=('python','prefix','modules','petsc_scalar_type','petsc_int_type','petsc_version',
            'mpi_library','qualification_manifest_sha256','qualification_scope')
RAW_OBSERVER_BASELINE_AST = {
 'src/solvers/fullspace_dtn_action.py':'7826924d16f8cc89149f494f0688bb5767fdb3e6ab388b457479556dcdcc1fd2',
 'src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py':'88247190179167e4d69f3b7fc37499e8703003c8f5ab2c68d01c460818d625f2',
 'src/solvers/dtn_boundary_phase_gauge.py':'fa39fcae0e0bb15b7ff1e875f40caa62bfcc6c276f31a744c20c43950bb7f7bc',
}


def _ast_dump(node):
 return ast.dump(node,include_attributes=False)


def _remove_exact_statement(root,expected):
 count=0
 for parent in ast.walk(root):
  for _name,items in ast.iter_fields(parent):
   if not isinstance(items,list):continue
   for index in range(len(items)-1,-1,-1):
    if isinstance(items[index],ast.stmt) and _ast_dump(items[index])==_ast_dump(expected):
     del items[index];count+=1
 if count!=1:raise ValueError('approved metadata statement must occur exactly once')


def normalized_raw_observer_ast(path,text):
 """Erase only the reviewed named metadata/API seams, then hash the whole module."""
 tree=ast.parse(text)
 if path not in RAW_OBSERVER_BASELINE_AST:raise ValueError('unknown protected raw-observer module')
 if path.endswith('dtn_boundary_phase_gauge.py'):
  function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='build_gauge_assembly_context')
  prelude=ast.parse('''expected_local_cells = 40
if quotient_context.direct_profile_name is not None:
    from .y_orbit_raw_observer_admission import direct_raw_observer_expected_local_cells
    expected_local_cells = direct_raw_observer_expected_local_cells(quotient_context, cfg)
''').body
  local_blocks=[node for node in function.body if isinstance(node,ast.If)
                and ast.unparse(node.test)=='quotient_context is not None']
  if (len(local_blocks)!=1 or len(local_blocks[0].body)<6
      or [_ast_dump(item) for item in local_blocks[0].body[3:5]]!=[_ast_dump(item) for item in prelude]):
   raise ValueError('local-cell prelude must immediately follow the original context type guard')
  for statement in prelude:_remove_exact_statement(function,statement)
  old=ast.parse('cell_count != 40',mode='eval').body
  new=ast.parse('cell_count != expected_local_cells',mode='eval').body
  class RestoreComparison(ast.NodeTransformer):
   count=0
   def visit_Compare(self,node):
    if _ast_dump(node)==_ast_dump(new):self.count+=1;return old
    return self.generic_visit(node)
  restore=RestoreComparison();restore.visit(function)
  if restore.count!=1 or any(isinstance(node,ast.Name) and node.id=='expected_local_cells' for node in ast.walk(tree)):
   raise ValueError('only the exact reviewed local-cell metadata comparison may change')
  old_area=ast.parse('(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*2',mode='eval').body
  new_area=ast.parse('(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*quotient_context.replication_count',mode='eval').body
  class RestoreQuotientAreaMetadata(ast.NodeTransformer):
   count=0
   def visit_Dict(self,node):
    for i,key in enumerate(node.keys):
     if isinstance(key,ast.Constant) and key.value=='global_boundary_area':
      value=node.values[i]
      if (not isinstance(value,ast.Call) or not isinstance(value.func,ast.Name) or value.func.id!='float'
          or len(value.args)!=1 or _ast_dump(value.args[0])!=_ast_dump(new_area)):
       raise ValueError('only the exact quotient global-area metadata seam is admitted')
      self.count+=1;value.args[0]=old_area
    return self.generic_visit(node)
  restore_area=RestoreQuotientAreaMetadata();restore_area.visit(function)
  if restore_area.count!=1:raise ValueError('the exact single quotient global-area metadata seam must occur')
 else:
  name='build_fullspace_dtn_carrier_from_surface' if path.endswith('fullspace_dtn_action.py') else 'build_same_mesh_physical_action'
  function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name)
  positions=[i for i,arg in enumerate(function.args.kwonlyargs) if arg.arg=='raw_observer_profile']
  if len(positions)!=1:raise ValueError('explicit raw observer keyword must occur once')
  index=positions[0]
  if (ast.unparse(function.args.kwonlyargs[index].annotation)!='str | None'
      or not isinstance(function.args.kw_defaults[index],ast.Constant)
      or function.args.kw_defaults[index].value is not None):raise ValueError('raw observer default must remain None')
  del function.args.kwonlyargs[index];del function.args.kw_defaults[index]
  guard=ast.parse('''if raw_observer_profile is not None and raw_mode_observer is None:
    raise ValueError("raw observer profile requires its explicit research callback")
''').body[0]
  if path.endswith('fullspace_dtn_action.py'):
   location=1
  else:
   anchors=[i for i,node in enumerate(function.body) if isinstance(node,ast.Expr)
            and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name)
            and node.value.func.id=='validate_phase_gauge']
   if len(anchors)!=1:raise ValueError('existing phase validation anchor must occur once')
   location=anchors[0]+1
  if location>=len(function.body) or _ast_dump(function.body[location])!=_ast_dump(guard):
   raise ValueError('explicit callback rejection must retain the approved early position')
  _remove_exact_statement(function,guard)
  if path.endswith('fullspace_dtn_action.py'):
   raw_condition=ast.parse('raw_mode_observer is not None',mode='eval').body
   profile_condition=ast.parse('raw_observer_profile is None',mode='eval').body
   outers=[node for node in ast.walk(function) if isinstance(node,ast.If) and _ast_dump(node.test)==_ast_dump(raw_condition)
           and len(node.body)==1 and isinstance(node.body[0],ast.If) and _ast_dump(node.body[0].test)==_ast_dump(profile_condition)]
   if len(outers)!=1 or len(outers[0].body)!=1 or outers[0].orelse:raise ValueError('exact old raw-observer gate wrapper required')
   wrapper=outers[0].body[0]
   expected=ast.parse('''if raw_observer_profile is None:
    pass
else:
    from .y_orbit_raw_observer_admission import validate_direct_raw_observer_profile
    validate_direct_raw_observer_profile(raw_observer_profile, modes=modes, mpc=mpc, cfg=cfg,
        assembly_context=assembly_context, physical_cfg=physical_cfg, quotient_context=quotient_context,
        physical_manifest_sha=_manifest_sha, surface_assemblers=surface_assemblers)
''').body[0]
   if (not isinstance(wrapper,ast.If) or _ast_dump(wrapper.test)!=_ast_dump(expected.test)
       or [_ast_dump(item) for item in wrapper.orelse]!=[_ast_dump(item) for item in expected.orelse]):
    raise ValueError('only the explicit X admission else branch may be added')
   outers[0].body=wrapper.body
   # Exactly two quotient-validation/identity expressions used the original
   # K=2 fixture. Restore those alone for the original operator AST comparison.
   old_product=ast.parse('np.isclose(denominator*2,global_h,rtol=32*np.finfo(float).eps,atol=0)',mode='eval').body
   new_product=ast.parse('np.isclose(denominator*quotient_context.replication_count,global_h,rtol=32*np.finfo(float).eps,atol=0)',mode='eval').body
   new_scale=ast.parse('1/quotient_context.replication_count',mode='eval').body
   class RestoreQuotientHMetadata(ast.NodeTransformer):
    product_count=0
    scale_count=0
    def visit_Call(self,node):
     if _ast_dump(node)==_ast_dump(new_product):
      self.product_count+=1;return old_product
     return self.generic_visit(node)
    def visit_Dict(self,node):
     for i,key in enumerate(node.keys):
      if isinstance(key,ast.Constant) and key.value=='local_H_scale_from_global_plane_H':
       if _ast_dump(node.values[i])!=_ast_dump(new_scale):raise ValueError('only the exact quotient1/K identity seam is admitted')
       self.scale_count+=1;node.values[i]=ast.Constant(0.5)
     return self.generic_visit(node)
   restore_H=RestoreQuotientHMetadata();restore_H.visit(function)
   if (restore_H.product_count,restore_H.scale_count)!=(1,1):
    raise ValueError('the exact single quotientK validation and1/K identity seam must both occur')
  else:
   forwarded=0
   for node in ast.walk(function):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='build_fullspace_dtn_carrier_from_surface':
     for keyword in list(node.keywords):
      if keyword.arg=='raw_observer_profile':
       if not isinstance(keyword.value,ast.Name) or keyword.value.id!='raw_observer_profile':raise ValueError('raw profile must be forwarded unchanged')
       node.keywords.remove(keyword);forwarded+=1
   if forwarded!=2:raise ValueError('exactly the two raw/quotient API forwards are required')
 if any(isinstance(node,ast.Name) and node.id=='raw_observer_profile' for node in ast.walk(tree)):
  raise ValueError('unreviewed use of raw-observer profile remains')
 return hashlib.sha256(_ast_dump(tree).encode()).hexdigest()


def validate_raw_observer_ast_seams(new_files):
 root=Path(__file__).resolve().parents[1];proof=[]
 for path,baseline in RAW_OBSERVER_BASELINE_AST.items():
  actual=root/path;data=actual.read_bytes()
  if hashlib.sha256(data).hexdigest()!=new_files.get(path):raise ValueError('actual protected module bytes differ from new source receipt')
  normalized=normalized_raw_observer_ast(path,data.decode())
  if normalized!=baseline:raise ValueError('protected numerical/default AST changed outside reviewed raw-observer seams: '+path)
  proof.append({'path':path,'whole_file_byte_equality_claimed':False,'baseline_whole_AST_sha256':baseline,
                'normalized_new_whole_AST_sha256':normalized,'numerical_and_None_default_AST_unchanged':True,
    'explicit_quotient_H_metadata_seam': ({'validation':'actual_local_H*validated_context_K against original_global_H',
      'identity':'1/validated_context_K','old_K2_exactly_unchanged':True,'denominator_and_C_D_assembly_unchanged':True,
      'rtol':'32*float64_eps','atol':0} if path.endswith('fullspace_dtn_action.py') else
     {'global_area_diagnostic':'local_area*validated_context_K','no_current_consumers':True,
      'old_K2_exactly_unchanged':True} if path.endswith('dtn_boundary_phase_gauge.py') else None)})
 return proof


def digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def validate_direct_source(old,new,old_env,new_env,*,direct_profile="X"):
 if direct_profile not in ("X","XZ","Y"):raise ValueError("only explicit X/XZ/Y source profiles are admitted")
 if (old.get('head')!=STEP0_HEAD or old.get('dirty') or new.get('dirty') or new.get('head')==STEP0_HEAD
     or not re.fullmatch('[0-9a-f]{40}',new.get('head','')) or old.get('branch')!='task40extra_dot_parallel_cloud'
     or new.get('branch')!=old.get('branch') or digest(old.get('files_sha256',{}))!=STEP0_SOURCE_SHA):
  raise ValueError('directX requires qualified immutable Step0 and actual distinct clean integrated source')
 before,after=old['files_sha256'],new.get('files_sha256',{})
 changed=sorted(name for name in set(before)|set(after) if before.get(name)!=after.get(name))
 required={name for name in ALLOWED_PATHS if not name.startswith('src/test/')}
 if (not after or any(not re.fullmatch('[0-9a-f]{64}',sha) for sha in after.values())
     or not set(changed).issubset(ALLOWED_PATHS) or not required.issubset(changed)
     or any(name not in after for name in required)):
  raise ValueError('only the complete reviewed direct profile/qualification/pipeline source changes are admitted')
 if any(name not in old_env or name not in new_env or old_env[name]!=new_env[name] for name in ENV_FIELDS):
  raise ValueError('direct calibration ABI differs from qualified Step0')
 ast_seams=validate_raw_observer_ast_seams(after)
 return {'schema':SCHEMA,'step0_head':STEP0_HEAD,'new_head':new['head'],
   'step0_report_sha256':STEP0_REPORT_SHA,'step0_checker_sha256':STEP0_CHECKER_SHA,
   'step0_dependency_manifest_sha256':digest(before),'new_dependency_manifest_sha256':digest(after),
   'changed_dependencies':[{'path':name,'old_sha256':before.get(name),'new_sha256':after.get(name)} for name in changed],
   'all_other_physical_volume_DtN_config_mode_dependencies_equal':True,'source_equality_claimed':False,
   'explicit_metadata_API_module_exceptions':ast_seams,
   'numerical_environment_fields_equal':list(ENV_FIELDS),'scope':f'fresh direct{direct_profile} profile; no historical arrays reused'}


def file_sha(path):
 result=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for block in iter(lambda:stream.read(1<<20),b''):result.update(block)
 return result.hexdigest()


def load_direct_source_contract(root,*,new_source,new_environment,allocation_gate,direct_profile="X"):
 directory=Path(root).resolve()/STEP0_RUN
 provenance_path=directory/'provenance.json'
 allocation_gate('direct_step0_source_metadata',{'matrix_payload_bytes':0,
     'workspace_bytes':8*provenance_path.stat().st_size+(4<<20)})
 # Exact qualified files are streamed; their large numerical/owner ledgers
 # never become Python objects or numerical controls for the new point.
 for name,sha in (('probe_report.json',STEP0_REPORT_SHA),('independent_checker.json',STEP0_CHECKER_SHA),
                  ('provenance.json',STEP0_PROVENANCE_SHA)):
  if file_sha(directory/name)!=sha:raise ValueError('immutable qualified Step0 metadata changed')
 provenance=json.loads(provenance_path.read_text())
 allocation_gate('direct_raw_observer_AST_metadata',{'matrix_payload_bytes':0,'workspace_bytes':16<<20})
 receipt=validate_direct_source(provenance['source'],new_source,provenance['environment'],new_environment,direct_profile=direct_profile)
 receipt['step0_provenance_sha256']=STEP0_PROVENANCE_SHA
 receipt['qualified_step0_original_check_count']=312
 receipt['qualified_step0_shared_storage_check_count']=38881
 receipt['historical_numerical_arrays_used']=False
 return receipt
