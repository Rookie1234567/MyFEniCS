import tarfile,hashlib,json,re
from pathlib import Path
A=Path('/workspace/scratch/9c465670b46b/archive_20261022');patterns={'private_key':rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----','github_token':rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})','aws_key':rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b','openai_key':rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{40,}','slack_token':rb'\bxox[baprs]-[A-Za-z0-9-]{20,}','credential_uri':rb'https?://[^\s/:]{1,80}:[^\s/@]{8,100}@'};hits=[];counts={};hashes=set()
for name in ['records.tar.xz','supplement.tar.gz']:
 n=0;total=0
 with tarfile.open(A/name,'r:*') as t:
  for m in t:
   if not m.isfile():raise ValueError('Unexpected nonfile '+m.name)
   b=t.extractfile(m).read();sha=hashlib.sha256(b).hexdigest()
   if name=='records.tar.xz' and m.name.startswith('blobs/') and sha!=m.name.split('/')[1]:raise ValueError('Blob mismatch')
   for k,p in patterns.items():
    if re.search(p,b):hits.append({'archive':name,'member':m.name,'pattern':k})
   hashes.add(sha);n+=1;total+=len(b)
 counts[name]={'files':n,'uncompressed_bytes':total,'sha256':hashlib.sha256((A/name).read_bytes()).hexdigest()}
r={'status':'PASS' if not hits else 'REVIEW_REQUIRED','archives':counts,'secret_scan_patterns':list(patterns),'secret_matches_without_values':hits,'limitations':'Pattern scan cannot prove absence of every unknown credential format. Scope excludes .git, installed runtime/env/library trees and private conversation exports. Worker exports are known source/tool artifacts, not chat transcripts.','checked_original_bytes':True};(A/'verification.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
