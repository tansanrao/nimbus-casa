#!/usr/bin/env python3
"""Live isolation checks. Default is read-only; optional flags exercise network failure paths.

Requires kubectl and curl/bash/timeout in the existing media application images.
Run only during an authorized maintenance window when exercising outages.
"""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import time

args = argparse.ArgumentParser()
args.add_argument('--exercise-outages', action='store_true')
args.add_argument('--exercise-underlay', action='store_true')
args.add_argument('--output', type=Path)
options = args.parse_args()
results = []


def kubectl(*cmd, **kw):
    return subprocess.run(['kubectl', *cmd], capture_output=True, text=True, **kw)


def get(kind, name, ns):
    r = kubectl('get', kind, name, '-n', ns, '-o', 'json')
    r.check_returncode()
    return json.loads(r.stdout)


def pod(app, ns='media'):
    r = kubectl('get', 'pods', '-n', ns, '-l', 'app.kubernetes.io/name=' + app, '-o', 'json')
    r.check_returncode()
    choices = [p for p in json.loads(r.stdout)['items']
               if not p['metadata'].get('deletionTimestamp') and p['status']['phase'] == 'Running']
    assert len(choices) == 1, f'{ns}/{app}: expected one running pod'
    return choices[0]


radarr = pod('radarr')['metadata']['name']
qb = pod('qbittorrent')['metadata']['name']


def execute(name, *cmd):
    return kubectl('exec', '-n', 'media', name, '-c', 'app', '--', *cmd, timeout=20)


def record(name, passed, detail=''):
    results.append({'test': name, 'passed': bool(passed), 'detail': detail})
    print(('PASS ' if passed else 'FAIL ') + name + (': ' + detail if detail else ''), flush=True)


def tcp(name, target, port, allowed, stage='baseline', source=qb):
    r = execute(source, 'timeout', '4', 'bash', '-c', 'exec 3<>/dev/tcp/$1/$2', 'bash', target, str(port))
    # A blocked test must reach the command, not fail because kubectl lost the pod.
    valid = r.returncode in (0, 1, 124)
    record(stage + ': ' + name, valid and ((r.returncode == 0) == allowed), 'exit=' + str(r.returncode))


def public(stage, allowed):
    r = execute(qb, 'curl', '--connect-timeout', '3', '--max-time', '6', '-fsS', 'https://am.i.mullvad.net/json')
    if allowed:
        try:
            data = json.loads(r.stdout)
            passed = r.returncode == 0 and data.get('mullvad_exit_ip') is True
        except ValueError:
            passed = False
    else:
        passed = r.returncode in (5, 6, 7, 28, 35, 52, 56)
    record(stage + ': public egress ' + ('via Mullvad' if allowed else 'blocked'), passed,
           'curl exit=' + str(r.returncode))
    return passed


def local(stage):
    tcp('Arr to downloader', 'qbittorrent.media.svc.cluster.local.', 8080, True, stage, radarr)
    tcp('Arr to database', 'media16-primary.media-database.svc.cluster.local.', 5432, True, stage, radarr)
    tcp('Arr to indexer', 'prowlarr.media.svc.cluster.local.', 80, True, stage, radarr)
    r = execute(qb, 'sh', '-c', 'test -r /mediastore && test -w /mediastore && stat /mediastore >/dev/null')
    record(stage + ': mounted NFS accessible', r.returncode == 0)
    r = subprocess.run(['curl', '--max-time', '8', '-fsS', 'https://radarr.nimbus.casa/ping'], capture_output=True, text=True)
    record(stage + ': home UI through ingress', r.returncode == 0 and 'OK' in r.stdout)


public('baseline', True)
local('baseline')
immich_server = get('service', 'immich-server', 'immich')['spec']['clusterIP']
immich_cache = get('service', 'immich-cache', 'immich')['spec']['clusterIP']
r = kubectl('get', 'pods', '-n', 'immich', '-l', 'postgres-operator.crunchydata.com/role=master', '-o', 'json')
r.check_returncode()
immich_db = json.loads(r.stdout)['items'][0]['status']['podIP']
for name, target, port in [('Immich server', immich_server, 2283), ('Immich cache', immich_cache, 6379),
                           ('Immich database pod', immich_db, 5432), ('API service', '10.43.0.1', 443),
                           ('node API', '10.10.40.40', 6443), ('NAS network service', '10.10.40.10', 2049)]:
    tcp(name + ' denied', target, port, False)

if options.exercise_underlay:
    # Force one public address onto the pod underlay, then remove that temporary route.
    try:
        r = kubectl('exec', '-n', 'media', qb, '-c', 'gateway-sidecar', '--',
                    'ip', 'route', 'add', '1.1.1.1/32', 'via', '10.42.0.95')
        r.check_returncode()
        tcp('direct underlay internet denied', '1.1.1.1', 443, False)
    finally:
        kubectl('exec', '-n', 'media', qb, '-c', 'gateway-sidecar', '--', 'ip', 'route', 'del', '1.1.1.1/32')

if options.exercise_outages:
    deny = {'apiVersion': 'cilium.io/v2', 'kind': 'CiliumNetworkPolicy',
            'metadata': {'name': 'isolation-outage-test', 'namespace': 'media-vpn'},
            'spec': {'endpointSelector': {'matchLabels': {'app.kubernetes.io/name': 'pod-gateway',
                                                         'app.kubernetes.io/controller': 'main'}},
                     'egressDeny': [{'toCIDR': ['185.156.46.130/32', '185.156.46.143/32', '185.156.46.156/32']}]}}
    assert kubectl('get', 'ciliumnetworkpolicy', 'isolation-outage-test', '-n', 'media-vpn').returncode != 0
    try:
        r = kubectl('create', '-f', '-', input=json.dumps(deny))
        r.check_returncode()
        time.sleep(4)
        public('relay outage', False)
        local('relay outage')
    finally:
        kubectl('delete', 'ciliumnetworkpolicy', 'isolation-outage-test', '-n', 'media-vpn', '--ignore-not-found').check_returncode()
    gateway = get('deployment', 'media-vpn-main', 'media-vpn')
    replicas = gateway['spec']['replicas']
    try:
        kubectl('scale', 'deployment', 'media-vpn-main', '-n', 'media-vpn', '--replicas=0').check_returncode()
        kubectl('wait', 'pod', '-n', 'media-vpn', '-l', 'app.kubernetes.io/controller=main',
                '--for=delete', '--timeout=45s').check_returncode()
        public('gateway stopped', False)
        local('gateway stopped')
    finally:
        kubectl('scale', 'deployment', 'media-vpn-main', '-n', 'media-vpn', '--replicas=' + str(replicas)).check_returncode()
    kubectl('rollout', 'status', 'deployment/media-vpn-main', '-n', 'media-vpn', '--timeout=60s').check_returncode()
    for attempt in range(12):
        r = execute(qb, 'curl', '--max-time', '4', '-fsS', 'https://am.i.mullvad.net/json')
        if r.returncode == 0:
            break
        time.sleep(3)
    public('recovered', True)
    local('recovered')

report = {'time': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'results': results}
if options.output:
    options.output.write_text(json.dumps(report, indent=2) + '\n')
assert all(r['passed'] for r in results), 'One or more isolation checks failed'
print(f'All {len(results)} checks passed.', flush=True)
