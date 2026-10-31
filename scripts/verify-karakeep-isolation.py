#!/usr/bin/env python3
"""Verify live Karakeep boundaries. Creates a temporary diagnostic Job and browser context.

No bookmarks or application data are changed. Requires kubectl and yq; run from
an authorized operator workstation. Public rendering uses https://example.com.
"""
import argparse
import json
from pathlib import Path
import subprocess
import datetime

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path)
args = parser.parse_args()
results = []


def kube(*cmd, **kwargs):
    return subprocess.run(['kubectl', *cmd], capture_output=True, text=True, timeout=60, **kwargs)


def get(kind, name, ns):
    r = kube('get', kind, name, '-n', ns, '-o', 'json')
    r.check_returncode()
    return json.loads(r.stdout)


def record(name, passed, detail=''):
    results.append({'test': name, 'passed': bool(passed), 'detail': detail})
    print(('PASS ' if passed else 'FAIL ') + name + (': ' + detail if detail else ''), flush=True)


def run(ns, deployment, *cmd, **kwargs):
    return kube('exec', '-i', '-n', ns, 'deploy/' + deployment, '-c', 'app', '--', *cmd, **kwargs)


def pod(ns, name):
    r = kube('get', 'pods', '-n', ns, '-l', 'app.kubernetes.io/name=' + name, '-o', 'json')
    r.check_returncode()
    pods = [p for p in json.loads(r.stdout)['items'] if p['status']['phase'] == 'Running' and not p['metadata'].get('deletionTimestamp')]
    assert len(pods) == 1, f'Expected one running {ns}/{name} pod'
    return pods[0]


browser = pod('karakeep-browser', 'karakeep-browser')
app = pod('default', 'karakeep')
for label, p in [('browser', browser), ('app', app)]:
    image = p['spec']['containers'][0]['image']
    record(label + ' image digest pinned', '@sha256:' in image)
    record(label + ' API token disabled', p['spec'].get('automountServiceAccountToken') is False)
record('browser has no secrets or persistent volumes', all('emptyDir' in v for v in browser['spec'].get('volumes', [])) and not browser['spec']['containers'][0].get('envFrom'))
record('browser restricted security context', browser['spec']['securityContext'].get('runAsNonRoot') is True and browser['spec']['securityContext'].get('seccompProfile', {}).get('type') == 'RuntimeDefault' and browser['spec']['containers'][0]['securityContext'] == {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}, 'readOnlyRootFilesystem': True})
r = run('karakeep-browser', 'karakeep-browser', 'sh', '-c', 'grep -E "^(CapEff|NoNewPrivs|Seccomp):" /proc/1/status; test ! -e /var/run/secrets/kubernetes.io/serviceaccount/token')
record('browser runtime privilege restrictions', r.returncode == 0 and '0000000000000000' in r.stdout and 'NoNewPrivs:\t1' in r.stdout and 'Seccomp:\t2' in r.stdout)

# Check actual browser navigation using a fresh, disposable CDP context.
cdp = r'''
import dns from 'node:dns/promises';
const endpoint=new URL(process.env.BROWSER_WEB_URL);endpoint.hostname=(await dns.lookup(endpoint.hostname)).address;
const base=endpoint.origin;
const meta=await (await fetch(base+'/json/version',{signal:AbortSignal.timeout(5000)})).json();
const u=new URL(meta.webSocketDebuggerUrl);u.host=new URL(base).host;
const ws=new WebSocket(u);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
let seq=0;const pending=new Map();
ws.onmessage=e=>{const d=JSON.parse(e.data);if(d.id&&pending.has(d.id)){const {resolve,reject,t}=pending.get(d.id);clearTimeout(t);pending.delete(d.id);d.error?reject(new Error(d.error.message)):resolve(d.result)}};
function send(method,params={},sessionId){return new Promise((resolve,reject)=>{const id=++seq;const t=setTimeout(()=>{pending.delete(id);reject(new Error(method+' timeout'))},12000);pending.set(id,{resolve,reject,t});ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}))})}
let context;
try {
 const version=await send('Browser.getVersion');console.log('Browser '+version.product);
 context=(await send('Target.createBrowserContext')).browserContextId;
 const target=(await send('Target.createTarget',{url:'about:blank',browserContextId:context})).targetId;
 const session=(await send('Target.attachToTarget',{targetId:target,flatten:true})).sessionId;
 const nav=await send('Page.navigate',{url:'https://example.com'},session);if(nav.errorText)throw new Error(nav.errorText);
 let title='';for(let i=0;i<20;i++){title=(await send('Runtime.evaluate',{expression:'document.title',returnByValue:true},session)).result.value;if(title==='Example Domain')break;await new Promise(r=>setTimeout(r,250))}
 if(title!=='Example Domain')throw new Error('Public page did not render');console.log('Rendered Example Domain');
} finally {if(context)await send('Target.disposeBrowserContext',{browserContextId:context});ws.close()}
'''
r = run('default', 'karakeep', 'node', '--input-type=module', input=cdp)
record('Karakeep controls browser and renders public HTTPS', r.returncode == 0, r.stdout.strip() if r.returncode == 0 else r.stderr[-400:])

checks = r'''
import net from 'node:net';
const db=new URL(process.env.DATABASE_URL);
await new Promise((resolve,reject)=>{const s=net.createConnection({host:db.hostname,port:Number(db.port||5432)},()=>{s.destroy();resolve()});s.setTimeout(4000,()=>{s.destroy();reject(new Error('database timeout'))});s.on('error',reject)});
for(const [name,url] of [['search',process.env.MEILI_ADDR+'/health'],['OAuth',process.env.OAUTH_WELLKNOWN_URL],['app','http://127.0.0.1:3000']]){const r=await fetch(url,{signal:AbortSignal.timeout(5000)});if(!r.ok)throw new Error(name+' HTTP '+r.status);console.log(name+' HTTP '+r.status)}
console.log('database connected');if(process.env.COREPACK_INTEGRITY_KEYS==='0')throw new Error('Corepack integrity disabled');
'''
r = run('default', 'karakeep', 'node', '--input-type=module', input=checks)
record('Karakeep database, search, OAuth and UI dependencies', r.returncode == 0, r.stdout.strip() if r.returncode == 0 else r.stderr[-400:])


def service(name, ns):
    return get('service', name, ns)['spec']['clusterIP']


pg = kube('get', 'pods', '-n', 'database', '-l', 'postgres-operator.crunchydata.com/cluster=postgres16,postgres-operator.crunchydata.com/role=master', '-o', 'json')
pg.check_returncode()
db_ip = json.loads(pg.stdout)['items'][0]['status']['podIP']
targets = [('Karakeep app', service('karakeep', 'default'), 3000),
           ('shared database pod', db_ip, 5432),
           ('search database', service('meilisearch-karakeep', 'database'), 7700),
           ('Immich server', service('immich-server', 'immich'), 2283),
           ('Immich cache', service('immich-cache', 'immich'), 6379),
           ('downloader', service('qbittorrent', 'media'), 8080),
           ('API service', '10.43.0.1', 443), ('node API', '10.10.40.40', 6443),
           ('NAS', '10.10.40.10', 2049), ('link-local metadata', '169.254.169.254', 80),
           ('direct external DNS', '1.1.1.1', 53)]
for name, host, port in targets:
    r = run('karakeep-browser', 'karakeep-browser', 'timeout', '3', 'bash', '-c', 'exec 3<>/dev/tcp/$1/$2', 'bash', host, str(port))
    blocked = r.returncode == 124 or (r.returncode == 1 and any(s in r.stderr for s in ['Connection refused', 'Network is unreachable', 'No route to host']))
    record('browser to ' + name + ' denied', blocked, 'exit=' + str(r.returncode))

# Downloads performed by the application itself must also stay out of private services.
app_targets = [(host, port) for name, host, port in targets if name in ('Immich server', 'API service', 'node API', 'NAS')]
code = r"""
import net from 'node:net';
for(const [host,port] of TARGETS){await new Promise((resolve,reject)=>{const s=net.createConnection({host,port},()=>{s.destroy();reject(Error('unexpected private access'))});s.setTimeout(3000,()=>{s.destroy();resolve()});s.on('error',e=>{if(['ECONNREFUSED','EHOSTUNREACH','ENETUNREACH'].includes(e.code))resolve();else reject(e)})})}
console.log('Immich, API, node and NAS blocked');
""".replace('TARGETS', json.dumps(app_targets))
r = run('default', 'karakeep', 'node', '--input-type=module', input=code)
record('application download path denies unrelated private services', r.returncode == 0, r.stdout.strip() or r.stderr[-200:])

# An unrestricted source in default proves ingress denial, independent of media policies.
name = 'karakeep-ingress-validation'
probe_targets = [(service('karakeep-browser', 'karakeep-browser'), 9222), (service('karakeep', 'default'), 3000)]
code = '''const net=require('node:net');(async()=>{const r=await fetch('https://example.com');if(!r.ok)throw Error('public baseline');for(const [host,port] of TARGETS){await new Promise((resolve,reject)=>{const s=net.createConnection({host,port},()=>{s.destroy();reject(Error('unexpected access '+host+':'+port))});s.setTimeout(3000,()=>{s.destroy();resolve()});s.on('error',e=>{if(['ECONNREFUSED','EHOSTUNREACH','ENETUNREACH'].includes(e.code))resolve();else reject(e)})})}console.log('Unrelated pod blocked from browser control port and app backend')})().catch(e=>{console.error(e.message);process.exitCode=1})'''.replace('TARGETS', json.dumps(probe_targets))
job = {'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':'default'},'spec':{'backoffLimit':0,'activeDeadlineSeconds':45,'ttlSecondsAfterFinished':600,'template':{'spec':{'restartPolicy':'Never','automountServiceAccountToken':False,'securityContext':{'runAsUser':1001,'runAsGroup':1001,'runAsNonRoot':True,'seccompProfile':{'type':'RuntimeDefault'}},'containers':[{'name':'check','image':app['spec']['containers'][0]['image'],'command':['node','-e',code],'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},'resources':{'limits':{'memory':'128Mi'}}}]}}}}
created = False
try:
    r = kube('create', '-f', '-', input=json.dumps(job));r.check_returncode();created = True
    r = kube('wait', '-n', 'default', '--for=condition=Complete', 'job/'+name, '--timeout=50s')
    logs = kube('logs', '-n', 'default', 'job/'+name)
    record('only Karakeep can access browser; app backend requires ingress', r.returncode == 0, logs.stdout.strip() or logs.stderr[-200:])
finally:
    if created:
        kube('delete', 'job', name, '-n', 'default', '--wait=true').check_returncode()

report = {'time': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'results': results}
if args.output:
    args.output.write_text(json.dumps(report, indent=2)+'\n')
assert all(r['passed'] for r in results), 'Isolation check failed'
print(f'All {len(results)} checks passed.', flush=True)
