# Ansible

Host configuration for Nimbus Casa infrastructure.

The first managed hosts are:

- Inventory host: `gw0.kiad.tansanrao.net`
- System hostname: `gw0`
- Inventory host: `connector0`
- System hostname: `connector0`
- Timezone: `UTC`

## Commands

Run through Taskfile from the repository root:

```sh
task ansible:inventory
task ansible:syntax
task ansible:check
task ansible:apply
```

## Secrets

Host secrets live in `group_vars/*.sops.yml` and are encrypted with the repo SOPS age recipient.

Before applying to the VPS or connector, replace the placeholder WireGuard values:

```sh
sops ansible/group_vars/vps.sops.yml
sops ansible/group_vars/connector.sops.yml
```

Install WireGuard tools locally, then generate keypairs with `wg`:

```sh
wg genkey | tee /tmp/gw0-wg.key | wg pubkey > /tmp/gw0-wg.pub
wg genkey | tee /tmp/connector-wg.key | wg pubkey > /tmp/connector-wg.pub
```

## Nexus production host

`nexus-kb` (`10.10.40.23`, SSH user `ubuntu`) is in the `nexus_kb` group.
After OpenTofu provisions it, run from this directory:

```sh
ansible-playbook --syntax-check site.yml
ansible-playbook site.yml --limit nexus-kb --diff
ansible-playbook site.yml --limit nexus-kb --check --diff
```

The play requires Ubuntu 24.04 amd64 and reuses the common UTC, chrony,
unattended-upgrades, and SSH-hardening baseline. It installs `git`, `curl`,
`openssl`, and Ubuntu Universe's `grokmirror` package (Noble provides `2.0.11-2`),
plus the QEMU guest agent. The official Ubuntu cloud image enables Universe.
Docker Engine (`docker-ce`), CLI, containerd, Buildx, and Compose come from
[Docker's official apt repository](https://docs.docker.com/engine/install/ubuntu/).
Docker and containerd are enabled at boot and started. Docker access uses `sudo`.

The `nexus` role checks out the revision pinned in `group_vars/nexus_kb.yml` at
`/opt/nexus/app`, builds revision-tagged images, starts ParadeDB/PostgreSQL, checks
migration checksums, and starts the API, worker, and web containers. It installs
the infrastructure-owned mirror configuration and a four-hour cron schedule. The web
listener is bound to `127.0.0.1:8080`; PostgreSQL binds to `127.0.0.1:5432`.
This role does not manage ingress. A separately configured Cloudflare tunnel
currently forwards `app.nexus-kb.com` to the localhost web listener.
The production disk intentionally remains 400 GiB.
This group does not load connector/VPS WireGuard secrets or routing roles.

`roles/nexus/files/grokmirror.conf` is the source of truth for the ten retained
Linux mailing lists. It deliberately excludes `/git/*`, even when deploying an
older application revision whose bundled configuration includes Git. Polling uses
cron, without a socket listener or purge option. `/opt/nexus/lore/git` may remain
offline as rollback data; do not confuse it with `/opt/nexus/mainline.git`, which
continues tracking Linux mainline. Maintenance reads the database's registered
mailing lists, not arbitrary archive directories on disk.

The production database password and shared admin bearer token are in
`group_vars/nexus_kb.sops.yml`. The `admin_token` must be 64 lowercase hexadecimal
characters, generated with `openssl rand -hex 32`. Both the API and worker receive
it as `NEXUS_ADMIN_TOKEN`; all `/api/v1/admin/` routes require the bearer token.
Public read APIs and health checks remain unauthenticated.

The play decrypts secrets with `community.sops` and stages protected files under
`/opt/nexus/.deploy`, outside the Docker build context, with `no_log`. It builds
images before taking `/run/lock/nexus-grokmirror.lock` (waiting up to ten minutes).
Under that lock, `/usr/local/sbin/nexus-deploy` installs root-owned, mode-0600
`/opt/nexus/nexus.env` and `/etc/default/nexus`, installs the matching maintenance
script, runs migrations, and brings the stack up. It then checks the public API,
unauthenticated admin rejection, and an authenticated read-only admin GET before
releasing the lock. Both maintenance POSTs pass the bearer header to curl on stdin,
never as a command argument. No maintenance jobs are enqueued by the rollout check.

To rotate the admin token, update the encrypted value and rerun the play; do not
edit either active credentials file independently. Run one deployment per host
at a time. A failed rollout may have installed new files or partially restarted
containers; inspect service state and rerun the play to converge under the lock.
There is no automatic rollback. Changing `postgres_password` alone does not rotate
an existing PostgreSQL role's password; coordinate that separately with the database.

To rebuild both application images without Docker's build cache and recreate the
server, worker, and web containers, run:

```sh
ansible-playbook site.yml --limit nexus-kb -e nexus_force_rebuild=true
```

The database container is not force-recreated. Omit this flag for normal,
idempotent deployments; the server and worker share the same application image.

### Initial restore from dev

On an empty host, provision the database and build images without starting
application writers or scheduling mirror updates:

```sh
ansible-playbook site.yml --limit nexus-kb -e nexus_app_enabled=false
```

This is an initial-provisioning switch, not a maintenance stop command for an
already-running application. Restore and verify data before the normal apply.

- Use PostgreSQL 18's `pg_dump` custom format with the matching ParadeDB version
  from the pinned application's Compose file. Do not copy a running database's
  data directory. A consistent exported snapshot can be shared between `pg_dump`
  and source row-count queries for exact post-restore comparison.
- Start a fresh `grok-pull -c /opt/nexus/lore/grokmirror.conf` on production under
  `/run/lock/nexus-grokmirror.lock`, and clone Linux mainline as a bare repository
  at `/opt/nexus/mainline.git`. These upstream fetches can run while the database
  dump transfers. Fetching archives is separate from re-ingesting messages.
- Keep checksums of the dump, migration ledger, and table counts, and verify them
  after transfer.
- Restore into a new database created with `TEMPLATE template0`, using
  `pg_restore --exit-on-error --no-owner --no-acl`. The image's initialized database
  already contains extensions; restoring into a clean database avoids collisions.
  Keep the application stopped while checking row counts, migration checksums,
  search indexes, and mainline state, then switch the verified database to `nexus`.
- Wait for the upstream fetches to finish before activating application workers.
  The role requires an existing bare mainline repository; it deliberately does not
  trigger a fresh ingestion.

Run the normal play to verify/apply migrations and activate the application and
cron. Then run check mode and inspect
`sudo docker compose --env-file /opt/nexus/nexus.env ps` from `/opt/nexus/app`.
Check `/healthz`, `/api/v1/mailing-lists`, and search through the localhost listener.
Use an SSH tunnel for remote review rather than changing the bind address:

```sh
ssh -N -L 8080:127.0.0.1:8080 ubuntu@10.10.40.23
```

The one-time seed backup is not an automated backup policy. Off-host scheduled
backups, retention, monitoring, and Cloudflare ingress management remain separate
work. Localhost binding alone does not protect routes forwarded by a tunnel.
The application enforces admin authentication; an additional ingress restriction
on `/api/v1/admin/` can provide defense in depth without changing local maintenance.

Check mode is most useful after the first successful apply because a fresh VM
does not yet have Docker's repository/package metadata.
