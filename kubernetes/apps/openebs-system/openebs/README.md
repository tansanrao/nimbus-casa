# OpenEBS LVM Bootstrap

This cluster uses a single Talos raw volume backed by the non-system NVMe and exposed as `/dev/disk/by-partlabel/r-openebs-lvm`.
The Talos machine config in this repo also loads the `dm_snapshot` kernel module at boot for OpenEBS LVM snapshot support.

## One-time bootstrap

1. Verify Talos created the raw volume:

   ```sh
   talosctl get volumestatus r-openebs-lvm -n 10.10.40.40
   talosctl read /dev/disk/by-partlabel/r-openebs-lvm -n 10.10.40.40 >/dev/null
   ```

2. Verify the `dm_snapshot` kernel module is loaded on the host:

   ```sh
   talosctl read /proc/modules -n 10.10.40.40 | grep dm_snapshot
   ```

   If this is empty, regenerate and apply the Talos config from this repo and reboot the node before continuing.

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
