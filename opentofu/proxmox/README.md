# Proxmox VMs

OpenTofu creates two VMs on Proxmox with the `bpg/proxmox` provider. Both use custom cloud-init snippets.

| VM | Image | Address | Size |
| --- | --- | --- | --- |
| `connector0` | Ubuntu 26.04 cloud image | `10.10.40.21/24` | 2 vCPU, 2 GiB RAM, 20 GiB disk |
| `nexus-kb` | Ubuntu 24.04 cloud image | `10.10.40.23/24` | 8 vCPU, 16 GiB RAM, 400 GiB disk |

Local settings go in `terraform.tfvars` (copy `terraform.tfvars.example`). State is kept locally in `terraform.tfstate`. Both files are gitignored.

## Proxmox host setup

This is a one-time setup on the Proxmox node.

Enable the `Import` and `Snippets` content types on the image and snippets datastores (Datacenter → Storage → `local` → Edit). If you use a datastore other than `local`, set `image_datastore_id` or `snippets_datastore_id` to match.

Create the API user and token as `root`. Proxmox shows the token value only once.

```sh
pveum user add terraform@pve
pveum aclmod / -user terraform@pve -role Administrator
pveum user token add terraform@pve provider --privsep=0
```

The provider uploads snippets over SSH because the Proxmox API cannot. Create a `terraform` Linux user, add your public key to `/home/terraform/.ssh/authorized_keys` (directory mode 700, file mode 600), install `sudo`, and add `/etc/sudoers.d/terraform-opentofu` with `visudo -f`:

```text
terraform ALL=(root) NOPASSWD: /usr/sbin/pvesm
terraform ALL=(root) NOPASSWD: /usr/sbin/qm
terraform ALL=(root) NOPASSWD: /usr/bin/tee /var/lib/vz/snippets/[a-zA-Z0-9_][a-zA-Z0-9_.-]*
```

For another snippets datastore, find its path with `pvesh get /storage/<name>` and use that path in the `tee` rule. Don't use a broad wildcard such as `/var/lib/vz/*`.

Check access from your workstation:

```sh
ssh terraform@10.10.1.20 'sudo -n /usr/sbin/pvesm apiinfo'
```

## Usage

Export the provider settings and load your SSH key with `ssh-add`:

```sh
export PROXMOX_VE_ENDPOINT='https://10.10.1.20:8006/'
export PROXMOX_VE_API_TOKEN='terraform@pve!provider=TOKEN_VALUE'
export PROXMOX_VE_INSECURE=true
export PROXMOX_VE_SSH_USERNAME='terraform'
export PROXMOX_VE_SSH_AGENT=true
```

From the repository root:

```sh
task opentofu:validate
task opentofu:plan
task opentofu:apply
```

One plan covers both VMs, so read it before applying. After a VM is created, configure it with Ansible (see [ansible/README.md](../../ansible/README.md)).

## nexus-kb

`nexus-kb` has MAC `02:CA:5A:40:00:23` and FQDN `nexus-kb.kbcb.tansanrao.net`. It starts when Proxmox boots. Its root disk uses discard, I/O threads and SSD emulation, and must sit on an SSD-backed datastore. It inherits `vm_datastore_id` unless `nexus_kb_datastore_id` is set. Cloud-init creates no swap. OpenTofu does not create DNS records. If you change the address, hostname or SSH user, update the Ansible inventory too.

To grow the disk, raise `nexus_kb_disk_gb`, apply, then reboot the guest so cloud-init grows the partition and filesystem. Check with `df -h /`. Never shrink the disk.
