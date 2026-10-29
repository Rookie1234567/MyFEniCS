"""Root-only byte/header audit of a completed NPZ; no numerical array evaluation."""
import ast
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
import zipfile

start = time.monotonic()
path = Path(sys.argv[1])
target = Path(sys.argv[2])
members = {}
issues = []
embedded = None
with zipfile.ZipFile(path) as archive:
    for name in archive.namelist():
        if not name.endswith('.npy') or '/' in name:
            raise ValueError('unexpected NPZ member ' + name)
        with archive.open(name) as stream:
            if stream.read(6) != b'\x93NUMPY':
                raise ValueError('invalid NPY magic')
            version = tuple(stream.read(2))
            width = 2 if version == (1, 0) else 4
            length = struct.unpack('<H' if width == 2 else '<I', stream.read(width))[0]
            header = ast.literal_eval(stream.read(length).decode('utf-8').strip())
            key = name[:-4]
            dtype = header['descr']
            shape = list(header['shape'])
            if not isinstance(dtype, str) or 'O' in dtype:
                raise ValueError('object/structured dtype not supported')
            data_hash = hashlib.sha256()
            identity_hash = hashlib.sha256()
            identity_hash.update(dtype.encode('ascii'))
            identity_hash.update(json.dumps(shape).encode('ascii'))
            count = 0
            record_bytes = bytearray() if key == '__task43_record_json__' else None
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                count += len(chunk)
                data_hash.update(chunk)
                identity_hash.update(chunk)
                if record_bytes is not None:
                    record_bytes.extend(chunk)
            if record_bytes is not None:
                if dtype != '|u1':
                    raise ValueError('embedded metadata must be uint8')
                embedded = json.loads(record_bytes)
            else:
                identity = {'dtype': dtype, 'shape': shape, 'sha256': identity_hash.hexdigest()}
                members[key] = {'identity': identity, 'payload_bytes': count,
                                'payload_sha256': data_hash.hexdigest(),
                                'fortran_order': header['fortran_order']}
                if header['fortran_order'] and len(shape) > 1:
                    issues.append([key, 'FORTRAN_ORDER_REQUIRES_SEPARATE_C_ORDER_BINDING'])
if embedded is None:
    raise ValueError('embedded identity missing')
if set(members) != set(embedded['arrays']):
    issues.append('array inventory mismatch')
for key, value in members.items():
    if value['identity'] != embedded['arrays'].get(key):
        issues.append([key, 'array identity mismatch'])
with path.open('rb') as stream:
    file_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
result = {'method': 'stdlib ZIP/NPY header and raw byte hashes only; no NumPy, project import, norm, operator, field restoration or sampling',
          'path': str(path.resolve()), 'sha256': file_hash,
          'members': members, 'embedded_record': embedded, 'issues': issues,
          'elapsed_seconds': time.monotonic() - start}
with target.open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps({'members': len(members), 'issues': issues,
                  'sha256': file_hash, 'elapsed_seconds': result['elapsed_seconds']}))
