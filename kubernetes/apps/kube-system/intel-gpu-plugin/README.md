# Intel GPU

The Intel Arc A380 is passed through to `k8s0`. Talos loads the `i915` and `mei` system extensions, Node Feature Discovery labels the node, and the Intel GPU device plugin runs as a plain DaemonSet (no operator or `GpuDevicePlugin` resource). GPU telemetry is disabled.

## Checks

```sh
talosctl -n 10.10.40.40 get extensions
talosctl -n 10.10.40.40 ls /dev/dri
kubectl get node k8s0 -o jsonpath='{.status.allocatable.gpu\.intel\.com/i915}{"\n"}'
kubectl -n kube-system get pods | grep -E 'node-feature-discovery|intel-gpu-plugin'
kubectl get node --show-labels | grep 'intel.feature.node.kubernetes.io/gpu=true'
```

## Using the GPU

A workload requests the device with:

```yaml
resources:
  limits:
    gpu.intel.com/i915: 1
```

Current consumers:

- `immich/immich-machine-learning`, which needs the `-openvino` image. `immich-server` needs no GPU.
- `media-services/jellyfin`, for Intel QSV or VA-API transcoding. Hardware acceleration is set in Jellyfin's own settings.
