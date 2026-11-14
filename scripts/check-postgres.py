#!/usr/bin/env python3
"""Check CloudNativePG cluster pins and backups; --live also checks the running clusters.

Every postgresql.cnpg.io Cluster under kubernetes/apps must pin a PostgreSQL 18
image by digest, bootstrap with en_US.UTF-8 (the collation the data was migrated
with), and archive WAL through the Barman Cloud plugin to an ObjectStore of the
same name. --live checks the running image and version, WAL archiving, and that
the last base backup is less than 26 hours old.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = 'barman-cloud.cloudnative-pg.io'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--live', action='store_true')
args = parser.parse_args()


def run(*command):
    return subprocess.check_output(command, text=True)


def get(kind, namespace, *options):
    return json.loads(run('kubectl', 'get', kind, '-n', namespace, *options, '-o', 'json'))


def namespace_of(path):
    """The Flux Kustomization next to app/ sets targetNamespace."""
    ks = json.loads(run('yq', '-o=json', 'select(.kind == "Kustomization")', str(path.parent.parent / 'ks.yaml')))
    return ks['spec']['targetNamespace']


clusters = []
for path in sorted((ROOT / 'kubernetes/apps').rglob('*.yaml')):
    if 'postgresql.cnpg.io' not in path.read_text():
        continue
    docs = run('yq', '-o=json', '-I=0', 'select(.kind == "Cluster" and .apiVersion == "postgresql.cnpg.io/v1")', str(path)).splitlines()
    clusters += [(path, json.loads(doc)) for doc in docs if doc.strip()]
assert clusters, 'no CloudNativePG clusters found'

for path, manifest in clusters:
    name, spec = manifest['metadata']['name'], manifest['spec']
    namespace = namespace_of(path)
    match = re.search(r':(18\.\d+)[^@]*@(sha256:[a-f0-9]{64})$', spec['imageName'])
    if not match:
        match = re.search(r':18-v[\d.]+@(sha256:[a-f0-9]{64})$', spec['imageName'])
    assert match, f'{namespace}/{name}: expected a PostgreSQL 18 tag pinned by digest'
    initdb = spec['bootstrap']['initdb']
    assert initdb.get('localeCollate') == initdb.get('localeCType') == 'en_US.UTF-8', f'{namespace}/{name}: collation'
    archiver = [p for p in spec.get('plugins', []) if p['name'] == PLUGIN and p.get('isWALArchiver')]
    assert len(archiver) == 1 and archiver[0]['parameters']['barmanObjectName'] == name, f'{namespace}/{name}: WAL archiving'
    print(f'PASS {namespace}/{name}: pinned {spec["imageName"].split("@")[0]}, en_US.UTF-8, WAL to ObjectStore {name}')
    if not args.live:
        continue
    live = get('cluster.postgresql.cnpg.io', namespace, name)
    status = live['status']
    assert live['spec']['imageName'] == spec['imageName'] and status.get('phase') == 'Cluster in healthy state', f'{namespace}/{name}: {status.get("phase")}'
    conditions = {c['type']: c['status'] for c in status.get('conditions', [])}
    assert conditions.get('ContinuousArchiving') == 'True', f'{namespace}/{name}: WAL archiving is failing'
    pod = status['currentPrimary']
    container = next(c for c in get('pod', namespace, pod)['status']['containerStatuses'] if c['name'] == 'postgres')
    assert container['ready'] and container['imageID'].endswith('@' + spec['imageName'].split('@')[1])
    version = run('kubectl', 'exec', '-n', namespace, pod, '-c', 'postgres', '--', 'psql', '-XAt', '-c', 'show server_version_num').strip()
    assert version.startswith('18'), f'{namespace}/{name}: server_version_num {version}'
    store = get('objectstore.barmancloud.cnpg.io', namespace, name)
    last = store.get('status', {}).get('serverRecoveryWindow', {}).get(name, {}).get('lastSuccessfulBackupTime')
    assert last, f'{namespace}/{name}: no completed base backup'
    age = datetime.now(timezone.utc) - datetime.fromisoformat(last.replace('Z', '+00:00'))
    assert age < timedelta(hours=26), f'{namespace}/{name}: last base backup is {age} old'
    print(f'PASS {namespace}/{name}: healthy, running pinned digest, WAL archiving, base backup {age.total_seconds() / 3600:.1f}h old')
