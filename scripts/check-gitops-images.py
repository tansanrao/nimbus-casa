#!/usr/bin/env python3
"""Verify pinned GitOps/ESO charts, images, and Flux distribution contents.

Requires helm, flux, yq, registry access; --live also uses kubectl. The optional
Renovate lookup log verifies extraction of every image/artifact and Flux version.
No Secrets are read and no cluster resources are modified.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [('flux-system','flux-operator'),('flux-system','flux-instance'),('external-secrets','external-secrets')]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--live',action='store_true')
parser.add_argument('--renovate-log',type=Path)
args=parser.parse_args()
def run(cmd,**kwargs):return subprocess.check_output(cmd,text=True,**kwargs)
def yaml(text):return json.loads(run(['yq','ea','-o=json','[.]','-'],input=text))
def read(path):return yaml(path.read_text())[0]
def pinned(ref):return bool(re.fullmatch(r'.+:[^@\s]+@sha256:[a-f0-9]{64}',ref))
lookups={}
if args.renovate_log:
    text=args.renovate_log.read_text();mark=text.index('DEBUG: packageFiles with updates')
    config=json.JSONDecoder().raw_decode(text[text.index('{',mark):])[0]
    for files in config.values():
        for file in files:
            for dep in file['deps']:
                if dep.get('datasource')=='docker':
                    assert not dep.get('warnings') and not dep.get('skipReason'),dep
                    ref=dep['depName']+':'+dep['currentValue']
                    if dep.get('currentDigest'):ref+='@'+dep['currentDigest']
                    lookups.setdefault(file['packageFile'],[]).append(ref)
def covered(path,ref,count=1):
    if args.renovate_log:assert lookups.get(str(path.relative_to(ROOT)),[]).count(ref)>=count,(path,ref,'missing Renovate coverage')
expected={};instance=None
for ns,name in TARGETS:
    app=ROOT/'kubernetes/apps'/ns/name/'app';hrpath=app/'helmrelease.yaml';sourcepath=app/'ocirepository.yaml'
    source=read(sourcepath)['spec'];spec=read(hrpath)['spec']
    chart=source['url']+':'+source['ref']['tag']+'@'+source['ref']['digest'];assert pinned(chart)
    covered(sourcepath,chart.removeprefix('oci://'))
    docs=yaml(run(['helm','template',name,source['url']+'@'+source['ref']['digest'],'-n',ns,'-f','-'],input=json.dumps(spec['values'])))
    counts={}
    for doc in docs:
        if not isinstance(doc,dict):continue
        if doc.get('kind')=='FluxInstance':instance=doc
        if doc.get('kind')=='Deployment':
            refs=[c['image'] for c in doc['spec']['template']['spec']['containers']]
            assert all(pinned(ref) for ref in refs),(name,refs)
            expected[(ns,doc['metadata']['name'])]=refs
            for ref in refs:counts[ref]=counts.get(ref,0)+1
    for ref,count in counts.items():covered(hrpath,ref,count)
    print('PASS',name,'immutable chart and explicit container settings',flush=True)
assert instance is not None
spec=instance['spec'];distribution=spec['distribution'];version=distribution['version']
assert re.fullmatch(r'v?\d+\.\d+\.\d+',version),'Flux version must be explicit'
assert pinned(distribution['artifact']),'Flux distribution must be immutable'
p=ROOT/'kubernetes/apps/flux-system/flux-instance/app/helmrelease.yaml'
covered(p,distribution['artifact'].removeprefix('oci://'));covered(p,'ghcr.io/fluxcd/flux-cli:'+version)
with tempfile.TemporaryDirectory(prefix='nimbus-flux-distribution-') as directory:
    run(['flux','pull','artifact',distribution['artifact'],'--output',directory])
    catalog=read(Path(directory)/'flux-images'/('v'+version.lstrip('v'))/'upstream-alpine.yaml')
    for name in spec['components']:
        image=next(i for i in catalog['images'] if i['name']=='ghcr.io/fluxcd/'+name)
        ref=image['name']+':'+image['newTag']+'@'+image['digest'];assert pinned(ref)
        expected[('flux-system',name)]=[ref]
print('PASS exact Flux release exists in pinned bundle; all selected controller images are pinned')
if args.live:
    for (ns,name),refs in expected.items():
        dep=json.loads(run(['kubectl','get','deployment',name,'-n',ns,'-o','json']))
        assert [c['image'] for c in dep['spec']['template']['spec']['containers']]==refs,(ns,name,'runtime images differ')
        assert dep['status'].get('observedGeneration')==dep['metadata']['generation'],name
        assert dep['status'].get('readyReplicas',0)==dep['spec'].get('replicas',1),name
    current=json.loads(run(['kubectl','get','fluxinstance','flux','-n','flux-system','-o','json']))
    assert current['spec']['distribution']['artifact']==distribution['artifact']
    assert current['status']['lastAppliedRevision'].startswith('v'+version.lstrip('v')+'@')
    assert any(c['type']=='Ready' and c['status']=='True' for c in current['status']['conditions'])
    print('PASS',len(expected),'live controller deployments and FluxInstance Ready')
print('PASS GitOps and External Secrets supply-chain checks')
