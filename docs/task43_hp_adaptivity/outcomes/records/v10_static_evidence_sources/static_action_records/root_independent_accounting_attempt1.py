"""Read saved text only; independent PACKAGE-terminated record accounting."""
import hashlib,json,re,time,datetime
from pathlib import Path
start=time.monotonic()
b=Path('/home/fenics/Projects/NN-Lab-V2');raw=b/'benchmarks/artifacts/task43/v9_resume_preparation/raw';out=b/'benchmarks/artifacts/task43/v10_static_correction'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(raw/'map_direct_needed_paths.stdout')=='42700961db2b4ca1ae2206d93c18a6e0ad8986ec72b818b26a192b082eb005c4'
assert sha(raw/'map_direct_needed_paths.sh')=='1568de57c0911a88c062df5b9d504ae42fad3e0b93217f730e55f2631ee1b8b2'
lines=(raw/'map_direct_needed_paths.stdout').read_text().splitlines();packets=[];current=None
for n,l in enumerate(lines,1):
 if l.startswith(('EDGE ','BRIDGE ')):
  assert current is None,('unclosed packet',n)
  current={'kind':l.split()[0],'line_start':n,'header':l,'lines':[]}
 elif current is not None:
  current['lines'].append(l)
  if l.startswith('PACKAGE '):
   current['line_end']=n;packets.append(current);current=None
assert current is None
edges=[];bridges=[];objects={}
for pkt in packets:
 h=pkt['header'];txt='\n'.join(pkt['lines']);a=dict(re.findall(r'(parent|needed|source|candidate|realpath)=(\S+)',h))
 hashes=re.findall(r'^([0-9a-f]{64})  (\S+)$',txt,re.M);build=re.findall(r'Build ID: ([0-9a-f]+)',txt);soname=re.findall(r'\(SONAME\).*?\[([^\]]+)\]',txt)
 assert len(hashes)==len(build)==len(soname)==1,pkt
 assert hashes[0][1]==a['realpath']
 owner=next(x for x in pkt['lines'] if x.startswith('PACKAGE_OWNER '));package=next(x[8:] for x in pkt['lines'] if x.startswith('PACKAGE '))
 assert owner.startswith('PACKAGE_OWNER exit=0 ') and owner.endswith(': '+a['realpath']),owner
 obj={'realpath':a['realpath'],'resolved_sha256':hashes[0][0],'build_id':build[0],'resolved_soname':soname[0],'needed_by_resolved_object':re.findall(r'\(NEEDED\).*?\[([^\]]+)\]',txt),'package_owner_line':owner,'package':package}
 key=(obj['realpath'],obj['resolved_sha256']);assert key not in objects or objects[key]==obj,key;objects[key]=obj
 if pkt['kind']=='EDGE':
  assert a['needed']==soname[0],('needed/SONAME mismatch',a)
  edges.append(dict(parent=a['parent'],needed_soname=a['needed'],resolution_source=a['source'],candidate_path=a['candidate'],**obj,raw_lines=[pkt['line_start'],pkt['line_end']]))
 else:
  assert h.split()[1]==soname[0];bridges.append(dict(**obj,raw_lines=[pkt['line_start'],pkt['line_end']]))
keys={(e['parent'],e['needed_soname']) for e in edges};parents={e['parent'] for e in edges}
assert len(edges)==len(keys)==61 and len(parents)==18
recheck=raw/'recheck_15_elf.stdout';assert sha(recheck)=='1ed5822173f54528544914c6e523fd2ce1241d0187a1df9f5fdf43df66201f6e'
frozen={}
for m in re.finditer(r'^===== (.+) =====\n(.*?)(?=^===== |\Z)',recheck.read_text(),re.M|re.S):
 frozen[m[1]]=set(re.findall(r'\(NEEDED\).*?\[([^\]]+)\]',m[2]))
assert len(frozen)==15
expected_old={(p,n) for p,ns in frozen.items() for n in ns};expected_bridges={(o['realpath'],n) for o in bridges for n in o['needed_by_resolved_object']}
assert len(expected_old)==48 and len(expected_bridges)==13 and not expected_old&expected_bridges and keys==expected_old|expected_bridges
old_path=b/'docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/direct_needed_edge_map.json'
old={(e['parent'],e['needed_soname']):e for e in json.loads(old_path.read_text())['edges']};assert set(old)==keys
diffs=[]
for e in edges:
 k=(e['parent'],e['needed_soname']);changes={f:{'old':v,'corrected':e[f]} for f,v in old[k].items() if e[f]!=v}
 if changes:diffs.append(dict(key=list(k),raw_lines=e['raw_lines'],changes=changes))
assert len(diffs)==3
result={'schema':'task43.v10.root-independent-offline-accounting.v1','derived_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'PACKAGE-terminated raw records; no agent parser or old audit execution','raw_sha256':sha(raw/'map_direct_needed_paths.stdout'),'collector_sha256':sha(raw/'map_direct_needed_paths.sh'),'recheck_sha256':sha(recheck),'old_edge_map_sha256':sha(old_path),'edge_count':len(edges),'unique_keys':len(keys),'parent_count':len(parents),'old15_edge_count':len(expected_old),'bridge_edge_count':len(expected_bridges),'resolved_object_count':len(objects),'same_realpath_hash_metadata_conflicts':0,'needed_soname_mismatches':0,'edges':edges,'bridges':bridges,'field_differences':diffs,'scope':'historical captured text consistency only; no installed-file or runtime claim','elapsed_seconds':time.monotonic()-start}
with (out/'root_independent_accounting.json').open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False);f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('edges','bridges')},indent=2,ensure_ascii=False))
