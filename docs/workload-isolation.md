# Workload isolation

Applications are split into namespaces with default-deny Cilium policies on ingress and egress. Each `<namespace>/isolation` Kustomization holds that namespace's policies. Policies select endpoints by namespace, and application pods don't mount a Kubernetes API token. This was deployed on 2026-10-31.

## Namespaces

| Namespace | Workloads | Allowed connections |
| --- | --- | --- |
| `immich` | Immich server and ML, `immich-db`, Dragonfly | Gateway to server; server to its database, cache and ML; OAuth, geocoding and model downloads (including `us.aws.cdn.hf.co`) |
| `media` | Radarr, Sonarr, Sonarr Anime, Prowlarr, Kapowarr, qBittorrent, SABnzbd, Recyclarr | Internet only through the VPN gateway; named app peers; `media-database`; internal gateway; NFS media library |
| `media-vpn` | Gluetun pod gateway, admission webhook, split DNS | Three Mullvad relay IPs on UDP 51820; local DNS; VXLAN clients |
| `media-database` | CloudNativePG `media` | Arr apps, Jellystat, operator, Garage |
| `media-services` | Jellyfin, Seerr, Kavita, Jellystat | Public metadata services; Arr, Jellyfin and database peers; media library mounted read-only in Jellyfin and Kavita |
| `authentik` | authentik, LDAP outpost, CloudNativePG `auth` | Restricted Pod Security |
| `karakeep`, `karakeep-browser` | Karakeep, Meilisearch, headless Chrome | See [karakeep-isolation.md](karakeep-isolation.md) |
| `mealie`, `miniflux` | One app each | Restricted Pod Security; database in `database/postgres` |
| `database` | CloudNativePG `postgres` and `paradedb`, shared Dragonfly, operators | Per-cluster client policies |

Every CloudNativePG cluster also gets a policy from `kubernetes/components/cnpg`. It allows the operator, metrics scraping from `observability`, DNS, the API server and Garage (`s3.kbcb.tansanrao.net`). Port 5432 is opened by a separate policy next to each cluster.

Immich ML has no application or database secret and cannot reach the database or cache. Media apps cannot reach Immich, other namespaces' databases, node addresses, the API server, the LAN or the NAS over the network.

Pods reach NFS through volumes the node CSI driver mounts, so no pod needs network access to the NAS.

Apps that sign in through authentik (in `immich`, `media-services`, `karakeep`, `mealie` and `miniflux`) reach it through Envoy external's backend port 10443, with the authentication hostname as TLS SNI, not through a LAN-wide exception.

## Media VPN

Media pods get a VXLAN route to the Gluetun gateway in `media-vpn` from a mutating webhook. The webhook fails closed. A validating admission policy rejects known media apps that lack the `untrusted` label or the pinned native VPN sidecar. Recyclarr's CronJob works because the native sidecar exits when the job finishes.

Gluetun connects to Mullvad `us-qas-wg-101` over IPv4. Cilium separately limits the gateway's underlay egress to three relay IPs on UDP 51820. The endpoint in `externalsecret.yaml` must be one of the IPs in `networkpolicy.yaml` (both in `kubernetes/apps/media-vpn/vpn-gateway/app/`), so change them together. A stale IP cuts internet access; it never opens a direct path.

The client routes that bypass the gateway for pod and service CIDRs, and for the node probe address, are routes only. Cilium still has to allow each destination.

DNS for media pods goes to the split DNS service at `10.43.0.53`. It forwards the cluster service zones to CoreDNS and everything else to the gateway's dnsmasq at `10.43.0.54`, which resolves through `1.1.1.1` inside the tunnel. There is no direct fallback, and Gluetun's own DNS listener is off.

When the VPN is down, running pods lose internet access but keep local DNS, UIs, Arr-to-downloader and database connections, and NFS. New pods may wait for the gateway during init.

A Renovate regex manager updates the VPN sidecar image pinned in the admission policy along with the Helm value. `scripts/check-workload-isolation.py` fails if the two drift apart.

## Moved app state

- Mealie, Karakeep and Meilisearch kept their original PVs (see the [OpenEBS runbook](../kubernetes/apps/openebs-system/openebs/README.md)). VolumeSnapshots from before the move still exist: `default/mealie-namespace-cutover`, `default/karakeep-namespace-cutover` and `database/meilisearch-karakeep-namespace-cutover`.
- The authentik outpost configuration, stored in PostgreSQL, targets the `authentik` namespace. It turns off the LDAP deployment's service-account token and requests `10.10.40.72` through `lbipam.cilium.io/ips`. Keep these settings when restoring authentik. Only the worker keeps outpost-management permissions.

## Legacy holds

Five Kustomizations from before the move are suspended with `prune: false` and `deletionPolicy: Orphan`: `default/immich`, `media/jellyfin`, `media/jellystat`, `media/kavita` and `network/vpn-gateway`. Their HelmReleases are also suspended, and the workloads are scaled to zero. They keep the old PVCs (`media/jellyfin`, `media/kavita` and `default/immich-nfs-pvc`). The old VPN webhook registration has been removed.

Don't resume them. A second Immich server against the same NFS library would corrupt it, and a second VPN webhook would conflict with `media-vpn`. To retire them, remove them from Git in a reviewed change.

## Verification

Static, no cluster access:

```sh
python3 scripts/check-workload-isolation.py
```

Live, read-only:

```sh
python3 scripts/verify-workload-isolation.py
python3 scripts/verify-application-isolation.py
python3 scripts/verify-karakeep-isolation.py
python3 scripts/verify-secret-isolation.py
```

Run `verify-application-isolation.py` and `verify-karakeep-isolation.py` one after the other, because their probes share policy selectors.

`verify-workload-isolation.py --exercise-underlay --exercise-outages` forces traffic through the original pod interface, blocks the relays and stops the gateway. It interrupts media downloads.

On 2026-10-31 that full run passed 31 checks ([results](workload-isolation-runtime-2026-10-31.json)). Media apps could not reach Immich, the API server, node addresses or the NAS. With relays blocked and with the gateway stopped, internet access failed while local access and NFS kept working. All seven media apps reported a Mullvad exit IP. Admission rejected pods without the label or the sidecar. Writes to the read-only Jellyfin and Kavita mounts failed.

Not yet tested:

- authenticated Immich upload and download;
- killing only the Gluetun process or deleting `wg0`;
- continuous leak checks across gateway restarts;
- a physical restore of a PostgreSQL cluster from Garage.

## Limits

Everything runs on one node and one kernel. These policies do not protect against a compromise of the node, the privileged VPN gateway, Cilium, the CSI drivers, the operators or cluster-admin. A separate VM or cluster would be a stronger boundary. Not yet reviewed: NAS export ACLs and root squash, home UI authentication, and separate backup credentials per namespace.
