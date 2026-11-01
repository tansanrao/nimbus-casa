#!/usr/bin/env python3
"""Check active PostgreSQL image pins; --live also checks versions and backups.

Cluster names retain their historical '16' suffix to preserve services, Secrets,
PVCs and backup paths. The quarantined legacy database/immich16 is excluded.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--live', action='store_true')
args = parser.parse_args()


def run(*command):
    return subprocess.check_output(command, text=True)


def get(kind, namespace, *options):
    return json.loads(run('kubectl', 'get', kind, '-n', namespace, *options, '-o', 'json'))


clusters = [
    ('database', 'postgres16', 'database/crunchy-postgres/clusters/app/postgres16.yaml'),
    ('media-database', 'media16', 'media-database/postgres/app/cluster.yaml'),
    ('immich', 'immich16', 'immich/database/app/cluster.yaml'),
]
for namespace, name, relative in clusters:
    manifest = json.loads(run('yq', '-o=json', '.', str(ROOT / 'kubernetes/apps' / relative)))
    spec = manifest['spec']
    assert spec['postgresVersion'] == 18
    match = re.search(r':ubi9-(18\.\d+)-[^@]+@(sha256:[a-f0-9]{64})$', spec['image'])
    assert match, f'{namespace}/{name}: expected PostgreSQL 18 tag and digest'
    assert not any('crunchy-userinit' in key for key in spec.get('metadata', {}).get('labels', {}))
    print(f'PASS {namespace}/{name}: pinned PostgreSQL {match[1]}')
    if not args.live:
        continue
    live = get('postgrescluster', namespace, name)
    assert live['spec']['image'] == spec['image'] and live['spec']['postgresVersion'] == 18
    selector = f'postgres-operator.crunchydata.com/cluster={name},postgres-operator.crunchydata.com/role=master'
    pods = get('pods', namespace, '-l', selector)['items']
    assert len(pods) == 1
    pod = pods[0]
    status = next(c for c in pod['status']['containerStatuses'] if c['name'] == 'database')
    assert status['ready'] and status['imageID'].endswith('@' + match[2])
    command = ['kubectl', 'exec', '-n', namespace, pod['metadata']['name']]
    version = run(*command, '-c', 'database', '--', 'psql', '-XAt', '-c', 'show server_version').strip()
    assert version == match[1]
    for repo in (1, 2):
        info = json.loads(run(*command, '-c', 'pgbackrest', '--', 'pgbackrest', f'--repo={repo}', '--output=json', 'info'))[0]
        assert info['status']['code'] == 0
        current_ids = {db['id'] for db in info['db'] if db['version'] == '18'}
        assert any(b['type'] == 'full' and b['database']['id'] in current_ids for b in info['backup'])
    print(f'PASS {namespace}/{name}: running digest/version and full PG18 backups in both repositories')

if args.live:
    for kind in ('deployments', 'serviceaccounts', 'roles', 'rolebindings', 'clusterroles', 'clusterrolebindings'):
        objects = get(kind, 'database')['items']
        assert not any('crunchy-userinit' in obj['metadata']['name'] for obj in objects)
    print('PASS user-init controller and RBAC removed')
