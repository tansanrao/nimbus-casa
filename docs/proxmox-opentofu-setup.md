# Proxmox OpenTofu Setup

One-time Proxmox host preparation for managing VMs from this repository with OpenTofu and the `bpg/proxmox` provider.

## Enable Storage Content Types

In the Proxmox UI, go to:

```text
Datacenter -> Storage -> local -> Edit
```

Make sure `Content` includes:

```text
Import
Snippets
```

`Import` is required for downloading Ubuntu cloud images. `Snippets` is required for custom cloud-init user-data and network-config.

If you use a datastore other than `local` for images or snippets, enable the matching content type on that datastore and set `image_datastore_id` or `snippets_datastore_id` in `opentofu/proxmox/terraform.tfvars`.

## Create API User And Token

SSH to the Proxmox node as `root`.

```sh
pveum user add terraform@pve
pveum aclmod / -user terraform@pve -role Administrator
pveum user token add terraform@pve provider --privsep=0
```

Copy the token value immediately. Proxmox only shows it once.

Use `Administrator` for the initial connector deployment to prove the flow works. After deployment, this can be tightened to a narrower custom role.

The local environment variable will look like:

```sh
export PROXMOX_VE_API_TOKEN='terraform@pve!provider=TOKEN_VALUE_HERE'
```

## Create SSH User For Snippets

The provider uses the Proxmox API for VM lifecycle, but Proxmox does not expose snippet upload through the API. BPG uploads snippets over SSH/SFTP using a PAM Linux account on the Proxmox node.

On the Proxmox node:

```sh
apt update
apt install -y sudo

useradd -m -s /bin/bash terraform
mkdir -p /home/terraform/.ssh
```

Add your workstation public key:

```sh
nano /home/terraform/.ssh/authorized_keys
```

Then fix ownership and permissions:

```sh
chown -R terraform:terraform /home/terraform/.ssh
chmod 700 /home/terraform/.ssh
chmod 600 /home/terraform/.ssh/authorized_keys
```

## Add Passwordless Sudo For Provider SSH Operations

Create a sudoers file:

```sh
visudo -f /etc/sudoers.d/terraform-opentofu
```

For the default `local` snippets datastore, add:

```text
terraform ALL=(root) NOPASSWD: /usr/sbin/pvesm
terraform ALL=(root) NOPASSWD: /usr/sbin/qm
terraform ALL=(root) NOPASSWD: /usr/bin/tee /var/lib/vz/snippets/[a-zA-Z0-9_][a-zA-Z0-9_.-]*
```

If the snippets datastore is not `local`, find its path:

```sh
pvesh get /storage/<storage-name>
```

Then add a matching `tee` rule for that datastore, for example:

```text
terraform ALL=(root) NOPASSWD: /usr/bin/tee /mnt/pve/<storage-name>/snippets/[a-zA-Z0-9_][a-zA-Z0-9_.-]*
```

Do not use broad wildcard paths like `/var/lib/vz/*` in sudoers.

## Verify SSH And Sudo

From your workstation:

```sh
ssh terraform@10.10.1.20 'sudo -n /usr/sbin/pvesm apiinfo'
```

Verify the exact snippet write path. For the default `local` datastore:

```sh
printf 'ok\n' | ssh terraform@10.10.1.20 'sudo -n /usr/bin/tee /var/lib/vz/snippets/opentofu-write-test.txt >/dev/null'
ssh root@10.10.1.20 'rm -f /var/lib/vz/snippets/opentofu-write-test.txt'
```

## Export Local Environment Variables

From your workstation:

```sh
export PROXMOX_VE_ENDPOINT='https://10.10.1.20:8006/'
export PROXMOX_VE_API_TOKEN='terraform@pve!provider=TOKEN_VALUE_HERE'
export PROXMOX_VE_INSECURE=true
export PROXMOX_VE_SSH_USERNAME='terraform'
export PROXMOX_VE_SSH_AGENT=true
```

Make sure your SSH key is loaded:

```sh
ssh-add -l
```

## Smoke Test

From the repository root:

```sh
mise exec -- task opentofu:validate
mise exec -- task opentofu:plan
```

The plan should show:

- one Ubuntu 26.04 cloud image download
- one cloud-init user-data snippet
- one cloud-init network-config snippet
- one `connector0` VM

If the plan succeeds, Proxmox is ready for:

```sh
tofu -chdir=opentofu/proxmox apply
```
