variable "proxmox_node_name" {
  description = "Proxmox node where connector0 should run."
  type        = string
}

variable "image_datastore_id" {
  description = "Datastore used to store imported cloud images. Must allow Import content."
  type        = string
  default     = "local"
}

variable "snippets_datastore_id" {
  description = "Datastore used for cloud-init snippets. Must allow Snippets content."
  type        = string
  default     = "local"
}

variable "vm_datastore_id" {
  description = "Datastore used for the connector VM disk."
  type        = string
  default     = "local-lvm"
}

variable "cloudinit_datastore_id" {
  description = "Datastore used for the connector VM cloud-init disk."
  type        = string
  default     = "local-lvm"
}

variable "network_bridge" {
  description = "Proxmox Linux bridge for the HOMELAB network."
  type        = string
  default     = "vmbr0"
}

variable "connector_vlan_id" {
  description = "Optional VLAN tag for the connector VM NIC. Use null when the bridge is already on HOMELAB."
  type        = number
  default     = null
}

variable "connector_vm_id" {
  description = "Optional fixed Proxmox VM ID for connector0."
  type        = number
  default     = null
}

variable "connector_name" {
  description = "Connector VM name."
  type        = string
  default     = "connector0"
}

variable "connector_fqdn" {
  description = "Connector VM FQDN."
  type        = string
  default     = "connector0.kbcb.tansanrao.net"
}

variable "connector_ipv4_address" {
  description = "Connector VM static IPv4 address without prefix length."
  type        = string
  default     = "10.10.40.21"
}

variable "connector_ipv4_prefix" {
  description = "Connector VM IPv4 prefix length."
  type        = number
  default     = 24
}

variable "connector_ipv4_gateway" {
  description = "Connector VM IPv4 default gateway."
  type        = string
  default     = "10.10.40.1"
}

variable "connector_mac_address" {
  description = "Stable locally-administered MAC address for connector0. Used by cloud-init network-config to match the NIC deterministically."
  type        = string
  default     = "02:CA:5A:40:00:21"

  validation {
    condition     = can(regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", var.connector_mac_address))
    error_message = "connector_mac_address must be a colon-separated MAC address."
  }
}

variable "dns_servers" {
  description = "DNS servers for cloud-init."
  type        = list(string)
  default     = ["10.10.40.1", "1.1.1.1"]
}

variable "dns_domain" {
  description = "DNS search domain for cloud-init."
  type        = string
  default     = "kbcb.tansanrao.net"
}

variable "ssh_username" {
  description = "Initial cloud-init SSH user."
  type        = string
  default     = "ubuntu"
}

variable "ssh_authorized_keys" {
  description = "SSH public keys authorized for the initial cloud-init user."
  type        = list(string)

  validation {
    condition     = length(var.ssh_authorized_keys) > 0
    error_message = "At least one SSH public key is required."
  }
}

variable "ubuntu_cloud_image_url" {
  description = "Rolling Ubuntu 26.04 LTS cloud image URL."
  type        = string
  default     = "https://cloud-images.ubuntu.com/resolute/current/resolute-server-cloudimg-amd64.img"
}

variable "connector_cpu_cores" {
  description = "Connector VM CPU cores."
  type        = number
  default     = 2
}

variable "connector_memory_mb" {
  description = "Connector VM dedicated memory in MiB."
  type        = number
  default     = 2048
}

variable "connector_disk_gb" {
  description = "Connector VM boot disk size in GiB."
  type        = number
  default     = 20
}
