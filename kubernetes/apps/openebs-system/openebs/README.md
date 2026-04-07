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

VolSync in this repo defaults to `copyMethod: Snapshot` for backups. Restores target the live app PVC directly with VolSync's existing-claim restore path. The expected flow is:

1. The app PVC is provisioned on `openebs-lvm`.
2. `ReplicationSource` creates a CSI snapshot using `openebs-lvm-snap`.
3. VolSync mounts the snapshot-backed temporary PVC and pushes data to restic.
4. To restore, scale the consuming app down or suspend its Helm release.
5. `ReplicationDestination` restores the latest data into the existing live PVC on `openebs-lvm`.
6. Wait for the restore to complete, then scale the app back up.

Keep the VolSync cache PVCs on `openebs-hostpath`; they do not need LVM snapshots.

Because restores are now in-place, they overwrite newer filesystem contents on the target PVC. Do not restore while the application is still writing to the volume.

## Backup coverage

This repo has three backup classes for persistent data:

- `VolSync + OpenEBS LVM`: application PVCs that live on `openebs-lvm` and are backed up with restic via VolSync.
- `NFS-backed storage`: workloads like Immich uploads and the media shared store that are backed up at the NAS/storage layer, not through VolSync.
- `Database-native backups`: PostgreSQL clusters that are backed up with `pgBackRest` and WAL archiving to S3.

### VolSync-protected PVCs

The shared VolSync component is intended for application PVCs on `openebs-lvm`, including:

- `default/actual`
- `default/karakeep`
- `default/mealie`
- `database/meilisearch-karakeep`
- `media/jellyseerr`
- `media/qbittorrent`
- `media/radarr`
- `media/recyclarr`
- `media/sabnzbd`
- `media/sonarr`
- `media/sonarr-anime`

### Intentionally excluded from VolSync

These PVCs are not gaps in the VolSync/OpenEBS design:

- `default/immich-nfs-pvc`: backed up through the Immich NFS storage path.
- `media/mediastore-nfs-pvc`: backed up through the media NFS storage path.
- `database/immich16-postgres-*-pgdata`: protected by `pgBackRest` and WAL-to-S3.
- `database/postgres16-postgres-*-pgdata`: protected by `pgBackRest` and WAL-to-S3.
- `media/jellystat`: the deployed chart is currently stateless and only uses `emptyDir`, so it should not carry the shared VolSync component.

## Restore runbook

Use this flow for any app PVC that is protected by VolSync on `openebs-lvm`:

1. Confirm the latest backup completed successfully:

   ```sh
   kubectl get replicationsources.volsync.backube -A
   kubectl get replicationdestinations.volsync.backube -A
   ```

2. Stop all writers to the target PVC. Scale the workload down or suspend its Flux `HelmRelease` before restoring.

3. Pick a new manual trigger token and patch the `ReplicationDestination`:

   ```sh
   kubectl -n <namespace> patch replicationdestination <app>-dst \
     --type merge \
     -p '{"spec":{"trigger":{"manual":"restore-YYYYMMDDHHMMSS"}}}'
   ```

   Always use a new token. VolSync only starts a new restore when `spec.trigger.manual` changes.

4. Watch the restore until it finishes:

   ```sh
   kubectl -n <namespace> get replicationdestination <app>-dst -w
   kubectl -n <namespace> describe replicationdestination <app>-dst
   ```

5. Validate the restored data before bringing the workload back:

   ```sh
   kubectl -n <namespace> get pvc <app>
   kubectl -n <namespace> get pods
   ```

6. Start the workload again and verify application health.

7. After the restore, inspect for lingering artifacts:

   ```sh
   kubectl get pv | grep Released
   kubectl get volumesnapshots.snapshot.storage.k8s.io -A
   kubectl get lvmsnapshots.local.openebs.io -A
   ```

## Audit and monitoring

Use the repo audit helper to review OpenEBS/VolSync coverage and current cluster health:

```sh
./scripts/audit-volsync-openebs.sh
```

The audit is expected to verify:

- every `openebs-lvm` application PVC is VolSync-protected, intentionally excluded, or a true gap
- every VolSync-protected workload has completed at least one successful sync
- thin-pool free space remains healthy on `openebs-vg`
- stale `Released` PVs and stuck snapshots/syncs are visible for cleanup

Prometheus should alert on:

- the VolSync metrics endpoint disappearing
- any VolSync volume reporting out-of-sync
- any VolSync source that has never completed a backup

Thin-pool monitoring is still partly operational rather than fully automated here. Review `LVMNode` capacity regularly and extend the thin pool before it fills.

## Cutover note

This repo now assumes a fresh thin-only bootstrap. The single `openebs-lvm` StorageClass is thin-provisioned, and the old thick-provisioned class definition has been removed from the repo.

## Thin-pool monitoring note

OpenEBS 4.4 adds Local PV LVM snapshot restore support, but thin-pool accounting still has limitations. Monitor thin-pool usage on `openebs-vg` and extend capacity before the pool fills.
