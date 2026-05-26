# Intel GPU Runbook

This cluster exposes the passed-through Intel Arc A380 to Kubernetes through:

- Talos system extensions: `i915` and `mei`
- Node Feature Discovery
- Intel GPU device plugin DaemonSet

## Expected Node State

Talos should report the Intel GPU extensions:

```sh
talosctl -n 10.10.40.40 get extensions
```

The node should expose the DRM render node:

```sh
talosctl -n 10.10.40.40 ls /dev/dri
```

Kubernetes should show allocatable Intel GPU resources:

```sh
kubectl get node k8s0 -o jsonpath='{.status.allocatable.gpu\.intel\.com/i915}{"\n"}'
kubectl get node k8s0 -o jsonpath='{.status.allocatable.gpu\.intel\.com/monitoring}{"\n"}'
```

## Validation

Check the support stack:

```sh
kubectl -n kube-system get pods | grep -E 'node-feature-discovery|intel-gpu-plugin'
kubectl get node --show-labels | grep 'intel.feature.node.kubernetes.io/gpu=true'
```

The Intel GPU plugin is deployed directly as a `DaemonSet`. It does not use the Intel device plugin operator or the `GpuDevicePlugin` custom resource.

Prometheus scrapes node-level Intel GPU telemetry through the `intel-gpu-exporter`
DaemonSet. The exporter uses the plugin's `gpu.intel.com/monitoring` resource so
it can read all Intel GPU devices without consuming the app-facing
`gpu.intel.com/i915` capacity.

```sh
kubectl -n kube-system get pods -l app.kubernetes.io/name=intel-gpu-exporter -o wide
kubectl -n kube-system port-forward svc/intel-gpu-exporter 8080:8080
curl -fsSL http://127.0.0.1:8080/metrics | grep '^igpu_'
```

Prometheus query examples:

```promql
up{job="intel-gpu"}
igpu_power_gpu
```

## Workload Contract

GPU-enabled apps should request:

```yaml
resources:
  limits:
    gpu.intel.com/i915: 1
```

For Immich:

- `immich-machine-learning` requests `gpu.intel.com/i915: 1`.
- `immich-machine-learning` must use the `-openvino` image variant.
- `immich-server` does not need a GPU for OpenVINO machine learning.

For future Jellyfin:

- request `gpu.intel.com/i915: 1`
- configure Jellyfin hardware acceleration for Intel QSV or VA-API
- on multi-GPU hosts, set the render device explicitly if the app does not auto-detect the injected device
