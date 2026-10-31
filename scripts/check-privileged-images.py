#!/usr/bin/env python3
"""Render GPU/storage charts and reject unpinned or unexpected publisher images.

Requires helm/yq/kustomize and registry access. --renovate-log also checks actual
Renovate lookup coverage. --live checks running workloads and generated-image
settings. Does not read Secrets or alter the cluster.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / 'kubernetes/apps'
TARGETS = ['kube-system/intel-gpu-plugin', 'kube-system/generic-device-plugin',
           'kube-system/node-feature-discovery', 'kube-system/csi-driver-nfs',
           'kube-system/snapshot-controller', 'openebs-system/openebs',
           'volsync-system/volsync']
PUBLISHERS = ('intel/intel-gpu-plugin:', 'squat/generic-device-plugin:',
              'registry.k8s.io/nfd/node-feature-discovery:', 'registry.k8s.io/sig-storage/',
              'quay.io/openebs/', 'docker.io/openebs/', 'quay.io/backube/volsync:')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--renovate-log', type=Path)
parser.add_argument('--live', action='store_true')
args = parser.parse_args()
def command(cmd, **kwargs):
    return subprocess.check_output(cmd, text=True, **kwargs)
def yaml(text):
    return json.loads(command(['yq', 'ea', '-o=json', '[.]', '-'], input=text))
def read(path):
    return yaml(path.read_text())
def images(obj):
    found = []
    if isinstance(obj, dict):
        if isinstance(obj.get('image'), str):
            found.append(obj['image'])
        if obj.get('name') == 'OPENEBS_IO_HELPER_IMAGE':
            found.append(obj['value'])
        for value in obj.values():
            found.extend(images(value))
    elif isinstance(obj, list):
        for value in obj:
            if isinstance(value, str) and '-container-image=' in value:
                found.append(value.split('=', 1)[1])
            else:
                found.extend(images(value))
    return found

def check(refs, label):
    assert refs, f'{label}: no images inspected'
    for ref in refs:
        assert re.fullmatch(r'.+:[^@\s]+@sha256:[a-f0-9]{64}', ref), (label, 'not pinned', ref)
        assert ref.startswith(PUBLISHERS), (label, 'unreviewed publisher', ref)

lookup = None
if args.renovate_log:
    log = args.renovate_log.read_text()
    start = log.index('DEBUG: packageFiles with updates')
    config = json.JSONDecoder().raw_decode(log[log.index('{', start):])[0]
    lookup = {}
    for files in config.values():
        for f in files:
            for d in f['deps']:
                if d.get('datasource') != 'docker':
                    continue
                assert not d.get('warnings'), (f['packageFile'], d['depName'], d['warnings'])
                if d.get('currentDigest'):
                    lookup.setdefault(f['packageFile'], set()).add(d['depName']+':'+d['currentValue']+'@'+d['currentDigest'])
all_refs = set()
for target in TARGETS:
    app = APPS / target / 'app'
    command(['kustomize', 'build', str(app)])
    hrfile = app / 'helmrelease.yaml'
    if hrfile.exists():
        hr = read(hrfile)[0]
        spec = hr['spec']
        name = hr['metadata']['name']
        cli = ['helm', 'template', name]
        if 'chartRef' in spec:
            source = read(app / 'ocirepository.yaml')[0]['spec']
            assert 'digest' in source['ref'], target + ': OCI chart must be digest-pinned'
            cli += [source['url']+'@'+source['ref']['digest']]
        else:
            chart = spec['chart']['spec']
            repo = read(app / 'helmrepository.yaml')[0]['spec']['url']
            cli += [chart['chart'], '--repo', repo, '--version', chart['version']]
        cli += ['--namespace', target.split('/')[0], '-f', '-']
        rendered = yaml(command(cli, input=json.dumps(spec['values'])))
        package_file = str(hrfile.relative_to(ROOT))
    else:
        file = app / ('daemonset.yaml' if 'intel-gpu' in target else 'generic-device-plugin.yaml')
        rendered = read(file)
        package_file = str(file.relative_to(ROOT))
    refs = set(images(rendered))
    check(refs, target)
    if lookup is not None:
        assert refs <= lookup.get(package_file, set()), (target, 'missing Renovate coverage', refs-lookup.get(package_file, set()))
    if target.endswith('/volsync'):
        movers = [s for d in rendered if isinstance(d, dict) and d.get('kind') == 'Deployment'
                  for c in d['spec']['template']['spec']['containers'] for s in c.get('args', []) if '-container-image=' in s]
        assert len(movers) == 5, 'Expected all five VolSync worker image settings'
    all_refs.update(refs)
    print('PASS', target, len(refs), 'distinct pinned image references', flush=True)
if args.live:
    pods = json.loads(command(['kubectl', 'get', 'pods', '-A', '-o', 'json']))['items']
    checked = 0
    for p in pods:
        ns = p['metadata']['namespace'];name = p['metadata']['name']
        if p['metadata'].get('deletionTimestamp') or p.get('status', {}).get('phase') in ['Succeeded','Failed']:
            continue
        selected = ns in ['openebs-system','volsync-system'] or (ns == 'kube-system' and name.startswith(('intel-gpu-plugin-','generic-device-plugin-','node-feature-discovery-','csi-nfs-','snapshot-controller-')))
        if selected:
            refs = set(images(p['spec']))
            check(refs, ns+'/'+name)
            assert refs <= all_refs, (name, 'unexpected runtime image', refs-all_refs)
            assert all(c.get('ready') for c in p.get('status',{}).get('containerStatuses',[])), name+' not Ready'
            checked += 1
    assert checked >= 11, 'Missing expected GPU/storage workloads'
    print('PASS', checked, 'live workloads, including generated-image settings')
print('PASS', len(all_refs), 'distinct immutable image references')
