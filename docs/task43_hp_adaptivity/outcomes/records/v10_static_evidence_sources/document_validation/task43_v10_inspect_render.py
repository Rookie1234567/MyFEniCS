"""Inspect saved GitHub GFM HTML; no project/native modules."""
import hashlib,json
from html.parser import HTMLParser
from pathlib import Path
p=Path('/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v10_static_correction')
class P(HTMLParser):
 def __init__(self):super().__init__();self.tables=[];self.row=None;self.cell=None;self.text=[]
 def handle_starttag(self,tag,attrs):
  if tag=='table':self.tables.append([])
  if tag=='tr':self.row=[]
  if tag in ('th','td'):self.cell=[]
 def handle_data(self,data):
  self.text.append(data)
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag in ('td','th'):
   self.row.append(''.join(self.cell));self.cell=None
  if tag=='tr':self.tables[-1].append(self.row);self.row=None
raw=(p/'github_render.html').read_bytes();h=P();h.feed(raw.decode())
assert len(h.tables)==7
for table in h.tables:
 assert len(table)>1
 assert len({len(row) for row in table})==1
text=''.join(h.text)
for word in ('Task43 V10 回应','781–795','829–844','885–904','61 / 18','UNKNOWN','NOT_PASSED','NOT_ESTABLISHED'):
 assert word in text,word
result={'schema':'task43.v10.github-gfm-render-inspection.v1','http_status':200,'html_sha256':hashlib.sha256(raw).hexdigest(),'render_request_sha256':hashlib.sha256((p/'github_render_request.json').read_bytes()).hexdigest(),'table_count':len(h.tables),'tables':h.tables,'scope':'GitHub official /markdown GFM HTML of exact current document slices/full new responses; not a browser screenshot or complete historical-document visual audit'}
with (p/'github_render_inspection.json').open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
