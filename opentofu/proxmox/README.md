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

## Nexus production host

`nexus-kb` uses Ubuntu 24.04 LTS (Noble), 8 vCPU, 16384 MiB dedicated RAM,
and a 400 GiB SCSI root disk with discard, I/O threading, and SSD emulation.
It starts on Proxmox boot. Cloud-init creates no swap and expands the root filesystem.
The disk inherits `vm_datastore_id` (currently `vm-disks` in the local configuration);
`nexus_kb_datastore_id` can override it. The underlying datastore must be SSD-backed.

Network: `10.10.40.23/24`, gateway `10.10.40.1`, MAC `02:CA:5A:40:00:23`,
FQDN `nexus-kb.kbcb.tansanrao.net`. It inherits the shared bridge (currently `vmbr1`),
DNS, Proxmox node, and SSH keys. Keep Ansible inventory/group variables synchronized
if changing its address, hostname, or SSH user. DNS records are not created here.

From this directory, with the provider environment configured:

```sh
tofu init
tofu fmt -check -recursive
tofu validate
tofu plan -out=nexus.tfplan
tofu apply nexus.tfplan
cd ../../ansible
ansible-playbook site.yml --limit nexus-kb --diff
```

Review the plan before applying: this root also manages `connector0`.
Ansible waits for cloud-init, applies the common UTC/SSH baseline, installs host
packages, and starts/enables Docker and containerd. See the Ansible README for scope.

To expand storage, increase `nexus_kb_disk_gb` in your local tfvars, review/apply the
plan, and reboot the guest so cloud-init growpart/resizefs expands the partition and
filesystem. Verify with `lsblk` and `df -h /`. Never decrease the disk size.
