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
