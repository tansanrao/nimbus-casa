# TrueNAS monitoring app

One TrueNAS custom app with three containers:

| Container | Port | What it gives |
| --- | --- | --- |
| `node-exporter` | 9100 | Free space per dataset, ZFS pool state (`node_zfs_zpool_state`), ARC, disk I/O, NIC errors, NFS server stats |
| `smartctl-exporter` | 9633 | SMART health, temperatures, reallocated and pending sectors, NVMe wear and media errors |
| `fluent-bit` | none | The host journal and `middlewared.log`, sent to VictoriaLogs at `logs.tansanrao.net` |

Prometheus in k8s0 scrapes both exporters, and Garage's `/metrics` on port 30190, as `instance="truenas"` (`kubernetes/apps/observability/kube-prometheus-stack/app/scrapeconfig.yaml`). Their alerts are in `prometheusrule.yaml` next to it.

## Install

1. Check that the journal is persistent: `ls /var/log/journal` in the TrueNAS shell should list a machine-ID directory. If it does not, change `path` in `fluent-bit.yaml` to `/run/log/journal` and mount `/run/log/journal` instead of `/var/log`.
2. Check that TrueNAS resolves the log endpoint through UniFi: `getent hosts logs.tansanrao.net` should print `10.10.40.61`.
3. Check the hostname with `hostname`. If it is not `truenas`, use it in `fluent-bit.yaml`'s `modify` filter and as the `instance` label in `scrapeconfig.yaml`, so metrics and logs share one name.
4. Create a dataset for the app, such as `<pool>/apps/fluent-bit`, with a `buffer` directory inside it, and copy `fluent-bit.yaml` into it.
5. Get the ingest password:

   ```sh
   SOPS_AGE_KEY_FILE=$PWD/age.key sops -d kubernetes/apps/observability/victoria-logs/app/ingest-users.sops.yaml | yq '.stringData["truenas-password"]'
   ```

6. In Apps → Discover → Install via YAML, paste `compose.yaml` with `<pool>` and `VL_PASSWORD` filled in, and name the app `monitoring`.

## Check

- `curl -s http://10.10.40.10:9100/metrics | grep node_zfs_zpool_state` lists every pool.
- `curl -s http://10.10.40.10:9633/metrics | grep smartctl_device_smart_status` lists every disk.
- In Grafana → Explore → VictoriaLogs, `_HOSTNAME:truenas` returns lines within a minute.
- In Prometheus → Status → Targets, the `node-exporter`, `smartctl` and `garage` targets for `truenas` are up.

## TrueNAS's own alerts

Pool degraded, SMART failures, scrub errors and pools over 80% are also TrueNAS alerts. Send them to Pushover directly, so they reach you while k8s0 is down: System → Alert Settings → Add, type Pushover, with your user key and a Pushover application token. Then send a test alert.

## Updating

Pin new image tags in `compose.yaml` and in the app's YAML in TrueNAS together. After a TrueNAS upgrade, check that the three targets above still report.
