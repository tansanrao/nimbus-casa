# OpenEBS LVM Bootstrap

This cluster uses a single Talos raw volume backed by the non-system NVMe and exposed as `/dev/disk/by-partlabel/r-openebs-lvm`.
The Talos machine config in this repo also loads the `dm_snapshot` and `dm_thin_pool` kernel modules at boot so OpenEBS LVM can support snapshot-based VolSync backup and restore on thin-provisioned volumes.

## Storage classes

- `openebs-lvm` is the thin-provisioned class used for all OpenEBS LVM-backed workloads in this repo.
- `openebs-lvm-snap` remains the `VolumeSnapshotClass` used by VolSync when `copyMethod: Snapshot` is enabled.

## One-time bootstrap

1. Verify Talos created the raw volume:

   ```sh
   talosctl get volumestatus r-openebs-lvm -n 10.10.40.40
   talosctl read /dev/disk/by-partlabel/r-openebs-lvm -n 10.10.40.40 >/dev/null
   ```

2. Verify the `dm_snapshot` and `dm_thin_pool` kernel modules are loaded on the host:

   ```sh
   talosctl read /proc/modules -n 10.10.40.40 | grep dm_snapshot
   talosctl read /proc/modules -n 10.10.40.40 | grep dm_thin_pool
   ```

   If either command is empty, regenerate and apply the Talos config from this repo and reboot the node before continuing.

3. Start a privileged node debug shell on `k8s0` and install the LVM userspace tools in the debug container:

   ```sh
   kubectl debug node/k8s0 -it --image=debian:12-slim --profile=sysadmin -- sh
   apt-get update
   apt-get install -y lvm2 util-linux
   mount --rbind /host/dev /dev
   mkdir -p /run/udev
   mount --rbind /host/run/udev /run/udev || true
   ls -l /dev/disk/by-partlabel/r-openebs-lvm
   ```

   `kubectl debug node` mounts the host root at `/host`, but LVM only scans the container's `/dev` by default. Running `pvcreate` directly against `/host/dev/...` fails with `No device found`. Entering the host mount namespace with `nsenter` also fails because Talos does not provide `ls`, `pvcreate`, or the other LVM userspace tools on the host rootfs. Rebinding the host device tree into the container keeps the Debian tools available while exposing the real host block devices at `/dev`.

4. Create the physical volume and volume group from inside the debug shell:

   ```sh
   pvcreate /dev/disk/by-partlabel/r-openebs-lvm
   vgcreate openebs-vg /dev/disk/by-partlabel/r-openebs-lvm
   vgs
   pvs
   ```

5. Exit the debug shell and remove the temporary debugger pod:

   ```sh
   exit
   kubectl get pods -A | grep node-debugger-k8s0
   kubectl delete pod -n default <node-debugger-pod-name>
   ```

6. Verify OpenEBS can see the volume group and provision storage:

   ```sh
   kubectl -n openebs-system get pods
   kubectl get sc openebs-lvm
   kubectl get volumesnapshotclass openebs-lvm-snap
   ```

Once `openebs-vg` exists, the durable workloads in this repo can bind their PVCs on `openebs-lvm`.

## VolSync backup and restore flow

VolSync in this repo defaults to `copyMethod: Snapshot` and uses `openebs-lvm` for the source PVC, destination PVC, and restore PVC it manages. The expected flow is:

1. The app PVC is provisioned on `openebs-lvm`.
2. `ReplicationSource` creates a CSI snapshot using `openebs-lvm-snap`.
3. VolSync mounts the snapshot-backed temporary PVC and pushes data to restic.
4. `ReplicationDestination` restores the latest data to a PVC on `openebs-lvm`.

Keep the VolSync cache PVCs on `openebs-hostpath`; they do not need LVM snapshots.

## Cutover note

This repo now assumes a fresh thin-only bootstrap. The single `openebs-lvm` StorageClass is thin-provisioned, and the old thick-provisioned class definition has been removed from the repo.

## Thin-pool monitoring note

OpenEBS 4.4 adds Local PV LVM snapshot restore support, but thin-pool accounting still has limitations. Monitor thin-pool usage on `openebs-vg` and extend capacity before the pool fills.
