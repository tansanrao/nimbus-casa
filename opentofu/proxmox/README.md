# Proxmox VMs

OpenTofu creates five VMs on Proxmox with the `bpg/proxmox` provider. The Ubuntu VMs use custom cloud-init snippets.

| VM | Image | Address | Size |
| --- | --- | --- | --- |
| `connector0` | Ubuntu 26.04 cloud image | `10.10.40.21/24` | 2 vCPU, 2 GiB RAM, 20 GiB disk |
| `nexus-kb` | Ubuntu 24.04 cloud image | `10.10.40.23/24` | 8 vCPU, 16 GiB RAM, 400 GiB disk |
| `gitlab0` | Ubuntu 24.04 cloud image | `10.10.40.24/24` | 12 vCPU (`host`, CPU units 200), 24 GiB RAM, 40 GiB OS + 300 GiB data disk |
| `runner0` | Talos Image Factory `nocloud` image | `10.10.40.25/24` | 24 vCPU (`host`, CPU units 50), 36 GiB RAM, 200 GiB disk |
| `obs0` | Talos Image Factory `nocloud` image | `10.10.40.26/24` | 2 vCPU (`host`), 12 GiB RAM, 20 GiB system + 100 GiB data disk |

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

One plan covers every VM, so read it before applying. After a VM is created, configure it with Ansible (see [ansible/README.md](../../ansible/README.md)).

## nexus-kb

`nexus-kb` has MAC `02:CA:5A:40:00:23` and FQDN `nexus-kb.kbcb.tansanrao.net`. It starts when Proxmox boots. Its root disk uses discard, I/O threads and SSD emulation, and must sit on an SSD-backed datastore. It inherits `vm_datastore_id` unless `nexus_kb_datastore_id` is set. Cloud-init creates no swap. OpenTofu does not create DNS records. If you change the address, hostname or SSH user, update the Ansible inventory too.

To grow the disk, raise `nexus_kb_disk_gb`, apply, then reboot the guest so cloud-init grows the partition and filesystem. Check with `df -h /`. Never shrink the disk.

## gitlab0

MAC `02:CA:5A:40:00:24`. Cloud-init moves admin OpenSSH to port 2022 before Ansible first connects, because port 22 belongs to `gitlab-sshd`. The data disk on `scsi1` has serial `gitlab-data`; Ansible formats it and mounts it at `/var/opt/gitlab`. Grow either disk the same way as `nexus-kb`.

## runner0

MAC `02:CA:5A:40:00:25`. The disk is imported from a Talos Image Factory image with the `qemu-guest-agent` extension. Proxmox only decompresses downloads into ISO storage, so the image is stored there as an `.img`. That image only bootstraps the VM: upgrade Talos with `talosctl upgrade`, not by changing `runner_talos_image_version`. The NoCloud drive gives Talos its static address in maintenance mode.

`runner.tf` also manages the Proxmox firewall. runner0's VM firewall drops inbound traffic except the Talos and Kubernetes APIs from `runner_admin_sources`, and outbound traffic to every private, CGNAT, link-local and IPv6 destination except `10.10.40.24:443` and gateway DNS. `ipfilter` stops it from sending from any other address. The datacenter firewall has to be on for any VM firewall to apply; it stays on with ACCEPT policies, and the node firewall stays off, so no other guest or the host is filtered.

To bootstrap a rebuilt runner0: `cd talos-runner && talhelper genconfig`, then `talosctl apply-config --insecure -n 10.10.40.25 -e 10.10.40.25 -f clusterconfig/gitlab-runner-runner0.yaml`, `talosctl bootstrap`, `talosctl kubeconfig talos-runner/kubeconfig`, and `task runner:deploy`. A rebuilt runner needs a new runner token from GitLab in `talos-runner/gitlab-runner/runner-token.sops.yaml`.

## obs0

MAC `02:CA:5A:40:00:26`. The monitoring cluster, kept apart from `k8s0` so a failure there does not take monitoring down. It boots the same Image Factory image as runner0 (`qemu-guest-agent` only), downloaded under its own file name. The data disk on `scsi1` has serial `obs0-data`, but Talos cannot read serials from virtio-scsi disks, so the `UserVolumeConfig` in `talos/obs0/talconfig.yaml` selects it as the non-system disk over 90 GB, formats it and mounts it at `/var/mnt/data`. As with runner0, the image only bootstraps the VM, and later image changes are ignored.

Before bootstrapping, set the Cloudflare API token that cert-manager uses for the `*.tansanrao.net` certificate. It needs `Zone:DNS:Edit` on `tansanrao.net` only:

```sh
sops set kubernetes/obs0/apps/cert-manager/cert-manager/app/secret.sops.yaml '["stringData"]["api-token"]' '"<token>"'
```

Then, from the repository root, after `task opentofu:apply`:

```sh
task bootstrap:talos CLUSTER=obs0   # Talos config, etcd bootstrap, talos/obs0/kubeconfig
task bootstrap:apps CLUSTER=obs0    # Cilium, CoreDNS, cert-manager and Flux; Flux syncs kubernetes/obs0
```

unifi-dns starts with `policy: upsert-only`. Once its records in UniFi look right, switch it to `sync` in `kubernetes/obs0/apps/network/unifi-dns/app/helmrelease.yaml`.
