# OpenEBS LVM and VolSync

Talos exposes the node's second NVMe as a raw volume at `/dev/disk/by-partlabel/r-openebs-lvm`. It holds the `openebs-vg` volume group and its thin pool. The Talos config loads `dm_snapshot` and `dm_thin_pool` so OpenEBS can take thin snapshots.

- StorageClass `openebs-lvm`: thin-provisioned. All application and database PVCs use it.
- VolumeSnapshotClass `openebs-lvm-snap`: used by VolSync.
- `openebs-hostpath`: VolSync cache PVCs, which need no snapshots.

## Backups

| Data | Backed up by |
| --- | --- |
| App PVCs: `karakeep/karakeep`, `karakeep/meilisearch-karakeep`, `mealie/mealie`, `media-services/{jellyfin,kavita,seerr}`, `media/{kapowarr,qbittorrent,radarr,recyclarr,sabnzbd,sonarr,sonarr-anime}` | VolSync restic, hourly from a snapshot. Keeps 24 hourly and 7 daily. |
| CloudNativePG volumes (`<cluster>-1`, label `cnpg.io/cluster`) | Barman Cloud to Garage. See [ARCHITECTURE.md](../../../../ARCHITECTURE.md#kubernetes). |
| NFS PVCs (`nfs-immich`, `nfs-mediastore`) | The NAS |
| `observability/*` (Prometheus, Alertmanager, Grafana) | Nothing |

`media/jellyfin` and `media/kavita` are the pre-isolation copies, kept with the suspended legacy Kustomizations. Their VolSync sources stopped on 2026-10-31.

Mealie, Karakeep and Meilisearch kept their original PVs when they moved namespaces. Their Kustomizations pin `volumeName`; remove that patch only to restore onto a new PV. They have no restore-once ReplicationDestination, so nothing overwrites them on startup.

`scripts/audit-volsync-openebs.sh` lists protected, excluded and unprotected PVCs, sync status, thin pool free space and Released PVs. Prometheus alerts when the VolSync metrics endpoint disappears, a volume is out of sync, or a source has never completed. Nothing alerts on thin pool usage; check `LVMNode` capacity and extend the pool before it fills.

## Restoring a PVC

A restore overwrites the live PVC in place.

1. Check that the latest backup succeeded: `kubectl get replicationsources -A`.
2. Stop every writer: scale the workload to zero or suspend its HelmRelease.
3. Trigger the restore with a new token. VolSync only starts a restore when the token changes.

   ```sh
   kubectl -n <namespace> patch replicationdestination <app>-dst --type merge \
     -p '{"spec":{"trigger":{"manual":"restore-YYYYMMDDHHMMSS"}}}'
   kubectl -n <namespace> get replicationdestination <app>-dst -w
   ```

4. Start the workload and check the app.
5. Look for leftovers: `kubectl get pv | grep Released`, `kubectl get volumesnapshots -A` and `kubectl get lvmsnapshots.local.openebs.io -A`.

## Bootstrapping the volume group

This is only needed on a new node or disk.

1. Check that Talos created the raw volume and loaded the modules. If either module is missing, apply the Talos config and reboot.

   ```sh
   talosctl -n 10.10.40.40 get volumestatus r-openebs-lvm
   talosctl -n 10.10.40.40 read /proc/modules | grep -E 'dm_snapshot|dm_thin_pool'
   ```

2. Talos has no LVM tools, so create the volume group from a debug pod. LVM only scans the container's `/dev`, so bind the host's `/dev` over it first.

   ```sh
   kubectl debug node/k8s0 -it --image=debian:12-slim --profile=sysadmin -- sh
   apt-get update && apt-get install -y lvm2 util-linux
   mount --rbind /host/dev /dev
   mkdir -p /run/udev && mount --rbind /host/run/udev /run/udev || true
   pvcreate /dev/disk/by-partlabel/r-openebs-lvm
   vgcreate openebs-vg /dev/disk/by-partlabel/r-openebs-lvm
   ```

3. Exit and delete the `node-debugger-k8s0-*` pod in `default`.
4. Check that `kubectl -n openebs-system get pods` is healthy and that `kubectl get sc openebs-lvm` lists the class.
