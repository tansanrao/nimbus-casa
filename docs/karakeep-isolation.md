# Karakeep browser isolation

Karakeep runs in `karakeep` with Meilisearch and keeps its data in SQLite on its PVC. Its headless Chrome runs alone in `karakeep-browser`. Both namespaces enforce restricted Pod Security and default-deny Cilium policies. This was deployed on 2026-10-31.

## Images

Both images come from the Karakeep project (`ghcr.io/karakeep-app/karakeep` and `ghcr.io/karakeep-app/karakeep-chrome`) and are pinned by digest in their HelmReleases. The upstream [Chrome publishing workflow](https://github.com/karakeep-app/karakeep/blob/85054d9a67de08bc83029a2e960e0a0621fd715f/.github/workflows/chrome.yml) refuses to overwrite a published version tag.

Renovate checks both images at any time of day instead of on the weekend schedule, and opens PRs without automerge. Chrome tags use a regex versioning that reads all four version numbers and the `-rN` rebuild suffix, so rebuilds count as updates and mutable aliases are ignored. The lookup was tested with Renovate 44.198.3 ([evidence](karakeep-renovate-evidence-2026-10-31.json)).

## Browser

- Ingress: only the Karakeep app pod, on DevTools port 9222. There is no route or external Service.
- Egress: CoreDNS, plus public IPv4 on TCP 80 and 443. Private, link-local, CGNAT, multicast and reserved ranges are excluded, and host, remote-node and API server destinations are explicitly denied. There is no IPv6 egress.
- Runtime: UID and GID 65534, no capabilities, no privilege escalation, RuntimeDefault seccomp, read-only root filesystem, size-limited temporary storage. No API token, secrets or persistent volumes.

The browser uses the normal internet connection, not the media VPN, so sites see the home IP. Bookmarks pointing at LAN or cluster addresses fail on purpose.

The upstream entrypoint turns off Chromium's own sandbox. Treat a browser exploit as a container compromise. The container holds no secrets or data, but the node, Cilium and cluster-admin remain outside this boundary.

## App

Karakeep accepts traffic only from the gateways. It can reach its browser, Meilisearch on 7700, CoreDNS, public web destinations, and authentik's OAuth hostname through Envoy external on port 10443. The policy covers Karakeep's own downloads as well as the browser's.

The app drops all capabilities and runs without privilege escalation. An init container creates an owned directory that is mounted at `/run`, because s6 would otherwise need escalation to fix that directory's ownership.

## Checks

```sh
python3 scripts/verify-karakeep-isolation.py --output /tmp/karakeep-check.json
```

The script runs in the real app and browser pods. It opens a disposable browser context and a temporary diagnostic Job, and does not change bookmarks. It checks public HTTPS rendering through the browser, the local SQLite database, search, OAuth and UI access, that the app cannot reach the shared PostgreSQL, the browser's runtime restrictions, blocked connections from the browser to private services, and that an unrelated pod cannot reach DevTools or the app. The 2026-10-31 results are in [karakeep-runtime-2026-10-31.json](karakeep-runtime-2026-10-31.json).
