variable "obs0_vm_id" {
  description = "Optional fixed Proxmox VM ID."
  type        = number
  default     = null
}

variable "obs0_name" {
  description = "Monitoring VM name; keep talos/obs0/talconfig.yaml in sync."
  type        = string
  default     = "obs0"
}

variable "obs0_ipv4_address" {
  description = "Monitoring VM static IPv4 address on HOMELAB; keep talos/obs0/talconfig.yaml in sync."
  type        = string
  default     = "10.10.40.26"
}

variable "obs0_mac_address" {
  description = "Stable locally administered MAC address; keep talos/obs0/talconfig.yaml in sync."
  type        = string
  default     = "02:CA:5A:40:00:26"
}

variable "obs0_cpu_cores" {
  description = "Monitoring VM vCPU count."
  type        = number
  default     = 2
}

variable "obs0_memory_mb" {
  description = "Monitoring VM dedicated memory in MiB."
  type        = number
  default     = 12288
}

variable "obs0_system_disk_gb" {
  description = "Talos system disk in GiB, holding the OS and container images."
  type        = number
  default     = 20
}

variable "obs0_data_disk_gb" {
  description = "Data disk in GiB for metrics and logs, mounted by Talos at /var/mnt/data."
  type        = number
  default     = 100
}

variable "obs0_datastore_id" {
  description = "SSD-backed datastore for both disks; null inherits vm_datastore_id."
  type        = string
  default     = null
}

variable "obs0_talos_image_version" {
  description = "Talos version of the bootstrap image only."
  type        = string
  default     = "v1.14.6"
}

variable "obs0_talos_schematic_id" {
  description = "Talos Image Factory schematic with siderolabs/qemu-guest-agent; keep talos/obs0/talconfig.yaml in sync."
  type        = string
  default     = "ce4c980550dd2ab1b17bbf2b08801c7eb59418eafe8f279833297925d67c7515"
}
