# Ansible

Configures the hosts outside Kubernetes. All of them run UTC.

| Group | Host | Roles |
| --- | --- | --- |
| `vps` | `gw0.kiad.tansanrao.net` (user `root`) | common, firewall, wireguard, haproxy, gatus |
| `connector` | `connector0`, `10.10.40.21` (user `ubuntu`) | common, firewall, wireguard, haproxy |
| `nexus_kb` | `nexus-kb`, `10.10.40.23` (user `ubuntu`) | common, docker, nexus |

The `common` role sets the hostname, timezone, chrony, unattended-upgrades and SSH hardening. [ARCHITECTURE.md](../ARCHITECTURE.md) describes the VPS and connector traffic path.

## Commands

From the repository root:

```sh
task ansible:inventory
task ansible:syntax
task ansible:check
task ansible:apply
```

To target one host, run `ansible-playbook site.yml --limit <host> --diff` from this directory.

The controller uses Python 3.14, the newest version Ansible Core 2.21 supports. After changing the Python minor version, rebuild the Python tools:

```sh
mise install
mise install --force pipx:ansible-core pipx:makejinja
```

## Secrets

Each group's secrets are in `group_vars/<group>.sops.yml`, encrypted with the repository's age recipient. Edit them with `sops`.

To rotate a WireGuard key pair, generate it with `wg genkey | tee key | wg pubkey > key.pub`. Put the private key in that host's file and the public key in the peer's file (`wireguard_vps_*` and `wireguard_connector_*`). Then apply both hosts.

## nexus-kb

The play requires Ubuntu 24.04 amd64 and waits for cloud-init to finish. Docker Engine, containerd, Buildx and Compose come from [Docker's apt repository](https://docs.docker.com/engine/install/ubuntu/). Use `sudo` for Docker.

The `nexus` role checks out `nexus_revision` from `group_vars/nexus_kb.yml` into `/opt/nexus/app` and builds images tagged with that revision. It then starts ParadeDB, runs migrations and starts the API, worker and web containers. The web listener binds to `127.0.0.1:8080` and PostgreSQL to `127.0.0.1:5432`. To reach the web listener from a workstation, use `ssh -N -L 8080:127.0.0.1:8080 ubuntu@10.10.40.23`.

The role does not manage ingress. A Cloudflare tunnel, configured separately, forwards `app.nexus-kb.com` to the web listener.

Mailing lists are mirrored with `grokmirror` every four hours from cron. `roles/nexus/files/grokmirror.conf` lists the ten mirrored Linux lists and excludes `/git/*`. `/opt/nexus/mainline.git` tracks Linux mainline. The old `/opt/nexus/lore/git` directory is kept offline as rollback data.

Secrets in `group_vars/nexus_kb.sops.yml`:

- `postgres_password`. Changing it does not change the password of an existing PostgreSQL role; change that in the database as well.
- `admin_token`: 64 lowercase hex characters from `openssl rand -hex 32`. The API and worker receive it as `NEXUS_ADMIN_TOKEN`, and every `/api/v1/admin/` route requires it. To rotate it, change the value and rerun the play.

Deployments run under `/run/lock/nexus-grokmirror.lock`. The deploy script installs `/opt/nexus/nexus.env` and `/etc/default/nexus` (root, mode 0600), runs migrations and starts the stack. It then checks the public API, that the admin API rejects requests without a token, and that it accepts the token. There is no automatic rollback. If a deploy fails, check the containers and rerun the play.

Optional flags:

- `-e nexus_force_rebuild=true` rebuilds the application images without cache and recreates the server, worker and web containers. The database container is left alone.
- `-e nexus_app_enabled=false` is for first provisioning. It creates the database and images but starts no application containers and no cron job. It does not stop a running deployment.

Check mode fails on a fresh VM until the first apply has added Docker's apt repository.

### Restoring the database onto a new host

1. Apply with `nexus_app_enabled=false`.
2. Dump the source with PostgreSQL 18 `pg_dump -Fc`, using the ParadeDB version from the pinned Compose file. Don't copy a live data directory. Record checksums and table row counts.
3. While the dump transfers, run `grok-pull -c /opt/nexus/lore/grokmirror.conf` under the lock and clone Linux mainline as a bare repository at `/opt/nexus/mainline.git`. The role expects that repository to exist.
4. Restore into a new database created from `template0` with `pg_restore --exit-on-error --no-owner --no-acl`. Check row counts, migration checksums and search indexes, then rename it to `nexus`.
5. Run the normal play, then check `/healthz`, `/api/v1/mailing-lists` and search through the local listener.

Scheduled off-host backups and monitoring for `nexus-kb` are not set up.
