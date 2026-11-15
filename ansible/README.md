# Ansible

Configures the hosts outside Kubernetes. All of them run UTC.

| Group | Host | Roles |
| --- | --- | --- |
| `vps` | `gw0.kiad.tansanrao.net` (user `root`) | common, firewall, wireguard, haproxy, gatus |
| `connector` | `connector0`, `10.10.40.21` (user `ubuntu`) | common, firewall, wireguard, haproxy |
| `nexus_kb` | `nexus-kb`, `10.10.40.23` (user `ubuntu`) | common, docker, nexus |
| `gitlab` | `gitlab0`, `10.10.40.24` port 2022 (user `ubuntu`) | common, firewall, haproxy, gitlab |

The VPS also runs `floating_ip`, which keeps GitLab's Floating IP on `eth0`.

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

## gitlab0

The `gitlab` role installs the pinned `gitlab_version` of `gitlab-ee` from GitLab's apt repository and holds the package. To upgrade, follow GitLab's required upgrade stops, change `gitlab_version` one stop at a time and rerun the play. The role mounts the data disk at `/var/opt/gitlab`, adds a 4 GiB swap file, renders `/etc/gitlab/gitlab.rb`, and applies instance settings that live in the database (sign-ups off, private by default). Nightly `gitlab-backup` runs at 02:00 and keeps two days of local backups.

HAProxy (`haproxy_role: forwards`) owns ports 22, 80 and 443 for direct clients and 10022, 10080 and 10443 for connector0; see `group_vars/gitlab.yml` and the GitLab section of [ARCHITECTURE.md](../ARCHITECTURE.md). Use `ssh -p 2022 ubuntu@10.10.40.24` for administration.

Secrets in `group_vars/gitlab.sops.yml`:

- `root_password`: the initial root password. Changing it later does not change the account.
- `gitlab_secrets_json`: `/etc/gitlab/gitlab-secrets.json`. A backup cannot be restored without it.
- `sshd_host_keys`: the `gitlab-sshd` host keys, so a rebuild keeps the same fingerprints.
- `smtp_username` and `smtp_password` (optional): Helo SMTP credentials. When present, GitLab sends mail through `smtp.helohq.com:587` with STARTTLS as `noreply@twicecooked.software`.
- `garage` (optional): `{endpoint, access_key, secret_key}`. When present, the role uploads backups to `gitlab-backups` and moves the registry, artifacts, LFS, uploads, packages and Dependency Proxy to `gitlab-*` buckets on Garage, with every download proxied through GitLab.

The Garage key is named `gitlab0`. It has read and write, but not owner, on the ten `gitlab-*` buckets and cannot create buckets. Garage has no prefix policies, so a new bucket needs its own grant. It was created with the Garage admin API on `http://10.10.40.10:30190` (`/v2/CreateKey`, `/v2/CreateBucket`, `/v2/AllowBucketKey`). To rotate it, create a new key with the same grants, update `garage` in SOPS, rerun the play, then delete the old key.

`gitlab-backups` has a lifecycle rule, `expire-backups-after-14-days`, that deletes backups 14 days after upload and aborts multipart uploads left incomplete for a day. gitlab0 keeps two days of local copies. The rule lives in Garage, not in this repository, and only a bucket owner can change it, which the `gitlab0` key is not. To change it, create a temporary key with owner on `gitlab-backups`, send `PUT /gitlab-backups?lifecycle` with a `Content-MD5` header, then delete the key.
