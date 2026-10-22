#!/usr/bin/env python3
"""Verify and reconstruct archives only. Never execute archived commands.

Usage: python restore_archive.py /path/to/new-empty-output-directory
Run from a checked-out copy of this archive directory, with parts/ present.
The first bundle contains content-addressed blobs plus original-path inventory;
the second contains labeled source snapshots, final fields and worker exports.
"""
import hashlib,json,sys,tarfile
from pathlib import Path

here=Path(__file__).resolve().parent
dest=Path(sys.argv[1]).resolve()
if dest.exists():
    raise SystemExit('Refusing an existing destination; choose a new empty path.')
manifest=json.loads((here/'multipart_manifest.json').read_text())
dest.mkdir(parents=True)
for bundle in manifest['bundles']:
    out=dest/bundle['file']
    with out.open('xb') as f:
        for part in bundle['parts']:
            data=(here/'parts'/part['file']).read_bytes()
            assert len(data)==part['bytes']
            assert hashlib.sha256(data).hexdigest()==part['sha256']
            f.write(data)
    assert out.stat().st_size==bundle['bytes']
    assert hashlib.sha256(out.read_bytes()).hexdigest()==bundle['sha256']
    unpack=dest/(bundle['file']+'.contents');unpack.mkdir()
    with tarfile.open(out,'r:*') as archive:
        for member in archive:
            if not member.isfile() or Path(member.name).is_absolute() or '..' in Path(member.name).parts:
                raise ValueError('Unsafe archive member: '+member.name)
            target=unpack/member.name
            target.parent.mkdir(parents=True,exist_ok=True)
            data=archive.extractfile(member).read()
            if member.name.startswith('blobs/'):
                assert hashlib.sha256(data).hexdigest()==member.name.split('/')[1]
            with target.open('xb') as f:f.write(data)
    print('Verified and extracted',bundle['file'])
print('No commands executed. Restore selected original paths manually using inventory.json; do not overwrite live locks/fences.')
