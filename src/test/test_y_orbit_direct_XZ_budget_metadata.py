"""Explicit XZ research metadata; no FE, JIT, factor or PDE imports."""
from pathlib import Path
import ast,copy,json,math,sys,unittest
ROOT=Path(__file__).resolve().parents[2]
REPO=ROOT.parents[2]/'repo' if ROOT.name=='runner' else ROOT
RUNNER=ROOT/'benchmarks/run_y_orbit_quotient_probe.py'
KEEP={'research_wall_budget','research_memory_budget','validate_research_memory_launch',
      'research_memory_child_budget','research_phase_budget','research_watchdog_environment','plan_metadata','validate_worker_result'}
SCOPE={'Path':Path,'json':json,'math':math,'WALL_SECONDS':600,'TREE_CAP_BYTES':1610612736,
       'RESERVE_BYTES':128<<20,'FACTOR_ALLOWANCE_BYTES':512<<20,'PASSES':{'prefactor':'QUOTIENT_PREFACTOR_COMPARE_PASS','solve':'QUOTIENT_FULL3D_INVERSE_PROBE_PASS'},
       'DIRECT_SCHEMA':'task40extra.y-orbit-direct-profile-probe.v1','SCHEMA':'task40extra.y-orbit-two-cell-quotient-probe.v1'}
TREE=ast.parse(RUNNER.read_text())
exec(compile(ast.Module(body=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in KEEP],type_ignores=[]),str(RUNNER),'exec'),SCOPE)

def envelope(cap=3*1024**3):
 reserve=4*1024**3
 return {'launch_cap_bytes':cap+(128<<20),'effective_available_bytes':reserve+cap+(128<<20),
         'effective_total_bytes':10*1024**3,'reserve_bytes':reserve,'cgroup_limits':[]}

class XZResearchBudgetTests(unittest.TestCase):
 def test_explicit_profiles_and_ordinary_defaults(self):
  wall=SCOPE['research_wall_budget'];memory=SCOPE['research_memory_budget']
  for p in (None,'X','XZ'):self.assertEqual(wall(p,None),600);self.assertEqual(memory(p,'solve',None,None),1610612736)
  self.assertEqual(wall('X',1800),1800);self.assertEqual(wall('XZ',4500),4500)
  self.assertEqual(memory('X','solve',1800,2),2*1024**3);self.assertEqual(memory('XZ','solve',4500,3),3*1024**3)
  with self.assertRaises(ValueError):memory('XZ','solve',4500,None)
  for p,t,m in [('X',4500,3),('XZ',1800,2),('Y',4500,3),(None,4500,3),('XZ',4500,2),('X',1800,3)]:
   with self.subTest(tuple=(p,t,m)),self.assertRaises(ValueError):memory(p,'solve',t,m)
  for p,t in [('Y',4500),('X',4500),('XZ',1800),('XZ',4501),('XZ',True)]:
   with self.assertRaises(ValueError):wall(p,t)
  for stage in ('prefactor',None,'other'):
   with self.assertRaises(ValueError):memory('XZ',stage,4500,3)
  for v in (True,3.,'3',4):
   with self.assertRaises(ValueError):memory('XZ','solve',4500,v)

 def test_XZ_requires_fresh4GiB_reserve_dynamic_and_cgroup_headroom(self):
  call=SCOPE['validate_research_memory_launch'];kw={'direct_profile':'XZ','research_wall_seconds':4500}
  value=call(envelope(),3,**kw)
  self.assertEqual(value['requested_tree_cap_bytes'],3*1024**3)
  self.assertEqual(value['required_cap_plus_evidence_reserve_bytes'],3*1024**3+(128<<20))
  self.assertTrue(value['launch_admission_passed']);self.assertIsNone(call({},None))
  self.assertEqual(call(envelope(2*1024**3),2)['requested_tree_cap_bytes'],2*1024**3)
  for k,v in [('reserve_bytes',3*1024**3),('launch_cap_bytes',3*1024**3),
              ('effective_available_bytes',3*1024**3+(128<<20)),('effective_total_bytes',3*1024**3),
              ('cgroup_limits',[{'limit_bytes':3*1024**3,'current_bytes':0}]),('cgroup_limits',None)]:
   e=envelope();e[k]=v
   with self.subTest(field=k),self.assertRaises(MemoryError):call(e,3,**kw)
  for p,t in [(None,None),('X',4500),('XZ',1800),('Y',4500)]:
   with self.assertRaises(ValueError):call(envelope(),3,direct_profile=p,research_wall_seconds=t)

 def test_exact_child_argv_environment_and_admitted_packet(self):
  receipt=SCOPE['validate_research_memory_launch'](envelope(),3,direct_profile='XZ',research_wall_seconds=4500)
  output=SCOPE['research_watchdog_environment'](4500,4300,3,receipt,direct_profile='XZ')
  env=output['worker_environment'];self.assertEqual(env['QUOTIENT_RESEARCH_MEMORY_PROFILE'],'XZ')
  self.assertEqual(env['QUOTIENT_RESEARCH_MEMORY_GIB'],'3');self.assertEqual(env['QUOTIENT_RESEARCH_TREE_CAP_BYTES'],str(3*1024**3))
  self.assertEqual(SCOPE['research_phase_budget']('XZ',4500,env),4300)
  cap,got=SCOPE['research_memory_child_budget']('XZ','solve',4500,3,env,3*1024**3)
  self.assertEqual(cap,3*1024**3);self.assertEqual(got,receipt)
  for field,bad in [('QUOTIENT_RESEARCH_MEMORY_PROFILE','X'),('QUOTIENT_RESEARCH_MEMORY_GIB','2'),
                    ('QUOTIENT_RESEARCH_MEMORY_STAGE','prefactor'),('QUOTIENT_RESEARCH_TREE_CAP_BYTES',str(2*1024**3))]:
   e=dict(env);e[field]=bad
   with self.assertRaises(ValueError):SCOPE['research_memory_child_budget']('XZ','solve',4500,3,e,3*1024**3)
  for cap in (2*1024**3,4*1024**3):
   with self.assertRaises(ValueError):SCOPE['research_memory_child_budget']('XZ','solve',4500,3,env,cap)
  bad=copy.deepcopy(receipt);bad['requested_memory_gib']=2
  with self.assertRaises(ValueError):SCOPE['research_watchdog_environment'](4500,4300,3,bad,direct_profile='XZ')
  with self.assertRaises(ValueError):SCOPE['research_watchdog_environment'](4500,4300,3,receipt)
  for phase in (0,4501,float('nan'),float('inf')):
   with self.assertRaises(ValueError):SCOPE['research_watchdog_environment'](4500,phase,3,receipt,direct_profile='XZ')

 def test_historical_X2_environment_output_and_None_remain_exact(self):
  receipt=SCOPE['validate_research_memory_launch'](envelope(2*1024**3),2)
  env=SCOPE['research_watchdog_environment'](1800,1700,2,receipt)['worker_environment']
  self.assertEqual(env,{'QUOTIENT_RESEARCH_WALL_SECONDS':'1800','QUOTIENT_PHASE_WALL_SECONDS':'1700',
   'QUOTIENT_RESEARCH_MEMORY_GIB':'2','QUOTIENT_RESEARCH_TREE_CAP_BYTES':str(2*1024**3),
   'QUOTIENT_RESEARCH_MEMORY_PROFILE':'X','QUOTIENT_RESEARCH_MEMORY_STAGE':'solve',
   'QUOTIENT_RESEARCH_MEMORY_LAUNCH_ADMISSION':json.dumps(receipt,sort_keys=True,allow_nan=False)})
  self.assertEqual(SCOPE['research_memory_child_budget']('X','solve',1800,2,env,2*1024**3),(2*1024**3,receipt))
  self.assertEqual(SCOPE['research_watchdog_environment'](None,600),{})
  self.assertEqual(SCOPE['research_memory_child_budget'](None,'solve',None,None,{},1610612736),(1610612736,None))
  with self.assertRaises(ValueError):SCOPE['research_memory_child_budget'](None,'solve',None,None,env,1610612736)

 def test_exact_XZ_derived_plan_and_held_Y(self):
  sys.path.insert(0,str(REPO))
  v=SCOPE['plan_metadata']('solve',direct_profile='XZ',research_wall_seconds=4500,research_memory_gib=3)
  self.assertEqual(v['dimensions'],[6,4,7]);self.assertEqual(v['global_cells'],168);self.assertEqual(v['local_cells'],84)
  self.assertEqual(v['global_storage_rows'],35332);self.assertEqual(v['global_independent_rows'],33024)
  self.assertEqual(v['global_interiors'],18144);self.assertEqual(v['local_storage_rows'],18364)
  self.assertEqual(v['local_independent_rows'],16512);self.assertEqual(v['local_interiors'],9072)
  self.assertEqual(v['q_augmented_rows'],[3796,3872,3872,3872]);self.assertEqual(v['tree_cap_bytes'],3*1024**3)
  self.assertEqual(v['wall_seconds'],4500);self.assertEqual(v['factor_workspace_allowance_bytes'],512<<20)
  self.assertEqual(v['evidence_reserve_bytes'],128<<20);self.assertEqual(v['physical_mode_count'],532)
  self.assertFalse(v['PDE_solved']);self.assertEqual(v['factor_count'],0)
  with self.assertRaises(ValueError):SCOPE['plan_metadata']('solve',direct_profile='Y')
  x=SCOPE['plan_metadata']('solve',direct_profile='X',research_wall_seconds=1800,research_memory_gib=2)
  self.assertEqual(x['global_cells'],120);self.assertEqual(x['local_cells'],60);self.assertEqual(x['q_augmented_rows'],[2788,2864,2864,2864])

 def test_worker_result_requires_exact_matching_X_or_XZ_profile(self):
  r={'schema':SCOPE['DIRECT_SCHEMA'],'stage':'solve','status':SCOPE['PASSES']['solve'],'degree':4,
     'physical_mode_count':532,'official_results':False,'factor_count':4,'PDE_solved':True,'prefactor_only':False,'direct_profile':'XZ'}
  self.assertTrue(SCOPE['validate_worker_result'](r,'solve',direct_profile='XZ'))
  for p in ('X','Y','other'):
   with self.assertRaises(ValueError):SCOPE['validate_worker_result'](r,'solve',direct_profile=p)
  x=dict(r,direct_profile='X');self.assertTrue(SCOPE['validate_worker_result'](x,'solve',direct_profile='X'))
  default=dict(r,schema=SCOPE['SCHEMA']);self.assertTrue(SCOPE['validate_worker_result'](default,'solve'))

 def test_actual_runner_metadata_sites_forward_profile_and_requested_budget(self):
  text=ast.unparse(TREE)
  self.assertNotIn("'research_memory_gib': 2",text)
  launches=[n for n in ast.walk(TREE) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='validate_research_memory_launch'
            and any(isinstance(a,ast.Call) and isinstance(a.func,ast.Name) and a.func.id=='memory_envelope' for a in n.args)]
  self.assertEqual(len(launches),2)
  self.assertTrue(all({'direct_profile','research_wall_seconds'}<= {k.arg for k in c.keywords} for c in launches))
  wraps=[n for n in ast.walk(TREE) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='research_watchdog_environment']
  self.assertEqual(len(wraps),2);self.assertTrue(all(any(k.arg=='direct_profile' for k in c.keywords) for c in wraps))
  factorfn=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=='allocation_request')
  self.assertIn('FACTOR_ALLOWANCE_BYTES',ast.unparse(factorfn));self.assertEqual(SCOPE['FACTOR_ALLOWANCE_BYTES'],512<<20)

if __name__=='__main__':unittest.main()
