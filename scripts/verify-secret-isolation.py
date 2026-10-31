#!/usr/bin/env python3
"""Read-only live checks plus server dry-run rejection tests; never reads Secret data.

Run after deploying the access policy. Requires kubectl and yq. New consumers
must be reviewed in access/app/contracts.yaml and the matching admission CEL.
"""
import copy
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
results = []
def kube(*args, **kwargs):
    return subprocess.run(['kubectl', *args], text=True, capture_output=True, timeout=30, **kwargs)
def record(name, ok):
    results.append(bool(ok))
    print(('PASS ' if ok else 'FAIL ') + name, flush=True)
def get(kind, *args):
    r = kube('get', kind, *args, '-o', 'json')
    r.check_returncode()
    return json.loads(r.stdout)
def dry(obj):
    return kube('apply', '--server-side', '--field-manager=kustomize-controller', '--dry-run=server', '-f', '-', input=json.dumps(obj))

contracts = json.loads(json.loads(subprocess.check_output(['yq', '-o=json', '.', str(ROOT / 'kubernetes/apps/external-secrets/access/app/contracts.yaml')]))['data']['contracts.json'])
policy = get('validatingadmissionpolicy', 'external-secret-contracts')
inline = json.loads(policy['spec']['variables'][0]['expression'])
for c in inline:
    c['keys'] = c['keys'].split('|')
record('policy matches reviewed contract inventory', inline == contracts)
for name in ['external-secret-contracts', 'secret-provider-administration']:
    p = get('validatingadmissionpolicy', name)
    record(name + ' compiled', p.get('status', {}).get('observedGeneration') == p['metadata']['generation'] and not p.get('status', {}).get('typeChecking', {}).get('expressionWarnings'))
    b = get('validatingadmissionpolicybinding', name)
    record(name + ' enforced', b['spec']['validationActions'] == ['Deny'])
live = get('externalsecrets', '-A')['items']
by_name = {(x['metadata']['namespace'], x['metadata']['name']): x for x in live}
record('no unreviewed or stale sync resources', set(by_name) == {(c['namespace'], c['name']) for c in contracts})
for c in contracts:
    key = c['namespace'], c['name']
    x = by_name.get(key)
    record('/'.join(key) + ' Ready', x is not None and any(z['type'] == 'Ready' and z['status'] == 'True' for z in x.get('status', {}).get('conditions', [])))
    if x:
        obj = {'apiVersion': x['apiVersion'], 'kind': x['kind'], 'metadata': {'namespace': key[0], 'name': key[1]}, 'spec': x['spec']}
        record('/'.join(key) + ' admitted', dry(obj).returncode == 0)
base = by_name['media', 'radarr-secret']
base = {'apiVersion': base['apiVersion'], 'kind': base['kind'], 'metadata': {'namespace': 'media', 'name': 'radarr-secret'}, 'spec': base['spec']}
cases = []
def case(name, fn):
    x = copy.deepcopy(base)
    fn(x)
    cases.append((name, x))
case('Immich item extraction', lambda x: x['spec'].update(dataFrom=[{'extract': {'key': 'immich'}}]))
case('infrastructure item extraction', lambda x: x['spec'].update(dataFrom=[{'extract': {'key': 'crunchy-postgres'}}]))
case('unknown ExternalSecret name', lambda x: x['metadata'].update(name='secret-isolation-negative-test'))
case('cross-namespace contract reuse', lambda x: x['metadata'].update(namespace='karakeep-browser'))
case('arbitrary destination Secret', lambda x: x['spec']['target'].update(name='stolen-credentials'))
case('alternate top-level store', lambda x: x['spec']['secretStoreRef'].update(name='crunchy-pgo-secrets'))
case('alternate store kind', lambda x: x['spec']['secretStoreRef'].update(kind='SecretStore'))
case('remoteRef cross-app key', lambda x: x['spec'].update(data=[{'secretKey':'password','remoteRef':{'key':'immich'}}]))
case('dataFrom discovery', lambda x: x['spec'].update(dataFrom=[{'find':{'name':{'regexp':'.*'}}}]))
case('dataFrom store override', lambda x: x['spec'].update(dataFrom=[{'extract':{'key':'radarr'},'sourceRef':{'storeRef':{'name':'crunchy-pgo-secrets','kind':'ClusterSecretStore'}}}]))
case('data store override', lambda x: x['spec'].update(data=[{'secretKey':'password','remoteRef':{'key':'radarr'},'sourceRef':{'storeRef':{'name':'crunchy-pgo-secrets','kind':'ClusterSecretStore'}}}]))
case('template Secret import', lambda x: x['spec']['target']['template'].update(templateFrom=[{'secret':{'name':'other-app','items':[{'key':'password'}]}}]))
for name, obj in cases:
    r = dry(obj)
    record(name + ' rejected by admission', r.returncode != 0 and 'external-secret-contracts' in r.stderr and ('denied' in r.stderr or 'failed' in r.stderr))
for ns, sa, yes, no in [
    ('database','external-secrets-pg','postgres16-pguser-authentik','immich16-pguser-postgres'),
    ('media-database','database-secret-reader','media16-pguser-radarr','crunchy-postgres-secret'),
    ('immich','database-secret-reader','immich16-pguser-immich','immich16-pguser-postgres')]:
    identity = 'system:serviceaccount:' + ns + ':' + sa
    for secret, allowed in [(yes, True), (no, False)]:
        r = kube('auth','can-i','get','secret/'+secret,'-n',ns,'--as='+identity)
        record(identity + ' GET ' + secret, (r.stdout.strip() == 'yes') == allowed)
    r = kube('auth','can-i','list','secrets','-n',ns,'--as='+identity)
    record(identity + ' cannot list secrets', r.stdout.strip() == 'no')
store = get('clustersecretstore','onepassword')
record('Connect store uses HTTPS', store['spec']['provider']['onepassword']['connectHost'] == 'https://onepassword.external-secrets.svc.cluster.local:8443')
record('Connect store limits namespaces', len(store['spec'].get('conditions',[])) == 1 and 'media' in store['spec']['conditions'][0]['namespaces'] and 'karakeep-browser' not in store['spec']['conditions'][0]['namespaces'])
record('all secret stores Ready', all(any(c['type']=='Ready' and c['status']=='True' for c in x.get('status',{}).get('conditions',[])) for kind in ['clustersecretstores','secretstores'] for x in get(kind,'-A')['items']))
print(f'{sum(results)}/{len(results)} checks passed')
raise SystemExit(0 if all(results) else 1)
