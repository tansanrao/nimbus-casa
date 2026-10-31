#!/usr/bin/env python3
"""Live admission/network/TLS tests. Creates temporary RBAC and a diagnostic pod.

Mounts only the public Connect CA; never reads credential values. Requires kubectl
and running Karakeep/Mealie deployments. Removes test resources in finally blocks.
"""
import subprocess,json

def k(*args,**kwargs):return subprocess.run(['kubectl',*args],capture_output=True,text=True,timeout=60,**kwargs)
def apply(obj):
 r=k('apply','--server-side','-f','-',input=json.dumps(obj));r.check_returncode()
# Give a temporary identity namespace-local store creation rights; admission must still reject it.
ns='media';name='secret-isolation-verification'
role={'apiVersion':'rbac.authorization.k8s.io/v1','kind':'Role','metadata':{'name':name,'namespace':ns},'rules':[{'apiGroups':['external-secrets.io'],'resources':['secretstores'],'verbs':['create','get','patch','update']}]}
binding={'apiVersion':role['apiVersion'],'kind':'RoleBinding','metadata':role['metadata'],'roleRef':{'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':name},'subjects':[{'kind':'ServiceAccount','name':'default','namespace':ns}]}
try:
 apply(role);apply(binding)
 store={'apiVersion':'external-secrets.io/v1','kind':'SecretStore','metadata':{'name':name,'namespace':ns},'spec':{'provider':{'kubernetes':{'remoteNamespace':'database','server':{'caProvider':{'type':'ConfigMap','name':'kube-root-ca.crt','key':'ca.crt'}},'auth':{'serviceAccount':{'name':'default'}}}}}}
 r=k('create','--dry-run=server','--as=system:serviceaccount:media:default','-f','-',input=json.dumps(store))
 assert r.returncode and 'secret-provider-administration' in r.stderr,r.stderr
 print('PASS namespace-author cannot create bypass SecretStore')
finally:
 k('delete','rolebinding,role',name,'-n',ns,'--ignore-not-found')
# The diagnostic pod mounts only the public CA certificate and has no API token.
image=json.loads(k('get','deploy','karakeep','-n','default','-o','json').stdout)['spec']['template']['spec']['containers'][0]['image']
code=r'''const https=require('https'),fs=require('fs');
const host='onepassword.external-secrets.svc.cluster.local';
const ca=fs.readFileSync('/ca/ca.crt');
function req(opts){return new Promise((resolve,reject)=>{const r=https.get({hostname:host,port:8443,path:'/heartbeat',timeout:5000,...opts},s=>{s.resume();resolve(s.statusCode)});r.on('error',reject);r.on('timeout',()=>r.destroy(new Error('timeout')))});}
(async()=>{if(await req({ca})!==200)throw Error('heartbeat failed');console.log('PASS trusted CA and correct hostname');for(const opts of [{},{ca,servername:'wrong.invalid'}]){let rejected=false;try{await req(opts)}catch(e){if(!['UNABLE_TO_VERIFY_LEAF_SIGNATURE','SELF_SIGNED_CERT_IN_CHAIN','DEPTH_ZERO_SELF_SIGNED_CERT','ERR_TLS_CERT_ALTNAME_INVALID','UNABLE_TO_GET_ISSUER_CERT_LOCALLY'].includes(e.code))throw e;rejected=true}if(!rejected)throw Error('TLS accepted invalid trust/hostname')}console.log('PASS untrusted CA and wrong hostname rejected')})().catch(e=>{console.error(e.message);process.exitCode=1});'''
pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':'external-secrets','labels':{'app.kubernetes.io/name':'external-secrets'}},'spec':{'restartPolicy':'Never','automountServiceAccountToken':False,'securityContext':{'runAsNonRoot':True,'runAsUser':1000,'runAsGroup':1000,'seccompProfile':{'type':'RuntimeDefault'}},'containers':[{'name':'probe','image':image,'command':['node','-e',code],'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']},'readOnlyRootFilesystem':True},'volumeMounts':[{'name':'ca','mountPath':'/ca','readOnly':True}]}],'volumes':[{'name':'ca','secret':{'secretName':'onepassword-tls','items':[{'key':'ca.crt','path':'ca.crt'}]}}]}}
try:
 apply(pod)
 r=k('wait','pod/'+name,'-n','external-secrets','--for=jsonpath={.status.phase}=Succeeded','--timeout=45s')
 logs=k('logs',name,'-n','external-secrets');print(logs.stdout.strip());assert r.returncode==0,r.stderr
finally:k('delete','pod',name,'-n','external-secrets','--ignore-not-found','--wait=false')
# Mealie has no general egress deny: this exercises Connect's ingress boundary.
svc=json.loads(k('get','svc','onepassword','-n','external-secrets','-o','json').stdout)['spec']['clusterIP']
pods=json.loads(k('get','pods','-n','external-secrets','-l','app.kubernetes.io/name=onepassword','-o','json').stdout)['items']
ip=next(p['status']['podIP'] for p in pods if not p['metadata'].get('deletionTimestamp'))
code='import socket\nfor host,port in '+repr([(svc,8443),(ip,8443),(ip,8080),(ip,8081)])+':\n try:\n  s=socket.create_connection((host,port),3)\n except (TimeoutError,ConnectionRefusedError):\n  print("PASS unauthorized connection blocked",host,port)\n else:\n  s.close();raise RuntimeError("Connect exposed to unauthorized application")\n'
r=k('exec','-i','deploy/mealie','-n','default','-c','app','--','python3','-',input=code)
print(r.stdout.strip());assert r.returncode==0,r.stderr
