# Talos patches

`talconfig.yaml` applies these patches when `task talos:generate-config` runs. A new file here takes effect only after it is listed in `talconfig.yaml`.

- `global/`: every node. Kernel modules for LVM thin snapshots, the `openebs-lvm` raw volume, containerd, kubelet, DNS, sysctls and NTP settings.
- `controller/`: control plane nodes. Allows scheduling on the control plane, disables the built-in CoreDNS and kube-proxy (Cilium and the Flux-managed CoreDNS replace them) and exposes metrics listeners.

See the [Talos configuration patching guide](https://www.talos.dev/latest/talos-guides/configuration/patching/).
