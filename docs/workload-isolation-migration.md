# Workload isolation and staged migration

Status: **deployed on 2026-10-31** after cluster recovery and stateful migration.
See [deployment evidence and remaining limits](cluster-recovery-and-isolation-2026-10-31.md).
The ordered migration below is retained as a recovery/reference procedure, not
an instruction to repeat the completed migration. Replacement Kustomizations and
HelmReleases are active. Legacy Kustomizations remain suspended with `prune: false`
and `deletionPolicy: Orphan`; legacy applications are stopped and their PVCs and
source databases are retained. Do not resume these legacy holds indiscriminately.

## Boundaries

| Namespace | Contents | Permitted connections |
| --- | --- | --- |
| `immich` | Immich server, ML, dedicated PostgreSQL, dedicated Dragonfly | Ingress gateway to server; server to its database/cache/ML; restricted OAuth/geocoding/model downloads; database backups/operator/API |
| `media` | Radarr, Sonarr, Sonarr Anime, Prowlarr, Kapowarr, qBittorrent, SABnzbd, Recyclarr | Internet through Gluetun only; explicit application peers and media DB; internal ingress gateway; mounted media library |
| `media-vpn` | Gluetun/pod gateway, admission webhook, split DNS | Pinned Mullvad relay on UDP 51820 (three permitted relay IPs); local DNS and VXLAN clients |
| `media-database` | Dedicated `media16` PostgreSQL | Arr clients, database operator/API/replication, backup endpoints |
| `media-services` | Jellyfin, Seerr, Kavita, Jellystat | Public HTTP(S) metadata services; explicit Arr/Jellyfin/database dependencies; read-only media library for Jellyfin/Kavita |

Every target namespace has default-deny ingress and egress. Application policies
use namespace-qualified endpoint selectors. Media applications cannot initiate
connections to Immich, the shared database, node addresses, Kubernetes API, LAN,
or arbitrary cluster services. The local ingress gateway remains the UI entry;
adding UI authentication is deferred as requested.

The VXLAN gateway and Gluetun firewall both fail closed. Cilium independently
restricts the gateway's underlay egress to selected VPN relays. The client routing
exceptions for pod/service CIDRs and the node probe return address are routes, **not network permissions**; Cilium
still requires an explicit allowed destination. The admission webhook fails closed
and a validating policy requires the pinned native VPN sidecar on known media apps.

Split DNS (`10.43.0.53`) forwards only the three permitted service zones to CoreDNS.
Public queries go to the VPN gateway DNS (`10.43.0.54`) without a direct fallback.
Gateway dnsmasq uses `1.1.1.1` through WireGuard; Gluetun's overlapping DNS listener
is disabled. The gateway cannot send direct underlay DNS to that address.
During VPN failure existing pods retain local service discovery, UI replies,
Arr/downloader/database connections, and mounted NFS access. New pods may wait
for the gateway during initialization. Public DNS caching never authorizes direct
internet egress. The two reserved DNS service IPs were verified during deployment.

NFS is mounted by the node CSI driver; application pods do not need arbitrary
network access to the NAS. New PV aliases preserve the existing exports without
rebinding or deleting the old PVs. **Never run both Immich servers against the same
library during migration.** Namespace separation cannot protect against a node,
privileged gateway, Cilium, CSI, operator, or cluster-admin compromise. A separate
VM/cluster remains deferred. NAS export ACLs/root squash and separate backup
credentials still need external configuration review; existing shared backup
credentials are retained and are not a strong boundary against a namespace admin.

## Before cutover

1. Repair the existing Flux and External Secrets controller crashloops observed
   during implementation. Confirm reconciliation, secret refresh, Cilium policy
   enforcement/L7 DNS proxy, storage provisioning, snapshots and backup restores
   are healthy. Do not migrate during that degraded baseline.
2. Run `python3 scripts/check-workload-isolation.py` (tools are pinned in
   `.mise.toml`). Render all affected Helm charts and apply their Flux
   post-renderers. Check live Cilium policy status after rollout; API schema
   validation alone does not prove traffic behavior.
3. Inventory source PVCs, routes, Deployments/CronJobs, Flux inventories and database
   pods. Record replicas/schedules. Take verified PostgreSQL backups, VolSync
   backups for all frontend configuration PVCs, and NAS snapshots. Secure any SQL
   dumps with mode 0600 and remove them after validated recovery. Test a restore.
4. Confirm the three Mullvad relay hostname/IP pairs in the gateway secret template
   and Cilium policy against the provider inventory. Changes must update both;
   the intentional failure mode for stale relay IPs is loss of internet.
5. Check free storage for two extra 50 GiB PostgreSQL PVCs and restored frontend
   configs. Verify destination backup paths differ from the source paths.
6. Review existing additive NetworkPolicies and ClusterwideNetworkPolicies. An
   extra broad allow can weaken a default-deny policy. Ensure no broad policy
   selects the new namespaces.

## Ordered migration

Perform in a maintenance window. Make each resumption explicit in Git; a manual
`flux resume` can be overwritten by the still-suspended Git declaration.

1. Reconcile the namespace roots and legacy holds. Verify old child Kustomizations
   are suspended and retain `Orphan`. This does not stop old workloads or Helm
   reconciliation: suspend each old application HelmRelease separately before
   scaling it down. Keep all old PVCs, database clusters and backups.
2. Resume the four isolation Kustomizations first: `media-isolation`,
   `media-services-isolation`, `media-database-isolation`, `immich-isolation`.
   Applying media policies interrupts old VPN-dependent pods until their gateway
   migration completes; expect downtime. Do not weaken the policy to bypass it.
3. Resume `media-database-postgres`, `immich-postgres`, and `immich-cache`. Check
   PostgreSQL readiness, operator access, generated user secrets, namespace-scoped
   secret stores, backup jobs and cache readiness. The new Immich database and
   cache are separate from `database/immich16` and the shared Dragonfly instance.
4. Stop/suspend Arr writers and schedules. Dump each source database from
   `database/postgres16`: `radarr_main`, `sonarr_main`, `sonarr_anime_main`, and
   `prowlarr_main`. Restore into the corresponding **empty** database in
   `media-database/media16`, owned by `radarr`, `sonarr`, `sonarr-anime`, and
   `prowlarr`, respectively. Use custom-format `pg_dump` and
   `pg_restore --exit-on-error --no-owner --no-acl --role=<app-role>` as the
   database administrator. Do not use `--clean` against a populated destination.
   Compare table counts and application data; preserve the source databases.
5. Stop the old Immich server and wait for database sessions/jobs to drain. Dump
   `database/immich16` database `immich`. The existing application used the
   PostgreSQL superuser and its tables are owned by `postgres`; ownership must
   change for the new least-privilege application account. Inspect the source
   extension names/versions/schemas. Pre-create matching extensions in the new
   empty database as administrator, retain extension ownership, exclude already
   created extension/comment entries from the restore TOC, and restore application
   objects with `--no-owner --no-acl --role=immich --exit-on-error`.
   Verify all application tables/sequences are owned by `immich`, the role has no
   superuser/CREATEDB/CREATEROLE privileges, and migrations can run. Do not grant
   superuser to work around restore errors. Keep the old server stopped.
6. Resume `media-services-shared` and the moved frontend/Immich application
   Kustomizations, keeping their **HelmReleases suspended**. Check the new NFS
   claims. Restore each frontend config with its VolSync ReplicationDestination;
   verify successful completion and contents before enabling its HelmRelease.
   VolSync backup movers have separate, narrow backup egress and no VPN mutation.
   Keep old config PVCs for rollback. Existing media app PVCs stay in `media`.
7. Suspend the old `network/vpn-gateway` HelmRelease and remove/disable its old
   MutatingWebhookConfiguration before creating replacement media pods, so there
   is exactly one injector. Preserve its configuration for rollback. Resume
   `media-vpn/vpn-gateway`; check the patched webhook `failurePolicy: Fail`,
   object selector, native sidecar flag, DNS services, relay connection and the
   actual gateway init command. Verify both DNS service IPs are still free first.
8. Resume the eight media app Kustomizations to reconcile new secrets/config and
   then their HelmReleases. Check pods contain the pinned init and native sidecar,
   `setGateway` annotation, untrusted label and no mounted API token. New Arr
   secrets must reference `media-postgres` / `media16`, never shared `postgres16`.
9. Enable restored frontend and Immich HelmReleases one at a time. Remove old
   conflicting HTTPRoutes before switching traffic; preserve route YAML for
   rollback. Update persisted Seerr/Jellystat URLs to services in
   `media-services`; verify Arr/downloader URLs still resolve in `media`.
   Immich must use `immich16-pguser-immich`, its dedicated cache and ML service.
   ML intentionally receives no application/database secrets.
10. Complete the acceptance matrix below. Trigger and verify new backups. Only
    after a retention window should legacy resources, old Arr database users,
    old database copies and old PVCs be removed in a separate reviewed change.

## Mandatory runtime acceptance matrix

Run tests from the **actual application pod network namespace** (an approved,
image-pinned ephemeral diagnostic container is suitable), with bounded timeouts.
A fresh standalone test pod with different labels does not prove the app policy.
Use Cilium/Hubble drops and Gluetun counters as evidence. Record results before
and during each failure mode, including continuous probes across transitions.

| Test | Expected result |
| --- | --- |
| Each media app: public HTTPS, public DNS | Works; visible egress IP belongs to selected VPN provider |
| Force public traffic via original pod gateway/interface, including direct IP, external DNS TCP/UDP 53 and DoH | Blocked; no bypass via direct underlay |
| Arr to permitted qBittorrent/SABnzbd/prowlarr and its media DB | Works on explicit application ports |
| Media to Immich server/ML/cache/database by Service IP and Pod IP | Blocked |
| Media to shared Postgres, API, node IP, LAN/NAS network services, unrelated pods | Blocked |
| Home UI via internal ingress gateway; file access via mounted NFS | Works |
| Stop Gluetun only; remove wg0; block relay traffic; restart gateway; scale gateway down | Public traffic blocked throughout; existing local connections, local DNS, UI and NFS remain usable |
| Restore VPN after each failure | Internet resumes only through VPN; no temporary direct egress |
| Break admission webhook or omit injection/untrusted label for known media app | Pod creation denied, never starts without VPN sidecar |
| Recyclarr CronJob finishes | Native VPN sidecar terminates and Job completes |
| Immich upload/download/search, OAuth, geocoding and fresh ML model download | Works; no broad internet permission needed |
| Immich ML to server DB/cache; media to Immich secrets/API | Blocked |
| Jellyfin/Kavita write to mounted media library | Denied; reads succeed |
| New PostgreSQL/VolSync backup and a restore to scratch storage | Succeeds |

If VPN startup or DNS fails, inspect Cilium drops and firewall counters; do not
allow world/RFC1918 egress as a workaround. If local access fails during the VPN
failure tests, the migration is not accepted even if internet is correctly blocked.

## Rollback

Stop new application writers first. Suspend the replacement HelmReleases and
Kustomizations. Preserve new data and take a backup before switching databases.
For a rollback after writes, restore the latest new database into a separate old
cluster recovery target; simply starting the stale database loses those writes.
Restore the prior routes and injector only after removing the new injector.
Revert policy/routing changes coherently with the old configuration, then resume
old HelmReleases and restore replica counts. Never run two Immich writers against
the same export. Keep legacy holds until successful cutover is established.

## Validation and remaining security work

The implementation passed Kustomize builds, policy contract checks, Helm renders,
server-side admission checks and live network tests. The automated live suite
passed 31 checks, including relay loss and gateway shutdown with local access
preserved. See the deployment report for the exact checks performed; the broader
acceptance matrix above also lists future regression tests and is not a claim that
every listed failure mode or authenticated application workflow was exercised.

Run `python3 scripts/verify-workload-isolation.py` for read-only baseline checks.
The `--exercise-underlay --exercise-outages` flags deliberately change routing,
block relays and stop the gateway, and belong in an authorized maintenance window.

This change addresses workload isolation. It does not finish the separate audit
of image maintenance/trust, all image digest pins, general Renovate coverage,
secret-vault tenancy, or backup credential separation. A Renovate regex manager
tracks the admission policy's embedded VPN image pin alongside the Helm value;
the regression check rejects pin drift. All new gateway/DNS/cache images are
pinned, but inherited database and application image gaps from the audit remain.

References: [Gluetun firewall rules](https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/firewall.md),
[WireGuard options](https://github.com/qdm12/gluetun-wiki/blob/main/setup/options/wireguard.md),
[Cilium DNS policies](https://docs.cilium.io/en/latest/security/dns/).
