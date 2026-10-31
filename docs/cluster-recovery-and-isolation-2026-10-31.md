# Cluster recovery and workload isolation — 2026-10-31

The cluster was repaired and the namespace migration deployed through Git and Flux.
This report covers workload isolation and the recovery needed to deploy it. The
separate audit of every image's provenance, maintenance, digest pinning and Renovate
coverage remains unfinished.

## Recovery and deployment

- Flux and External Secrets controllers recovered after the earlier API connection
  failures. The Cilium chart source was changed from the inaccessible GHCR mirror
  to the official `quay.io/cilium/charts/cilium`, keeping version 1.18.6.
- Echo's updated Node runtime needed more startup time and memory. Its memory
  limit is now 256 MiB with a startup probe; the endpoint returned HTTP 200.
- Live rollout exposed and corrected Cilium default-deny validation, asymmetric
  VXLAN return rules, DNS proxy rules and search suffixes, node health-probe return
  routing, webhook bootstrap DNS, CoreDNS's required bind capability, and the
  chart's overwritten gateway init command.
- The VPN is pinned to the IPv4 endpoint for Mullvad `us-qas-wg-101`. IPv6 relay
  selection was unusable on this IPv4 cluster. Both underlay policy and Gluetun
  firewall restrict traffic; public DNS also traverses the tunnel.
- OAuth access to the local external gateway uses its actual backend port 10443
  with the specific authentication hostname as TLS SNI. No broad LAN exception
  was introduced. Fresh ML downloads required the exact `us.aws.cdn.hf.co` CDN
  hostname in addition to the Hugging Face domains.
- Post-migration Immich backups initially encountered the replaced pod's old DNS
  address, concurrent backup locks, and WAL archive timeouts during the restore
  burst. DNS converged. New database backup configurations use Zstandard level 3,
  two workers, and a 600-second archive wait instead of single-worker bzip2 level 9
  and the default 60-second wait. This follows the [pgBackRest configuration
  guidance](https://pgbackrest.org/user-guide.html).

## Deployed boundaries

| Namespace | Workloads and boundary |
| --- | --- |
| `immich` | Immich server/ML, dedicated PostgreSQL and Dragonfly; default deny with explicit internal and external dependencies |
| `media` | Arr, downloaders and Recyclarr; only explicit peers, dedicated DB, local DNS and VPN transport; no direct internet, other cluster, API, node or NAS connections |
| `media-vpn` | Gluetun gateway, fail-closed injector and split DNS; underlay restricted to selected VPN relay IPs/port |
| `media-database` | Dedicated Arr PostgreSQL and scoped credentials |
| `media-services` | Jellyfin, Jellyseerr, Kavita and Jellystat; explicit dependencies; Jellyfin/Kavita media mounts read-only |

The media injector fails closed, and admission rejects known media apps missing
the untrusted label or pinned native VPN sidecar. Applications do not mount an API
service-account token. Cilium enforces pod isolation independently of the gateway's
routes. NFS file access uses the node-mounted volume, without permitting pod-to-NAS
network access. Immich ML receives no application/database secret and cannot reach
the database or cache.

## Data preservation and migration

Writers were stopped before final dumps. The four Arr databases were restored into
`media-database/media16`; application table counts matched (Radarr 41, Sonarr 40,
Sonarr Anime 40, Prowlarr 20). Immich was restored into `immich/immich16`, preserving
extension ownership while assigning application objects to the `immich` role.
All **72 application tables** had matching exact row counts at cutover. The new
Immich role has no superuser, CREATEDB or CREATEROLE privileges.

Jellyfin, Jellyseerr and Kavita configuration PVCs were restored from their final
VolSync backups before starting the moved applications. All three subsequently
completed fresh backups in `media-services`, including scheduled runs at 16:00 UTC.
Jellystat's stored Jellyfin URL was updated to the new local service address.

The original PVCs, `database/immich16`, old Arr databases in `database/postgres16`,
and old Flux inventories remain available for rollback. A quarantine policy on the
old Immich database permits its operator, replication, monitoring and backups,
with no application clients. Old frontend backup sources are paused so they cannot
overwrite newer configuration backups. Old application writers and the old VPN
main deployment are stopped; the old VPN admission registration was removed.

Private pre-cutover manifests and SQL dumps are in
`/tmp/nimbus-recovery-20261031` on the operator workstation (directory mode 0700,
files 0600). These are temporary recovery artifacts, not durable backups. Do not
commit them. Retire them and legacy resources after a deliberate retention window.
Do not restart the stale databases as writers: subsequent writes exist only in the
new databases and must be accounted for in any rollback.

## Verification evidence

- Offline policy contracts and all 28 affected Kustomize builds passed; root Flux
  patches preserve suspended legacy inventories. Fourteen affected Helm renders
  were checked, including the gateway's post-rendered init command.
- Live Cilium policies reported valid, and active Flux Kustomizations and
  HelmReleases reported Ready.
- `scripts/verify-workload-isolation.py --exercise-underlay --exercise-outages`
  passed **31 checks**. The sanitized result is in
  [the runtime report](workload-isolation-runtime-2026-10-31.json).
- qBittorrent could not reach Immich server/cache/database, the API service, node
  API, or the NAS NFS endpoint. A forced public route through the original pod
  underlay also failed. Additional checks blocked both old/shared database pods.
- Blocking all permitted VPN relay IPs and then stopping the gateway each blocked
  internet access while Arr-to-downloader, Arr-to-indexer, Arr-to-database, the
  home UI, and mounted NFS stayed usable. Restoring the gateway restored Mullvad
  egress and all local checks. Temporary routes and outage policies were removed.
- Every long-running media app (all seven) independently reported a Mullvad exit
  address. Kapowarr used Python because its image has no curl.
- Three server-side admission checks verified rejection without the isolation
  label, rejection without injection, and successful pinned native sidecar
  injection for a correctly annotated pod.
- A Recyclarr Job using `--version` completed successfully with the native sidecar;
  it did not alter Arr configuration.
- Immich's server ping and both Immich/Kavita OAuth discovery returned HTTP 200.
  A fresh `ViT-B-32__openai` download and synthetic text-embedding request returned
  HTTP 200. ML-to-database and ML-to-cache connections were blocked.
- Jellyfin and Kavita mounts reported read-only; attempted temporary-file creation
  in each returned `Read-only file system`. No files were created.

Post-migration PostgreSQL backups were verified using both successful Jobs and
`pgbackrest info` reporting `ok`:

| Database | Local repository | Off-site repository |
| --- | --- | --- |
| Immich | Full `20261031-160724F`, finished 16:07:58 UTC | Full `20261031-160630F`, finished 16:08:19 UTC |
| Media | Full `20261031-155604F`, followed by successful incremental at 16:00:08 UTC | Full `20261031-160630F`, finished 16:06:40 UTC |

The Immich WAL archive backlog reached zero. Failed pre-correction backup Job
attempts were removed before triggering the final successful backup; application
volumes and existing repository backups were preserved. Final baseline network
checks passed again after deployment, with no new application container restarts
or unhealthy pods during the final observation period. All active secret stores
and ExternalSecrets reported Ready.

## Remaining limits

This is one shared node and kernel. Namespaces and policies do not isolate against
node, privileged gateway, CNI, CSI, operator or cluster-admin compromise. A separate
VM/cluster remains deferred. Home UI authentication remains deferred as requested.
NAS export ACLs/root squash and backup credential separation still need review.
Existing shared backup credentials are not a strong boundary against namespace
administrators. The inherited local S3 configuration also disables TLS certificate
verification; that remains part of the backup/supply-chain review. Retained database/image versions still require the separate supply
chain audit.

The tests above are bounded observations, not proof of every possible bypass.
Authenticated photo upload/download, full UI workflows, Gluetun-only process death,
WireGuard-interface deletion, and packet-continuous startup/restart leak tests were
not exercised. Logical database restores and frontend VolSync restores were tested;
a new physical PostgreSQL disaster-recovery restore should also be rehearsed.

Pre-existing Released restore volumes still emit cleanup warnings because they have
retained snapshots. These were preserved rather than deleting recovery snapshots;
they do not prevent active workloads, provisioning, or the verified backups.
