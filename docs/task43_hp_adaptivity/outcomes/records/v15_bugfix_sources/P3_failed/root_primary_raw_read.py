"""Offline stdlib arithmetic on already-saved A1 primary; no native/project imports."""
import ast, datetime, hashlib, json, math, struct, time, zipfile
from pathlib import Path
t=time.perf_counter()
repo=Path('/home/fenics/Projects/NN-Lab-V2')
root=repo/'benchmarks/artifacts/task43/v11_science/formal/A1_q_attempt3'
out=repo/'benchmarks/artifacts/task43/v11_science/recovery_v15/preparation/P3_raw_stdlib_recheck.json'
terminal=json.loads((root/'run/task43_v11_partial_terminal.json').read_text())
packet=terminal['primary_packet']; p=Path(packet['npz_path'])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(p)==packet['npz_sha256']
arrays={}; checks=[]
with zipfile.ZipFile(p) as z:
 for member in z.namelist():
  data=z.read(member);assert data[:6]==b'\x93NUMPY'
  major=data[6]; n=2 if major==1 else 4;hlen=int.from_bytes(data[8:8+n],'little')
  head=ast.literal_eval(data[8+n:8+n+hlen].decode('latin1'));payload=data[8+n+hlen:]
  assert not head['fortran_order']
  name=member[:-4]
  if name=='__task43_record_json__':
   embedded=json.loads(payload);continue
  spec=packet['arrays'][name]
  h=hashlib.sha256(head['descr'].encode()+json.dumps(list(head['shape'])).encode()+payload).hexdigest()
  assert h==spec['sha256'] and list(head['shape'])==spec['shape'] and head['descr']==spec['dtype'],name
  checks.append({'array':name,'sha256':h,'shape':spec['shape'],'dtype':spec['dtype']})
  if head['descr']=='<c16':arrays[name]=[complex(a,b) for a,b in struct.iter_unpack('<dd',payload)]
assert embedded['identity']==packet['identity']
def a(name):return arrays[name]
def sq(x):return math.fsum(v.real*v.real+v.imag*v.imag for v in x)
def dual(x,y):
 assert len(x)==len(y)
 re=math.fsum((u.conjugate()*v).real for u,v in zip(x,y))
 im=math.fsum((u.conjugate()*v).imag for u,v in zip(x,y))
 assert abs(im)<=5e-11*max(abs(re),1) and re>=-5e-11
 return max(re,0)
def ratio(r,b):return math.sqrt(r)/math.sqrt(b)
i=packet['identity'];s=i['raw_full_active_scope'];nt=s['independent_reduced_trace_rows'];ni=s['active_interior_rows'];nr=s['raw_trace_rows']
assert s['reduced_trace_dtn_owned_range']==[0,nt+612] and s['mpi_size']==1
assert nt+ni==i['independent_active_fe_dofs']==118800
pr='independent_A6_independent_active_'
assert all(v==0 for v in a(pr+'modal_lower_solver_gauge_rhs'))
a6=ratio(sum(sq(a(pr+k)) for k in ('residual_trace','residual_cell_interior','modal_lower_solver_gauge')),sum(sq(a(pr+k)) for k in ('rhs_trace','rhs_cell_interior','modal_lower_solver_gauge_rhs')))
pr='full_active_';res=a(pr+'reduced_trace_dtn_residual_Ax_minus_b_owned');rhs=a(pr+'reduced_trace_dtn_rhs_owned');sol=a(pr+'reduced_trace_dtn_solution_owned');inter=a(pr+'eliminated_active_interior_residual')
assert all(v==0 for v in inter[:nr])
full=ratio(dual(res[:nt],a(pr+'reduced_trace_dtn_residual_trace_metric_action'))+sq(res[nt:])+sq(inter),dual(rhs[:nt],a(pr+'reduced_trace_dtn_rhs_trace_metric_action'))+sq(rhs[nt:])+sq(a(pr+'active_full_rhs')[nr:]))
assert a(pr+'active_full_rhs')==a('recovered_active_full_rhs_owned')
assert a(pr+'active_full_solution')==a('recovered_active_full_solution_owned')
assert rhs==a('returned_trace_dtn_rhs') and sol==a('returned_trace_dtn_solution')
assert res==[-v for v in a('returned_trace_dtn_b_minus_Ax')]
assert a('normal_before_normal_correction_rhs')==a('normal_after_normal_correction_rhs')==rhs
assert a('normal_after_normal_correction_solution')==sol
assert a('normal_after_normal_correction_residual_b_minus_Ax')==a('returned_trace_dtn_b_minus_Ax')
condensed=ratio(sq(a('returned_trace_dtn_b_minus_Ax')),sq(rhs))
before=ratio(sq(a('normal_before_normal_correction_residual_b_minus_Ax')),sq(rhs))
normal=i['normal_correction_audit']
values={'independent_A6':{'actual':a6,'limit':1e-8},'full_active_Gram':{'actual':full,'limit':1e-8},'returned_condensed':{'actual':condensed,'limit':1e-9},'normal_before':before,'normal_after':condensed,'normal_count':i['normal_correction_count'],'extra_count':i['extra_correction_count'],'normal_reason':normal['correction_ksp']['converged_reason']}
gates={k:v['actual']<=v['limit'] and math.isfinite(v['actual']) for k,v in values.items() if isinstance(v,dict)}
gates.update(normal_once=i['normal_correction_count']==1,extra_zero=i['extra_correction_count']==0,normal_decreased=condensed<before,normal_reason_positive=normal['correction_ksp']['converged_reason']>0)
record={'schema':'task43.v15.root-primary-stdlib-recheck.v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_primary':{'path':str(p),'sha256':sha(p)},'source_terminal':{'path':str(root/'run/task43_v11_partial_terminal.json'),'sha256':sha(root/'run/task43_v11_partial_terminal.json')},'array_identity_checks':checks,'embedded_identity_equal':True,'full_scope':s,'raw_equalities_checked':True,'values':values,'gates':gates,'numerical_gates_pass':all(gates.values()),'original_endpoint_remains':'FAILED','q8_q10':'NOT_RUN','scope':'stdlib offline arithmetic only; no operator action, native import, PDE or fresh sampling','elapsed_seconds':time.perf_counter()-t}
with out.open('x') as f:json.dump(record,f,indent=2);f.write('\n')
print(json.dumps({'output':str(out),'sha256':sha(out),'values':values,'gates':gates,'seconds':record['elapsed_seconds']},indent=2))
