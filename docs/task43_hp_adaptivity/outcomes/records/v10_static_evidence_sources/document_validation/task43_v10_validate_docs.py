"""Bounded final JSON/hash/excerpt/link checks and render-input preparation."""
import datetime,hashlib,json,re,subprocess
from pathlib import Path
root=Path('/home/fenics/Projects/NN-Lab-V2'); art=root/'benchmarks/artifacts/task43/v10_static_correction'
base=root/'docs/task43_hp_adaptivity/outcomes/records'; src=base/'v10_static_evidence_sources'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def strict(p):
 def pairs(items):
  d={}
  for k,v in items:
   assert k not in d,('duplicate JSON key',str(p),k)
   d[k]=v
  return d
 return json.loads(p.read_text(),object_pairs_hook=pairs)
hash_checks=[]
def walk(o):
 if isinstance(o,dict):
  if isinstance(o.get('path'),str) and isinstance(o.get('sha256'),str):
   p=Path(o['path']); p=p if p.is_absolute() else root/p
   if p.is_relative_to(root):
    assert p.is_file(),str(p)
    assert sha(p)==o['sha256'],str(p)
    hash_checks.append(str(p.relative_to(root)))
  for v in o.values():walk(v)
 elif isinstance(o,list):
  for v in o:walk(v)
json_paths=sorted(src.rglob('*.json'))+[base/'v10_static_evidence_correction_v1.json']
for p in json_paths:walk(strict(p))
context=strict(src/'v9_static_input_context.json');excerpt_count=0
for rec in context['raw_records']:
 raw=(root/rec['files']['stdout']['path']).read_text().splitlines()
 for line in rec['bounded_saved_stdout_excerpt']:
  assert raw[line['line']-1]==line['text'],(rec['record'],line)
  excerpt_count+=1
 if rec.get('command_text') is not None:
  assert (root/rec['files']['command']['path']).read_text().strip()==rec['command_text'].strip()
 assert (root/rec['files']['exit_code']['path']).read_text().strip()==rec['recorded_exit_code']
activation=next(r for r in context['raw_records'] if r['record']=='activation_mca')['bounded_saved_stdout_excerpt']
assert any(x['line']==15 and '46:source' in x['text'] for x in activation)
assert {28,29}.issubset({x['line'] for x in activation})
files=['docs/README.md','docs/development_model_registry.md','docs/development_progress.md','docs/task43_hp_adaptivity/README.md','docs/task43_hp_adaptivity/outcomes/summary.md','docs/task43_hp_adaptivity/outcomes/selective_merge_manifest.md','docs/task43_hp_adaptivity/response_v10.md',str((src/'README.md').relative_to(root))]
modified=subprocess.check_output(['git','diff','--name-only'],cwd=root,text=True).splitlines()
assert set(modified)<=set(files),modified
assert subprocess.check_output(['git','diff','9be37f5dda06039e50400d395baa732e70012976','--','src','benchmarks','scripts','AGENTS.md','docs/AGENTS.md','docs/task43_hp_adaptivity/AGENTS.md','docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources'],cwd=root)==b''
subprocess.run(['git','diff','--check'],cwd=root,check=True)
render_chunks=[];selected=[];links=[];tables=0
for f in files:
 p=root/f;text=p.read_text();lines=text.splitlines()
 if f.endswith('response_v10.md') or p==src/'README.md':end=len(lines)
 elif f=='docs/README.md':end=next(i for i,l in enumerate(lines) if l.startswith('`docs/task'))
 elif f=='docs/task43_hp_adaptivity/README.md':end=next(i for i,l in enumerate(lines) if l=='## 与其他研究线的关系')
 else:end=next(i for i,l in enumerate(lines) if l.startswith('## ') and 'V9' in l)
 chunk='\n'.join(lines[:end])+'\n'
 for target in re.findall(r'\[[^\]]+\]\(([^\s)]+)\)',chunk):
  if target.startswith(('https://','http://','#')):continue
  assert (p.parent/target.split('#')[0]).exists(),(f,target)
  links.append([f,target])
 previous_cells=None
 for line in chunk.splitlines():
  if line.startswith('|'):
   cells=len(re.split(r'(?<!\\)\|',line))-2
   if previous_cells is None:tables+=1
   else:assert cells==previous_cells,(f,line)
   previous_cells=cells
  else:previous_cells=None
 render_chunks.append('## 文件：'+f+'\n\n'+chunk)
 selected.append({'path':f,'full_file_sha256':sha(p),'rendered_lines':[1,end],'slice_sha256':hashlib.sha256(chunk.encode()).hexdigest()})
payload={'text':'\n\n---\n\n'.join(render_chunks),'mode':'gfm','context':'Rookie1234567/MyFEniCS'}
(art/'github_render_request.json').write_text(json.dumps(payload,ensure_ascii=False))
result={'schema':'task43.v10.final-document-static-validation.v1','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'json_files':len(json_paths),'path_hash_checks':len(hash_checks),'unique_hash_paths':len(set(hash_checks)),'saved_stdout_excerpt_lines_checked':excerpt_count,'local_links_checked':len(links),'tables_checked':tables,'historical_and_source_paths_unchanged':True,'modified_tracked_paths':modified,'render_input':selected,'github_render_request_sha256':sha(art/'github_render_request.json'),'scope':'only saved texts, JSON, local links and Markdown table structure; no imported project modules or tests'}
with (art/'root_document_validation.json').open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
