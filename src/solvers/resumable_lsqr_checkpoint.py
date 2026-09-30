"""Two-generation numerical checkpoints, committed only after fsync/hash.

The store owns small recurrence/state arrays, never Q/U/R. An interrupted
new generation leaves the other committed slot usable. Identity is mandatory.
"""
import json
import os
from pathlib import Path
import time

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers.neural_fe_action_packet import file_hash


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


class RollingCheckpoint:
    schema = 'task042.gk-rolling.v17'

    def __init__(self, directory, identity):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.identity = identity

    def read(self):
        valid, errors = [], []
        for slot in range(2):
            prefix = self.directory / ('slot'+str(slot))
            try:
                commit = json.loads(prefix.with_suffix('.commit.json').read_text())
                manifest_path = prefix.with_suffix('.json')
                if file_hash(manifest_path) != commit['manifest_sha256']:
                    raise ValueError('manifest hash differs')
                manifest = json.loads(manifest_path.read_text())
                if (manifest['schema'] != self.schema or manifest['identity'] != self.identity
                        or manifest['generation'] != commit['generation']):
                    raise ValueError('checkpoint identity/schema/generation differs')
                path = prefix.with_suffix('.npz')
                if file_hash(path) != manifest['arrays_sha256']:
                    raise ValueError('array hash differs')
                with np.load(path, allow_pickle=False) as stream:
                    arrays = {k: np.array(stream[k]) for k in stream.files}
                if any(not np.isfinite(v).all() for v in arrays.values()):
                    raise ValueError('nonfinite checkpoint')
                valid.append((manifest, arrays))
            except (OSError,ValueError,KeyError,json.JSONDecodeError) as error:
                errors.append(dict(slot=slot,error=str(error)))
        if not valid:
            raise ValueError('no legal generation: '+str(errors))
        manifest, arrays = max(valid,key=lambda item:item[0]['generation'])
        return manifest, arrays, errors

    def save(self, arrays, metadata, *, interrupt_after=None):
        began = time.perf_counter()
        generations = []
        for path in self.directory.glob('slot*.commit.json'):
            try: generations.append(int(json.loads(path.read_text())['generation']))
            except (OSError,ValueError,KeyError): pass
        generation = max(generations,default=-1)+1
        prefix = self.directory/('slot'+str(generation%2))
        tmp = prefix.with_suffix('.npz.partial')
        with tmp.open('wb') as stream:
            np.savez(stream,**arrays);stream.flush();os.fsync(stream.fileno())
        if interrupt_after == 'arrays_partial': return None
        os.replace(tmp,prefix.with_suffix('.npz'));sync_directory(self.directory)
        if interrupt_after == 'arrays': return None
        record = dict(schema=self.schema,generation=generation,identity=self.identity,
                      arrays_sha256=file_hash(prefix.with_suffix('.npz')),metadata=metadata,
                      arrays_bytes=prefix.with_suffix('.npz').stat().st_size,
                      write_seconds_before_manifest=time.perf_counter()-began)
        write_json(prefix.with_suffix('.json'),record);sync_directory(self.directory)
        if interrupt_after == 'manifest': return None
        write_json(prefix.with_suffix('.commit.json'),dict(generation=generation,
                   manifest_sha256=file_hash(prefix.with_suffix('.json'))))
        sync_directory(self.directory)
        return dict(generation=generation,path=str(prefix.with_suffix('.npz')),
                    sha256=record['arrays_sha256'],bytes=record['arrays_bytes'],
                    write_seconds=time.perf_counter()-began)
