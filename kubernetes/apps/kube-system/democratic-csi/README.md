# democratic-csi on Rocky Linux 10 (OpenZFS over SSH)

This stack uses:
- `zfs-generic-nfs` over SSH
- `zfs-generic-nvmeof` over SSH

Storage classes:
- `rocky-nfs`
- `rocky-nvmeof`

Snapshot class:
- `rocky-nvmeof-snap`

## 1) Rocky host preparation

Install OpenZFS and required packages:

```bash
sudo dnf install -y https://zfsonlinux.org/epel/zfs-release-2-3$(rpm --eval "%{dist}").noarch.rpm
sudo dnf install -y epel-release
sudo dnf install -y kernel-devel zfs
sudo dnf install -y openssh-server nfs-utils nvmetcli nvme-cli sudo
```

Enable services and NVMe target support:

```bash
sudo systemctl enable --now sshd
sudo systemctl enable --now nfs-server
sudo mkdir -p /etc/nvmet

printf "nvmet\nnvmet-tcp\n" | sudo tee /etc/modules-load.d/nvmet.conf
sudo modprobe nvmet
sudo modprobe nvmet-tcp

# nvmet.service fails if config.json is empty or invalid JSON
sudo sh -c 'test -s /etc/nvmet/config.json || echo "{}" > /etc/nvmet/config.json'
sudo nvmetcli save /etc/nvmet/config.json
sudo systemctl enable --now nvmet
```

Create dedicated SSH user:

```bash
sudo useradd -m -s /bin/bash democratic-csi
sudo mkdir -p /home/democratic-csi/.ssh
sudo chmod 700 /home/democratic-csi/.ssh
sudo touch /home/democratic-csi/.ssh/authorized_keys
sudo chmod 600 /home/democratic-csi/.ssh/authorized_keys
sudo chown -R democratic-csi:democratic-csi /home/democratic-csi/.ssh
```

Grant sudo for storage commands (tighten later if desired):

```bash
echo 'democratic-csi ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/democratic-csi
sudo chmod 440 /etc/sudoers.d/democratic-csi
```

Import and verify ZFS pool:

```bash
sudo zpool import
sudo zpool import <poolname>
zfs list
```

Open firewall ports:

```bash
sudo firewall-cmd --permanent --add-port=2049/tcp
sudo firewall-cmd --permanent --add-port=4420/tcp
sudo firewall-cmd --reload
```

## 2) Required ExternalSecret keys (`democratic-csi` item)

Shared SSH:
- `ROCKY_SSH_HOST`
- `ROCKY_SSH_PORT`
- `ROCKY_SSH_USER`
- `ROCKY_SSH_PRIVATE_KEY`
- `ROCKY_SSH_HOST_PUBLIC_KEY`

NFS:
- `ROCKY_NFS_DATASET_PARENT`
- `ROCKY_NFS_SNAPSHOT_PARENT`
- `ROCKY_NFS_SHARE_HOST`
- `ROCKY_NFS_ALLOWED_NETWORK`

NVMe-oF:
- `ROCKY_NVME_DATASET_PARENT`
- `ROCKY_NVME_SNAPSHOT_PARENT`
- `ROCKY_NVME_SHARE_HOST`
- `ROCKY_NVME_TRANSPORT` (for example: `tcp`)
- `ROCKY_NVME_PORT_ID` (for example: `1`)

## 3) Validation checklist

Host checks:

```bash
ssh democratic-csi@<rocky-host> sudo zfs list
ssh democratic-csi@<rocky-host> sudo nvmetcli ls
ssh democratic-csi@<rocky-host> sudo exportfs -v
```

Cluster checks:
- Create test PVC using `rocky-nvmeof`; verify pod read/write.
- Create test PVC using `rocky-nfs`; verify pod read/write.
- Create and restore a snapshot with `rocky-nvmeof-snap`.

## 4) Troubleshooting

If `nvmet.service` fails with `JSONDecodeError`, recreate a valid config:

```bash
sudo mkdir -p /etc/nvmet
echo '{}' | sudo tee /etc/nvmet/config.json
sudo nvmetcli save /etc/nvmet/config.json
sudo systemctl restart nvmet
sudo systemctl status nvmet --no-pager
```

If `nvmetcli ls` shows no ports, create one (example `portid=1` for `tcp/4420`):

```bash
sudo nvmetcli
# In the interactive shell:
cd /ports
create portid=1
cd 1
set addr adrfam=ipv4
set addr trtype=tcp
set addr traddr=<rocky_storage_ip>
set addr trsvcid=4420
cd /
ls
exit

# Persist to disk so nvmet.service can restore on boot
sudo nvmetcli save /etc/nvmet/config.json
sudo systemctl restart nvmet
sudo systemctl status nvmet --no-pager
```

Set these ExternalSecret values to match:
- `ROCKY_NVME_PORT_ID=1`
- `ROCKY_NVME_TRANSPORT=tcp`
- `ROCKY_NVME_SHARE_HOST=<rocky_storage_ip>`

If testing sudo access for the service account, run a command with `-n`:

```bash
sudo -u democratic-csi sudo -n zfs list
sudo -u democratic-csi sudo -n nvmetcli ls
```
