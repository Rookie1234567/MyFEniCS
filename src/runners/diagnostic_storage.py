"""One stat-only, deduplicated storage scope for the fixed return campaign.

The same function is used by preflight, live guards and the delivery inventory.
It reads no array or factor payload and does not remove historical evidence.
"""
import re
import shutil
from pathlib import Path

NEW_LIMIT = 32 * 2**20
CUMULATIVE_LIMIT = 128 * 2**20
TASK_ARTIFACT_LIMIT = 20 * 2**30
FREE_MINIMUM = 50 * 2**30


def scope_paths(root, *, batch=32):
    root = Path(root).resolve()
    if batch != 32:
        raise ValueError('storage scope is explicitly V32')
    tmp = root / 'tmp/task042'
    artifact = root / 'benchmarks/artifacts/task042'
    results = root / 'results/task042'
    records = root / 'docs/task042_neural_coarse_inverse/outcomes/records'
    cumulative = []
    new = []
    for parent, pattern in ((tmp, r'v(\d+)(?:_|$)'),
                            (artifact, r'v(\d+)$'),
                            (results, r'task042_v(\d+)(?:_|$)')):
        for p in parent.glob('*'):
            match = re.match(pattern, p.name)
            if match and 27 <= int(match[1]) <= batch:
                cumulative.append(p)
                if int(match[1]) == batch:
                    new.append(p)
    # Review temporary data were included in the declared historical inventory.
    cumulative.extend(p for p in tmp.glob('review_v*')
                      if (m := re.match(r'review_v(\d+)(?:_|$)', p.name))
                      and 24 <= int(m[1]) <= 29)
    for p in records.glob('*'):
        match = re.search(r'(?:^|_)v(\d+)(?:[_.]|$)', p.name)
        if not match:
            continue
        version = int(match[1])
        if 27 <= version <= batch or (p.name.startswith('review_v') and 24 <= version <= 29):
            cumulative.append(p)
        if version == batch:
            new.append(p)
    return dict(new=new, cumulative=cumulative, task_artifact=[artifact])


def inventory_paths(paths, root):
    """Normalize filenames before deduplication, including overlapping roots."""
    root = Path(root).resolve()
    files = {}
    for entry in paths:
        entry = Path(entry)
        candidates = entry.rglob('*') if entry.is_dir() else (entry,)
        for p in candidates:
            if not p.is_file():
                continue
            canonical = p.resolve()
            if not canonical.is_relative_to(root):
                raise ValueError('storage scope escapes canonical worktree')
            files[str(canonical.relative_to(root))] = canonical.stat().st_size
    return dict(bytes=sum(files.values()), file_count=len(files),
                files=files, deduplication='normalized absolute filename')


def inventory(root, *, batch=32, include_files=False):
    paths = scope_paths(root, batch=batch)
    result = {key: inventory_paths(value, root) for key, value in paths.items()}
    if not include_files:
        for value in result.values():
            value.pop('files')
    result.update(scope_roots={key: sorted(str(p) for p in value) for key, value in paths.items()},
                  free_bytes=shutil.disk_usage(root).free,
                  limits=dict(new=NEW_LIMIT, cumulative=CUMULATIVE_LIMIT,
                              task_artifact=TASK_ARTIFACT_LIMIT, free_minimum=FREE_MINIMUM),
                  stat_only=True)
    return result


def enforce(root, *, reserve_bytes=0):
    result = inventory(root)
    for key, limit in (('new', NEW_LIMIT), ('cumulative', CUMULATIVE_LIMIT),
                       ('task_artifact', TASK_ARTIFACT_LIMIT)):
        if result[key]['bytes'] + reserve_bytes > limit:
            raise MemoryError('V32 ' + key + ' storage cap / reserved output')
    if result['free_bytes'] < FREE_MINIMUM + reserve_bytes:
        raise MemoryError('V32 disk free-space gate')
    return result
