# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Kubernetes cluster template based on Talos Linux with GitOps using Flux. The repository provides a complete home lab setup with infrastructure as code.

## Architecture

### Core Technologies
- **Talos Linux**: Immutable Linux OS for Kubernetes nodes
- **Flux**: GitOps continuous delivery for Kubernetes
- **Cilium**: CNI for networking and security
- **SOPS**: Secret encryption with age keys
- **External Secrets**: Uses 1password as a source for secrets
- **Cloudflare**: DNS and tunneling

### Directory Structure
```
├── .taskfiles/         # Task definitions
├── bootstrap/         # Bootstrap scripts and configs
├── kubernetes/        # Kubernetes manifests organized by namespace
│   ├── apps/         # Application deployments by namespace
│   ├── components/   # Reusable components (volsync, common)
│   └── flux/         # Flux system configuration
├── scripts/          # Shell scripts for automation
└── talos/           # Talos cluster configuration
```

### Kubernetes Apps Organization
Apps are organized by namespace:
- `cert-manager/`: Certificate management
- `database/`: Database services (postgres, dragonfly)
- `default/`: User applications (immich, jellyfin, authentik, etc.)
- `external-secrets/`: Secret management
- `flux-system/`: GitOps system
- `kube-system/`: Core cluster services
- `media/`: Media server stack (sonarr, radarr, jellyfin, etc.)
- `network/`: Networking services (cloudflare, vpn, k8s-gateway)
- `observability/`: Monitoring stack (prometheus, grafana, loki)

## Development Commands

### Task Commands (using Taskfile)
**Talos cluster management:**
- `task talos:generate-config` - Generate Talos configuration
- `task talos:apply-node IP=<node-ip> MODE=<mode>` - Apply config to specific node
- `task talos:upgrade-node IP=<node-ip>` - Upgrade Talos on single node
- `task talos:upgrade-k8s` - Upgrade Kubernetes version

**Flux management:**
- `task reconcile` - Force Flux to reconcile with Git repository

### Environment Setup
1. Install mise: follow instructions at https://mise.jdx.dev/getting-started.html
2. Run `mise trust` then `mise install` to install all tools
3. Ensure SOPS age key is present at `age.key`

### Configuration Files
- `talconfig.yaml` - Talos cluster configuration

### Secret Management
- Secrets configured through external-secrets using 1password vault as source. Credentials for external-secrets encrypted using SOPS.
- Age key stored in `age.key` file (gitignored)
- SOPS config in `.sops.yaml`
- Encrypted files have `.sops.yaml` extension

### Flux Structure
- Flux system configured in `kubernetes/flux/`
- Apps deployed via Kustomization resources (ks.yaml files)
- Each app has its own namespace and kustomization
- HelmReleases and standard Kubernetes manifests supported

### Common Debugging Commands
- `flux check` - Check Flux system status
- `flux get sources git -A` - Check git sources
- `flux get ks -A` - Check kustomizations
- `flux get hr -A` - Check helm releases
- `kubectl get pods --all-namespaces` - Check pod status
- `cilium status` - Check Cilium networking

## Key instructions
- ALWAYS Check online for changelogs when planning upgrades
- Check other Home-ops repositories on github when adding new applications
- Follow current practices in the repository such as using volsync for
  persistent storage, adding a DB to the cloudnative-postgres instance, syncing
  secrets from 1password through external secrets, exposing traffic through
  Gateway API HTTP Routes for external and internal URLs, exposing traffic
  through tailscale using the nginx-ingress for tailscale.
