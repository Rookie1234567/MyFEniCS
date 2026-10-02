"""Execute approved Y production metadata/resource branches without FE/JIT/PDE."""
from pathlib import Path
import ast,copy,importlib.util,json,math,sys,tempfile,unittest
ROOT=Path(__file__).parents[2]
RUNNER=ROOT/'benchmarks/run_y_orbit_quotient_probe.py'
PROFILE=ROOT/'src/solvers/y_orbit_direct_profile.py'
sys.path.insert(0,str(ROOT))
TREE=ast.parse(RUNNER.read_text())
KEEP={'factor_policy','research_wall_budget','research_memory_budget','validate_research_memory_launch',
 'research_memory_child_budget','research_phase_budget','research_watchdog_environment','plan_metadata',
 'allocation_request','validate_worker_result','retained_factor_evidence'}
SCOPE={'Path':Path,'json':json,'math':math,'WALL_SECONDS':600,'TREE_CAP_BYTES':1610612736,
 'RESERVE_BYTES':128<<20,'FACTOR_ALLOWANCE_BYTES':512<<20,
 'PASSES':{'prefactor':'QUOTIENT_PREFACTOR_COMPARE_PASS','solve':'QUOTIENT_FULL3D_INVERSE_PROBE_PASS'},
 'DIRECT_SCHEMA':'task40extra.y-orbit-direct-profile-probe.v1','SCHEMA':'task40extra.y-orbit-two-cell-quotient-probe.v1'}
exec(compile(ast.Module(body=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in KEEP],type_ignores=[]),str(RUNNER),'exec'),SCOPE)
spec=importlib.util.spec_from_file_location('_production_Y_profile_test',PROFILE)
P=importlib.util.module_from_spec(spec);sys.modules[spec.name]=P;spec.loader.exec_module(P)

def envelope():
 return {'launch_cap_bytes':(3<<30)+(128<<20),'effective_available_bytes':(7<<30)+(128<<20),
         'effective_total_bytes':10<<30,'reserve_bytes':4<<30,'cgroup_limits':[]}

class YRuntimeMetadataTests(unittest.TestCase):
 def test_actual_metadata_plan_and_all_six_counts(self):
  d=SCOPE['plan_metadata']('solve',direct_profile='Y',research_wall_seconds=4500,research_memory_gib=3)
  self.assertEqual(d['dimensions'],[4,6,5]);self.assertEqual(d['global_cells'],120);self.assertEqual(d['local_cells'],40)
  self.assertEqual((d['global_storage_rows'],d['global_independent_rows'],d['global_interiors']),(25468,23808,12960))
  self.assertEqual((d['local_storage_rows'],d['local_independent_rows'],d['local_interiors']),(8940,7936,4320))
  self.assertEqual(d['q_augmented_rows'],[1884,1884,1884,1960,1884,1884]);self.assertEqual(d['q_port_counts'],[76,76,76,152,76,76])
  self.assertEqual(d['factor_workspace_allowance_bytes'],768<<20);self.assertEqual(d['evidence_reserve_bytes'],128<<20)
  self.assertFalse(d['PDE_solved']);self.assertEqual(d['factor_count'],0)

 def test_exact_Y_budget_and_missing_or_swapped_tuple_stops(self):
  self.assertEqual(SCOPE['research_wall_budget']('Y',4500),4500)
  self.assertEqual(SCOPE['research_memory_budget']('Y','solve',4500,3),3<<30)
  for stage,time,memory in [('solve',None,None),('solve',4500,None),('solve',1800,2),('prefactor',4500,3),('solve',4500,2),('solve',4500,True)]:
   with self.subTest(tuple=(stage,time,memory)),self.assertRaises(ValueError):SCOPE['research_memory_budget']('Y',stage,time,memory)
  with self.assertRaises(ValueError):SCOPE['plan_metadata']('solve',direct_profile='Y')

 def test_all_six_factor_admissions_and_old_four_policy(self):
  self.assertEqual(SCOPE['factor_policy']('Y'),(6,768<<20))
  for p in (None,'X','XZ'):self.assertEqual(SCOPE['factor_policy'](p),(4,512<<20))
  for q in range(6):
   f={'retained_factor_count':q,'factor_workspace_allowance_bytes':(6-q)*(128<<20),'LU_fill_and_workspace_unknown':True}
   self.assertEqual(SCOPE['allocation_request']('solve',f,direct_profile='Y')[-1],(6-q)*(128<<20))
  for q,a in [(6,128<<20),(1,768<<20),(0,512<<20)]:
   with self.assertRaises(ValueError):SCOPE['allocation_request']('solve',{'retained_factor_count':q,'factor_workspace_allowance_bytes':a,'LU_fill_and_workspace_unknown':True},direct_profile='Y')
  self.assertEqual(SCOPE['allocation_request']('solve',{'workspace_bytes':8},direct_profile='Y'),(0,8,128<<20,0))
  with self.assertRaises(ValueError):SCOPE['allocation_request']('prefactor',{'factor_count':1},direct_profile='Y')
  with self.assertRaises(ValueError):SCOPE['factor_policy']('unknown')

 def test_Y_argv_env_receipt_and_dynamic_host_cgroup_admission(self):
  admission=SCOPE['validate_research_memory_launch'](envelope(),3,direct_profile='Y',research_wall_seconds=4500)
  env=SCOPE['research_watchdog_environment'](4500,4400,3,admission,direct_profile='Y')['worker_environment']
  self.assertEqual(env['QUOTIENT_RESEARCH_MEMORY_PROFILE'],'Y');self.assertEqual(SCOPE['research_phase_budget']('Y',4500,env),4400)
  self.assertEqual(SCOPE['research_memory_child_budget']('Y','solve',4500,3,env,3<<30),(3<<30,admission))
  for key in ('QUOTIENT_RESEARCH_MEMORY_PROFILE','QUOTIENT_RESEARCH_MEMORY_GIB','QUOTIENT_RESEARCH_TREE_CAP_BYTES'):
   bad=dict(env);bad[key]='wrong'
   with self.assertRaises(ValueError):SCOPE['research_memory_child_budget']('Y','solve',4500,3,bad,3<<30)
  for key,value in [('reserve_bytes',3<<30),('launch_cap_bytes',3<<30),('cgroup_limits',[{'limit_bytes':3<<30,'current_bytes':0}])]:
   bad=envelope();bad[key]=value
   with self.assertRaises(MemoryError):SCOPE['validate_research_memory_launch'](bad,3,direct_profile='Y',research_wall_seconds=4500)

 def test_complete_Y_worker_counter_and_partial_failure_six_retained(self):
  r={'schema':SCOPE['DIRECT_SCHEMA'],'stage':'solve','status':SCOPE['PASSES']['solve'],'degree':4,'physical_mode_count':532,
   'official_results':False,'factor_count':6,'PDE_solved':True,'prefactor_only':False,'direct_profile':'Y'}
  self.assertTrue(SCOPE['validate_worker_result'](r,'solve',direct_profile='Y'))
  for q in (0,4,5,7):
   with self.assertRaises(ValueError):SCOPE['validate_worker_result'](dict(r,factor_count=q),'solve',direct_profile='Y')
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'phase.json';p.write_text(json.dumps({'factor_count':6}))
   self.assertEqual(SCOPE['retained_factor_evidence'](folder,direct_profile='Y')['count'],6)
   with self.assertRaises(ValueError):SCOPE['retained_factor_evidence'](folder)
   p.write_text(json.dumps({'factor_count':7}))
   with self.assertRaises(ValueError):SCOPE['retained_factor_evidence'](folder,direct_profile='Y')

 def test_exact_new_Y_notch_and_old_X_XZ_boxes(self):
  old=tuple(x*P.SCALE for x in (25,33.5,6.25,18.75,40,80))
  for name in ('X','XZ'):self.assertEqual(P.direct_notch_box_and_count(name),(old,2))
  box,count=P.direct_notch_box_and_count('Y');m=P.direct_profile_metadata('Y')
  self.assertEqual(count,3);self.assertEqual(box,tuple(x*P.SCALE for x in (25,33.5,25/6,100/6,40,80)))
  self.assertEqual(box[2],m.global_axes[1][1]);self.assertEqual(box[3],m.global_axes[1][4])
  self.assertAlmostEqual(box[3]-box[2],old[3]-old[2]);self.assertAlmostEqual(box[2]-old[2],(-25/12)*P.SCALE)
  for name in (None,'other'):
   with self.assertRaises(ValueError):P.direct_notch_box_and_count(name)

 def test_exact_float_Y_widths_are_retained_and_not_coalesced(self):
  m=P.direct_profile_metadata('Y');a=m.global_axes[1];widths=[y-x for x,y in zip(a,a[1:])]
  self.assertEqual(len(set(widths)),4);self.assertEqual(m.local_axes[1],a[:3])
  self.assertLess((max(widths)-min(widths))/min(widths),2e-15)

if __name__=='__main__':unittest.main()
