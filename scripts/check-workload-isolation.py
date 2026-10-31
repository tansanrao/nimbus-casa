#!/usr/bin/env python3
"""Offline isolation regression checks. Requires Python 3, yq v4, kustomize.

Checks declared policy contracts, not Cilium's runtime enforcement. Run the
cutover acceptance tests before declaring the live cluster isolated.
"""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / 'kubernetes/apps'
ZONES = ('media', 'media-services', 'media-vpn', 'media-database', 'immich')
UNTRUSTED = ('radarr', 'sonarr', 'sonarr-anime', 'prowlarr', 'kapowarr',
             'qbittorrent', 'sabnzbd', 'recyclarr')


def read(path):
    return json.loads(subprocess.check_output(['yq', 'ea', '-o=json', '[.]', str(path)]))


def one(path):
    return read(path)[0]


def policy(ns):
    part = 'vpn-gateway' if ns == 'media-vpn' else 'isolation'
    return {d['metadata']['name']: d['spec'] for d in
            read(APPS / ns / part / 'app/networkpolicy.yaml')}


policies = {ns: policy(ns) for ns in ZONES}
for ns, ps in policies.items():
    assert ps['default-deny'] == {'endpointSelector': {}, 'ingress': [], 'egress': []}, ns

# A positive or negative assertion below concerns explicit endpoint rules.
# CIDR/FQDN/entity exceptions are checked separately; this is not a Cilium simulator.
def endpoint_allowed(ns, name, dst_ns, dst_app, port):
    for rule in policies[ns][name].get('egress', []):
        for selector in rule.get('toEndpoints', []):
            labels = selector['matchLabels']
            if (labels.get('k8s:io.kubernetes.pod.namespace') == dst_ns
                    and labels.get('k8s:app.kubernetes.io/name') == dst_app):
                if any(str(p['port']) == str(port) for block in rule.get('toPorts', [])
                       for p in block['ports']):
                    return True
    return False

for app in UNTRUSTED:
    ps = policies['media'][app]
    assert ps['egressDeny'][0]['toEntities'] == ['host', 'remote-node', 'kube-apiserver']
    for rule in ps['egress']:
        assert not any(k in rule for k in ('toCIDR', 'toCIDRSet', 'toEntities', 'toFQDNs'))
        for ep in rule['toEndpoints']:
            assert ep['matchLabels']['k8s:io.kubernetes.pod.namespace'] in (
                'media', 'media-vpn', 'media-database', 'kube-system')
    assert endpoint_allowed('media', app, 'media-vpn', 'pod-gateway', 4789)
    assert endpoint_allowed('media', app, 'media-vpn', 'media-dns', 1053)
    assert not endpoint_allowed('media', app, 'immich', 'immich', 2283)
    assert not endpoint_allowed('media', app, 'network', 'envoy', 443)
    hr = one(APPS / 'media' / app / 'app/helmrelease.yaml')['spec']
    assert hr['suspend'] is True
    pod = hr['values']['defaultPodOptions']
    assert pod['automountServiceAccountToken'] is False
    pod = hr['values']['controllers']['main']['pod']
    assert pod['labels']['isolation.nimbus.casa/zone'] == 'untrusted'
    assert str(pod['annotations']['setGateway']).lower() == 'true'

for app in ('radarr', 'sonarr', 'sonarr-anime', 'kapowarr'):
    assert endpoint_allowed('media', app, 'media', 'qbittorrent', 8080)
    assert endpoint_allowed('media', app, 'media', 'sabnzbd', 80)
assert endpoint_allowed('media-services', 'jellyseerr', 'media', 'radarr', 80)
assert not endpoint_allowed('media', 'qbittorrent', 'media-services', 'jellyfin', 8096)

vpn = one(APPS / 'media-vpn/vpn-gateway/app/helmrelease.yaml')['spec']
values = vpn['values']
assert values['settings']['VPN_BLOCK_OTHER_TRAFFIC'] is True
assert values['webhook']['sidecarAsInit'] is True
assert values['webhook']['gatewayDefault'] is False
assert values['DNS'] == '10.43.0.53'
secret = one(APPS / 'media-vpn/vpn-gateway/app/externalsecret.yaml')['spec']['target']['template']['data']
assert secret['DNS_SERVER'] == 'off' and secret['DNS_KEEP_NAMESERVER'] == 'off'
assert secret['DNS_ADDRESS'] == '1.1.1.1'
img = values['controllers']['main']['containers']['main']['image']
image = img['repository'] + ':' + img['tag']
admission = one(APPS / 'media/isolation/app/admission.yaml')['spec']
assert any(image in v['expression'] for v in admission['validations']), 'VPN admission pin drifted'
assert admission['failurePolicy'] == 'Fail'
patches = vpn['postRenderers'][0]['kustomize']['patches']
assert any('"failurePolicy"' in p['patch'] or '/failurePolicy' in p['patch'] for p in patches)
assert any('/isolation/forward-guard.sh' in p['patch'] for p in patches)
for rule in policies['media-vpn']['gateway']['egress']:
    if 'toCIDR' in rule:
        assert len(rule['toCIDR']) == 3 and all(c.endswith('/32') for c in rule['toCIDR'])
        assert rule['toPorts'] == [{'ports': [{'port': '51820', 'protocol': 'UDP'}]}]
    else:
        assert 'toEndpoints' in rule

# Preserve old Flux inventories; the parent's default patch must not override Orphan.
parent = one(ROOT / 'kubernetes/flux/cluster/ks.yaml')
assert parent['spec']['patches'][0]['target']['labelSelector'] == '!isolation.nimbus.casa/legacy-hold'
for ns in ('default', 'media', 'network'):
    for hold in read(APPS / ns / 'isolation-legacy.yaml'):
        assert hold['spec']['suspend'] is True
        assert hold['spec']['prune'] is False
        assert hold['spec']['deletionPolicy'] == 'Orphan'
        assert hold['metadata']['labels']['isolation.nimbus.casa/legacy-hold'] == 'true'

immich = one(APPS / 'immich/immich/app/helmrelease.yaml')['spec']['values']
assert 'envFrom' not in immich['controllers']['machine-learning']['containers']['app']
assert 'immich16-pguser-postgres' not in (APPS / 'immich/immich/app/externalsecret.yaml').read_text()
for ns in ('immich', 'media-database'):
    cluster = one(APPS / ns / ('database' if ns == 'immich' else 'postgres') / 'app/cluster.yaml')
    assert cluster['spec']['service']['type'] == 'ClusterIP'
    assert cluster['spec']['backups']['pgbackrest']['global']['repo1-path'].startswith('/isolation/')
for app in ('jellyfin', 'kavita'):
    text = (APPS / 'media-services' / app / 'app/helmrelease.yaml').read_text()
    assert 'readOnly: true' in text and 'media-services-nfs-pvc' in text

# Build every affected tree (including VolSync components), and exercise root patches.
builds = 0
for ns in ZONES:
    for path in (APPS / ns).rglob('kustomization.yaml'):
        subprocess.run(['kustomize', 'build', str(path.parent)], check=True, stdout=subprocess.DEVNULL)
        builds += 1
with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    rendered = subprocess.check_output(['kustomize', 'build', str(APPS)], text=True)
    (directory / 'apps.yaml').write_text(rendered)
    (directory / 'kustomization.yaml').write_text(json.dumps({
        'apiVersion': 'kustomize.config.k8s.io/v1beta1', 'kind': 'Kustomization',
        'resources': ['apps.yaml'], 'patches': parent['spec']['patches']}))
    patched = subprocess.check_output(['kustomize', 'build', str(directory)], text=True)
    (directory / 'patched.yaml').write_text(patched)
    for obj in read(directory / 'patched.yaml'):
        if obj.get('metadata', {}).get('labels', {}).get('isolation.nimbus.casa/legacy-hold'):
            assert obj['spec']['deletionPolicy'] == 'Orphan'
print(f'Isolation contracts passed; {builds} affected Kustomizations and root patches built.')
