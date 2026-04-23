# Nimbus Casa Infrastructure

Infrastructure-as-code for Nimbus Casa.

The target architecture is documented in [ARCHITECTURE.md](./ARCHITECTURE.md). In short: a Hetzner VPS public edge, WireGuard backhaul, HAProxy routing, Flux-managed Kubernetes, and Ansible-managed host configuration.

## Repository Layout

- `ansible/`: host configuration for infrastructure machines. The first target is the Hetzner VPS edge, `gw0.kiad.tansanrao.net`.
- `kubernetes/`: Flux-managed Kubernetes apps, components, and cluster reconciliation state.
- `talos/`: Talos Linux machine configuration for the Kubernetes node.
- `bootstrap/`: one-time bootstrap resources for cluster setup.
- `.taskfiles/`: Taskfile modules for repeatable local operations.

## Tooling

Local tools are managed with [mise](https://mise.jdx.dev/).

```sh
mise trust
mise install
```

Secrets are managed with [SOPS](https://github.com/getsops/sops) and age. The expected local age key path is `age.key`

## Ansible

The VPS edge configuration lives under `ansible/`.

```sh
task ansible:inventory
task ansible:syntax
task ansible:check
task ansible:apply
```

Encrypted VPS variables live in:

```sh
ansible/group_vars/vps.sops.yml
```

Before applying the VPS playbook, replace the placeholder WireGuard keys:

```sh
sops ansible/group_vars/vps.sops.yml
```

Install WireGuard tools locally, then generate keys with `wg`:

```sh
wg genkey | tee /tmp/gw0-wg.key | wg pubkey > /tmp/gw0-wg.pub
```

All Ansible-managed infrastructure hosts should run UTC unless a host has an explicit documented exception.

## Kubernetes

Flux is the source of truth for Kubernetes workloads and cluster apps.

Useful checks:

```sh
flux check
flux get sources git -A
flux get ks -A
flux get hr -A
```

Force Flux to reconcile from Git:

```sh
task reconcile
```

## Talos

Talos tasks are kept under the `talos:` namespace.

```sh
task talos:generate-config
task talos:apply-node IP=? MODE=?
task talos:upgrade-node IP=?
task talos:upgrade-k8s
```

## Notes

- Cloudflare remains DNS-only in the target architecture.
- Public ingress should move through the Hetzner VPS edge rather than Cloudflare Tunnel.
- `kubernetes/` contains cluster desired state; `ansible/` contains host desired state.
- Keep secrets out of Terraform/OpenTofu state and unencrypted YAML.
