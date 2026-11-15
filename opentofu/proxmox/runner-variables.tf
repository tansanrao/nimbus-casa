variable "runner_vm_id" {
  description = "Optional fixed Proxmox VM ID."
  type        = number
  default     = null
}

variable "runner_name" {
  description = "Runner VM name; keep talos-runner/talconfig.yaml in sync."
  type        = string
  default     = "runner0"
}

variable "runner_ipv4_address" {
  description = "Runner static IPv4 address on HOMELAB; keep talos-runner/talconfig.yaml and the GitLab allowlist in sync."
  type        = string
  default     = "10.10.40.25"
}

variable "runner_mac_address" {
  description = "Stable locally administered MAC address; keep talos-runner/talconfig.yaml in sync."
  type        = string
  default     = "02:CA:5A:40:00:25"
}

variable "runner_cpu_cores" {
  description = "Runner vCPU count. Overcommitted on purpose; CPU units keep builds below other guests."
  type        = number
  default     = 24
}

variable "runner_memory_mb" {
  description = "Runner dedicated memory in MiB."
  type        = number
  default     = 36864
}

variable "runner_disk_gb" {
  description = "Runner system disk in GiB, holding images and job ephemeral storage."
  type        = number
  default     = 200
}

variable "runner_datastore_id" {
  description = "SSD-backed datastore; null inherits vm_datastore_id."
  type        = string
  default     = null
}

variable "runner_talos_image_version" {
  description = "Talos version of the bootstrap image only."
  type        = string
  default     = "v1.14.6"
}

variable "runner_talos_schematic_id" {
  description = "Talos Image Factory schematic with siderolabs/qemu-guest-agent; keep talos-runner/talconfig.yaml in sync."
  type        = string
  default     = "ce4c980550dd2ab1b17bbf2b08801c7eb59418eafe8f279833297925d67c7515"
}

variable "runner_admin_sources" {
  description = "Sources allowed to reach the Talos and Kubernetes APIs. Admin traffic routed through Proxmox arrives from 10.10.1.20."
  type        = list(string)
  default     = ["10.10.1.20", "10.10.10.0/24"]
}
