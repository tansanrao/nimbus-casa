#!/usr/bin/env python3
"""Verify restricted admission, token mounts, namespace RBAC, and live network paths.

Creates temporary unprivileged probe Jobs without credentials; always deletes them.
Probe labels select the same Cilium rules as each application. Existing application
health, storage bindings, and public routes are checked separately by Kubernetes.
"""
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

APPS = ('authentik', 'karakeep', 'mealie', 'miniflux')
NAME = 'application-isolation-check'

def kube(*args, **kwargs):
    return subprocess.run(['kubectl', *args], text=True, capture_output=True, timeout=65, **kwargs)

def get(kind, *args):
    r = kube('get', kind, *args, '-o', 'json')
    r.check_returncode()
    return json.loads(r.stdout)

def check(name, ok):
    print(('PASS ' if ok else 'FAIL ') + name, flush=True)
    if not ok:
        raise AssertionError(name)

image = get('deployment', 'mealie', '-n', 'mealie')['spec']['template']['spec']['containers'][0]['image']
pg = get('pods', '-n', 'database', '-l', 'postgres-operator.crunchydata.com/cluster=postgres16,postgres-operator.crunchydata.com/role=master')['items'][0]['status']['podIP']

def svc(ns, name):
    return get('service', name, '-n', ns)['spec']['clusterIP']

api = svc('default', 'kubernetes')
immich = svc('immich', 'immich-server')
sonarr = svc('media', 'sonarr')
app_ips = {a: svc(a, 'authentik-server' if a == 'authentik' else a) for a in APPS}
ports = {'authentik': 80, 'karakeep': 3000, 'mealie': 9000, 'miniflux': 80}
extras = {
    'authentik': [(svc('database', 'dragonfly'), 6379), (svc('default', 'smtp-relay'), 25)],
    'mealie': [(svc('default', 'smtp-relay'), 25)],
    'karakeep': [(svc('karakeep-browser', 'karakeep-browser'), 9222), (svc('database', 'meilisearch-karakeep'), 7700)],
    'miniflux': [],
}
code = '''import json,socket,urllib.request
results=[]
for host,port,expected in TARGETS:
 try:
  with socket.create_connection((host,port),timeout=2): reachable=True
 except OSError: reachable=False
 results.append(reachable == expected)
 print(json.dumps({'host':host,'port':port,'expected':expected,'reachable':reachable}),flush=True)
for url in ['https://example.com','https://auth.nimbus.casa/if/flow/default-authentication-flow/']:
 with urllib.request.urlopen(url,timeout=15) as r:
  assert r.status == 200
 print('HTTPS allowed: '+url,flush=True)
assert all(results), 'network expectations failed'
'''

def probe(app):
    ns = get('namespace', app)
    check(app + ' enforces restricted v1.37', ns['metadata']['labels']['pod-security.kubernetes.io/enforce'] == 'restricted' and ns['metadata']['labels']['pod-security.kubernetes.io/enforce-version'] == 'v1.37')
    policy = get('networkpolicy', 'default-deny', '-n', app)['spec']
    check(app + ' defaults to deny in both directions', policy['podSelector'] == {} and set(policy['policyTypes']) == {'Ingress', 'Egress'} and not policy.get('ingress') and not policy.get('egress'))
    bad = {'apiVersion':'v1','kind':'Pod','metadata':{'name':NAME+'-rejected','namespace':app},'spec':{'containers':[{'name':'bad','image':image,'securityContext':{'privileged':True}}]}}
    r = kube('create', '--dry-run=server', '-f', '-', input=json.dumps(bad))
    check(app + ' rejects privileged pods', r.returncode != 0 and 'violates PodSecurity' in r.stderr)
    for p in get('pods', '-n', app)['items']:
        if p['metadata'].get('deletionTimestamp') or p['status']['phase'] != 'Running':
            continue
        spec = p['spec']
        worker = app == 'authentik' and p['metadata']['labels'].get('app.kubernetes.io/component') == 'worker'
        if not worker:
            check(app + '/' + p['metadata']['name'] + ' has no API token', spec.get('automountServiceAccountToken') is False and not any(s.get('serviceAccountToken') for v in spec.get('volumes', []) for s in v.get('projected', {}).get('sources', [])))
    targets = [(pg,5432,True)] + [(h,p,True) for h,p in extras[app]]
    targets += [(api,443,False), ('10.10.40.40',6443,False), ('10.10.40.10',2049,False), (immich,2283,False), (sonarr,8989,False)]
    targets += [(app_ips[a],ports[a],False) for a in APPS if a != app]
    labels = {'app.kubernetes.io/name':app,'app.kubernetes.io/controller':'karakeep' if app == 'karakeep' else 'main'}
    if app == 'authentik':
        labels['app.kubernetes.io/component'] = 'server'
    podspec = {'restartPolicy':'Never','automountServiceAccountToken':False,'securityContext':{'runAsUser':1001,'runAsGroup':1001,'runAsNonRoot':True,'seccompProfile':{'type':'RuntimeDefault'}},'containers':[{'name':'check','image':image,'command':['python3','-c',code.replace('TARGETS',repr(targets))],'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},'resources':{'limits':{'memory':'128Mi'}}}]}
    job = {'apiVersion':'batch/v1','kind':'Job','metadata':{'name':NAME,'namespace':app},'spec':{'backoffLimit':0,'activeDeadlineSeconds':60,'ttlSecondsAfterFinished':300,'template':{'metadata':{'labels':labels},'spec':podspec}}}
    try:
        kube('create','-f','-',input=json.dumps(job)).check_returncode()
        r = kube('wait','job/'+NAME,'-n',app,'--for=condition=Complete','--timeout=60s')
        logs = kube('logs','job/'+NAME,'-n',app)
        print(app + ':\n' + logs.stdout,flush=True)
        check(app + ' allowed dependencies and blocked lateral access', r.returncode == 0)
    finally:
        kube('delete','job',NAME,'-n',app,'--ignore-not-found','--wait=true').check_returncode()

with ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(probe, APPS))
identity = 'system:serviceaccount:authentik:authentik'
for namespace, allowed in [('authentik', True), ('default', False), ('immich', False), ('database', False)]:
    r = kube('auth','can-i','create','deployments','-n',namespace,'--as='+identity)
    check('Authentik worker deployment permission in '+namespace, (r.stdout.strip() == 'yes') == allowed)
print('Application namespace isolation checks passed')
