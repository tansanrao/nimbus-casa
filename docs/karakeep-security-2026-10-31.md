# Karakeep image maintenance and browser isolation — 2026-10-31

Deployed through Flux. Karakeep remains in `default` with its existing data volume
and databases. Its stateless browser now runs in the dedicated `karakeep-browser`
namespace. The old `default/karakeep-chrome` Deployment and Service were removed.

## Images and updates

The official Karakeep publisher remains the chosen upstream. Its [migration
guidance](https://docs.karakeep.com/administration/chrome-image-migration/) documents
the maintained browser image and versioned releases. The reviewed build source and
[publishing workflow](https://github.com/karakeep-app/karakeep/blob/85054d9a67de08bc83029a2e960e0a0621fd715f/.github/workflows/chrome.yml)
match the registry's source/revision labels. The workflow refuses to overwrite a
published version tag. Keeping this tested upstream avoids adding a separate
browser repackager and compatibility layer.

| Component | Deployed reference |
| --- | --- |
| Karakeep app and runtime-directory init container | `ghcr.io/karakeep-app/karakeep:0.34.1@sha256:69ae5315c618b7c14c1af3e34c6e211acdb231793af424ecd1cab0b70691d987` |
| Browser | `ghcr.io/karakeep-app/karakeep-chrome:156.0.8078.47-r1@sha256:4ad61127638dd27bfe685222787c5780dd1d083d23a7658c39af657775814c44` |

Karakeep 0.34.1 was already the latest stable app release. The old browser was still
running the stale `release` digest `5b19bbb160e9ff60681a3abd97e1c4ec9f64212301410de658c3900ab7ef31e7`.
The new browser digest matches the upstream's current promoted stable image.
The running container's imageID matched the configured digest, and both the Chrome
binary and DevTools reported **Chrome 156.0.8078.47** on this amd64 node.

Renovate now enables digest pinning for both images and permits their updates at
any time, overriding the repository's weekend-only schedule. Updates require
review/merge; this does not automatically deploy every new browser build or control
the hosted Renovate service's execution frequency. Chrome uses explicit regex
versioning for all four numeric components plus `-rN`, so rebuild revisions are
updates rather than a permanently fixed compatibility suffix. Mutable aliases and
architecture-specific tags are excluded by that versioning pattern.

Renovate 44.198.3 config validation and live lookup dry runs passed. Its Flux manager
extracted the app, init-container and browser references with their digests, with
no lookup warnings. A temporary fixture using Chrome `154.0.8037.57-r1` proposed
`156.0.8078.47-r1` with the correct new digest. The actual Renovate versioning API
also accepted `-r1` to `-r2`, fourth-component patch changes, and major upgrades.
See [sanitized lookup evidence](karakeep-renovate-evidence-2026-10-31.json).

## Enforced boundaries

- Browser namespace: default-deny ingress/egress and enforced Kubernetes
  `restricted` Pod Security at v1.37. Only the Karakeep application pod may access
  its DevTools port 9222. There is no ingress route or external Service.
- Browser egress: public IPv4 TCP 80/443 and CoreDNS TCP/UDP 53 only. Public CIDR
  permissions exclude private, link-local, CGNAT, multicast and reserved ranges.
  Host, remote-node and API-server destinations have explicit deny rules.
  No public IPv6 egress is allowed by this policy.
- Browser runtime: UID/GID 65534, no Linux capabilities, no privilege escalation,
  RuntimeDefault seccomp, read-only root filesystem, bounded temporary storage,
  no Kubernetes API token, no application secrets and no persistent/data mounts.
- Karakeep itself: ingress only through the configured gateways; egress only to
  its browser, shared PostgreSQL on 5432, Meilisearch on 7700, CoreDNS, public web
  destinations, and the authentication gateway's specific TLS hostname. This
  constrains direct application downloads as well as browser activity.
- The application also drops all capabilities and disables privilege escalation.
  Its s6 supervisor previously depended on escalation to repair `/run` ownership.
  A non-root init container now prepares an owned temporary subdirectory mounted
  at `/run`; startup and workers succeeded without that privilege dependency.
- The obsolete `COREPACK_INTEGRITY_KEYS=0` override was removed.

The browser uses ordinary public internet egress, not the media VPN. Public sites
can observe its egress IP. Local/intranet bookmarks are intentionally blocked.
The application can still access its own database and search backend, as required.

## Live validation

Run `python3 scripts/verify-karakeep-isolation.py --output /tmp/karakeep-check.json`
from an authorized workstation. It uses actual application/browser pods, creates a
disposable browser context and temporary diagnostic Job, and changes no bookmarks.

The completed checks are recorded in [runtime evidence](karakeep-runtime-2026-10-31.json).
They verify public HTTPS rendering through Karakeep's real browser endpoint,
database/search/OAuth/UI access, browser runtime restrictions, blocked browser
connections to private services, and denial from an unrelated unrestricted pod to
both DevTools and the app backend. Additional checks confirmed the restricted
namespace rejects a privileged Pod in server-side dry-run and that both Cilium
policies report Valid. The old browser resources are absent.

## Limits

The upstream entrypoint explicitly disables Chromium's own sandbox. These controls
provide pod and network containment, not a separate kernel or VM. A browser exploit
must still be treated as a possible container compromise; the browser has no app
secrets or data volumes to expose. Host/CNI/cluster-admin compromise remains outside
this boundary. A separate VM/cluster is still the stronger future boundary.

Digest pinning prevents silent tag replacement in deployments; it does not prove
that upstream maintainers or build systems can never be compromised. This change
is not a complete CVE/signature audit of the images or a repository-wide supply
chain remediation. Existing shared-database and secret-store trust limits remain.
