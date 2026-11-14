# Nimbus Casa

Infrastructure as code for the Nimbus Casa homelab: a single-node Talos Kubernetes cluster managed by Flux, plus the VMs and the Hetzner VPS around it. [ARCHITECTURE.md](ARCHITECTURE.md) describes the hosts, network, ingress path and databases.

## Layout

| Path | Contents |
| --- | --- |
| `kubernetes/` | Flux apps, shared components and cluster settings |
| `talos/` | talhelper configuration and patches for `k8s0` |
| `bootstrap/` | One-time cluster bootstrap resources |
| `opentofu/proxmox/` | VMs created on Proxmox (`connector0`, `nexus-kb`) |
| `ansible/` | Configuration for the VPS, `connector0` and `nexus-kb` |
| `scripts/` | Static checks and live verification scripts |
| `docs/` | Runbooks and isolation notes |
| `.taskfiles/` | Taskfile modules for `bootstrap:` and `talos:` |

## Setup

Tools are pinned in `.mise.toml`:

```sh
mise trust
mise install
```

SOPS decrypts secrets with the age key at `age.key`. The Taskfile sets `KUBECONFIG`, `SOPS_AGE_KEY_FILE` and `TALOSCONFIG` from the repository root.

## Common tasks

```sh
task reconcile                 # Flux pulls the latest commit
task talos:generate-config
task talos:apply-node IP=? MODE=?
task talos:upgrade-node IP=?
task talos:upgrade-k8s
task opentofu:plan             # also: fmt, validate, apply
task ansible:check             # also: inventory, syntax, apply
```

Checks that need no cluster access:

```sh
python3 scripts/check-workload-isolation.py
python3 scripts/check-postgres.py
```

Run `scripts/check-postgres.py --live` and the `scripts/verify-*.py` scripts against the live cluster.

## Docs

- [Workload isolation](docs/workload-isolation.md)
- [Karakeep browser isolation](docs/karakeep-isolation.md)
- [OpenEBS LVM and VolSync](kubernetes/apps/openebs-system/openebs/README.md)
- [Intel GPU](kubernetes/apps/kube-system/intel-gpu-plugin/README.md)
- [Proxmox and OpenTofu](opentofu/proxmox/README.md)
- [Ansible hosts](ansible/README.md)
