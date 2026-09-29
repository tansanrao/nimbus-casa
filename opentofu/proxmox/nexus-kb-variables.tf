variable "nexus_kb_vm_id" {
  description = "Optional fixed Proxmox VM ID."
  type        = number
  default     = null
}

variable "nexus_kb_name" {
  description = "Nexus VM name."
  type        = string
  default     = "nexus-kb"
}

variable "nexus_kb_fqdn" {
  description = "Nexus VM FQDN."
  type        = string
  default     = "nexus-kb.kbcb.tansanrao.net"
}

variable "nexus_kb_ipv4_address" {
  description = "Nexus static IPv4 address; keep Ansible inventory in sync."
  type        = string
  default     = "10.10.40.23"
}

variable "nexus_kb_ipv4_prefix" {
  description = "Nexus IPv4 prefix length."
  type        = number
  default     = 24
}

variable "nexus_kb_ipv4_gateway" {
  description = "Nexus IPv4 default gateway."
  type        = string
  default     = "10.10.40.1"
}

variable "nexus_kb_mac_address" {
  description = "Stable locally administered MAC address."
  type        = string
  default     = "02:CA:5A:40:00:23"
}

variable "nexus_kb_vlan_id" {
  description = "Optional VLAN tag; null for an untagged bridge."
  type        = number
  default     = null
}

variable "nexus_kb_cpu_cores" {
  description = "Nexus vCPU count."
  type        = number
  default     = 8
}

variable "nexus_kb_memory_mb" {
  description = "Nexus dedicated memory in MiB."
  type        = number
  default     = 16384
}

variable "nexus_kb_disk_gb" {
  description = "Nexus root disk size in GiB; may be increased, never shrunk."
  type        = number
  default     = 400
}

variable "nexus_kb_datastore_id" {
  description = "SSD-backed datastore; null inherits vm_datastore_id. SSD emulation does not guarantee physical SSD backing."
  type        = string
  default     = null
}

variable "nexus_kb_cloud_image_url" {
  description = "Ubuntu 24.04 LTS cloud image URL."
  type        = string
  default     = "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
}
