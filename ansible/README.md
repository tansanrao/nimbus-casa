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

The command-line tools need no services. Grokmirror is installed, but scheduling
mirrors requires repository URLs and a mirror configuration, which this handoff
does not supply. No Nexus application containers or public ingress are deployed.
This group does not load the connector/VPS WireGuard secrets or routing roles.

Check mode is most useful after the first successful apply because a fresh VM
does not yet have Docker's repository/package metadata.
