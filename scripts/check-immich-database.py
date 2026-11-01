#!/usr/bin/env python3
"""Read-only checks for the pinned Immich database image, extensions, and Renovate.

--live checks the running database and both search indexes without reading photos
or returning personal records. --renovate-log accepts a Renovate lookup dry run.
Extension upgrades require an isolated restore rehearsal and index rebuilds;
rolling the image back alone is unsafe after a VectorChord format upgrade.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--live', action='store_true')
p.add_argument('--renovate-log', type=Path)
a = p.parse_args()
path = ROOT / 'kubernetes/apps/immich/database/app/cluster.yaml'
def run(*cmd):
    return subprocess.check_output(cmd, text=True)
cluster = json.loads(run('yq', '-o=json', '.', str(path)))
image = cluster['spec']['image']
m = re.fullmatch(r'ghcr.io/aaronspruit/crunchy-postgres-vectorchord:ubi9-(16\.\d+)-\d+-(\d+\.\d+\.\d+)@(sha256:[a-f0-9]{64})', image)
assert m, 'Expected reviewed publisher, PostgreSQL 16, composite release tag and digest'
assert cluster['spec']['postgresVersion'] == 16
print('PASS pinned PostgreSQL 16 image')
if a.renovate_log:
    text = a.renovate_log.read_text()
    marker = text.index('DEBUG: packageFiles with updates')
    config = json.JSONDecoder().raw_decode(text[text.index('{', marker):])[0]
    deps = [d for files in config.values() for f in files if f['packageFile'] == str(path.relative_to(ROOT)) for d in f['deps'] if d['depName'] == image.split(':')[0]]
    assert len(deps) == 1, 'Expected exactly one extracted database dependency'
    d = deps[0]
    assert not d.get('warnings') and not d.get('skipReason')
    assert d['currentValue'] == image.split(':')[1].split('@')[0] and d['currentDigest'] == m[3]
    print('PASS Renovate extracts release and digest and resolves the registry')
if a.live:
    def get(kind, *args):return json.loads(run('kubectl', 'get', kind, *args, '-n', 'immich', '-o', 'json'))
    assert get('postgrescluster', 'immich16')['spec']['image'] == image
    pods = get('pods', '-l', 'postgres-operator.crunchydata.com/cluster=immich16,postgres-operator.crunchydata.com/role=master')['items']
    assert len(pods) == 1
    pod = pods[0]
    db = next(c for c in pod['spec']['containers'] if c['name'] == 'database')
    status = next(c for c in pod['status']['containerStatuses'] if c['name'] == 'database')
    assert db['image'] == image and status['ready'] and status['imageID'].endswith('@'+m[3])
    print('PASS running database matches the pinned digest')
    sql = "SELECT current_setting('server_version'); SELECT extversion FROM pg_extension WHERE extname='vchord'; SELECT bool_and(indisvalid AND indisready) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE c.relname IN ('face_index','clip_index'); SELECT count(*) FROM pg_class WHERE relname IN ('face_index','clip_index');"
    lines = run('kubectl','exec', '-n','immich',pod['metadata']['name'],'-c','database','--','psql','-U','postgres','-d','immich','-XAt','-v','ON_ERROR_STOP=1','-c',sql).splitlines()
    assert lines == [m[1],m[2],'t','2'], lines
    print('PASS PostgreSQL/VectorChord versions and both valid search indexes')
