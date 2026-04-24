# Proxmox OpenTofu

OpenTofu configuration for Proxmox-managed Nimbus Casa VMs.

The first managed VM is the home connector:

- `connector0`
- Ubuntu Server 26.04 LTS rolling current cloud image
- `10.10.40.21/24`
- `2 vCPU / 2 GiB RAM / 20 GiB disk`
- custom cloud-init user-data and network-config snippets

## Prerequisites

Enable these content types on the configured Proxmox datastores:

- `Import` on the image datastore for `proxmox_download_file`
- `Snippets` on the snippets datastore for custom cloud-init user-data and network-config

The `bpg/proxmox` provider reads Proxmox credentials from environment variables:

```sh
export PROXMOX_VE_ENDPOINT='https://10.10.1.20:8006/'
export PROXMOX_VE_API_TOKEN='terraform@pve!provider=...'
export PROXMOX_VE_INSECURE=true
```

Custom cloud-init snippets require SSH access to the Proxmox node. With API token auth, also provide SSH access through the provider environment variables:

```sh
export PROXMOX_VE_SSH_USERNAME='terraform'
export PROXMOX_VE_SSH_AGENT=true
```

## Commands

```sh
tofu init
tofu fmt -check -recursive
tofu validate
tofu plan
```

From the repository root, the same checks are available through Taskfile:

```sh
task opentofu:fmt
task opentofu:validate
task opentofu:plan
```
