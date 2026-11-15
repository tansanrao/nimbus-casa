variable "gitlab_vm_id" {
  description = "Optional fixed Proxmox VM ID."
  type        = number
  default     = null
}

variable "gitlab_name" {
  description = "GitLab VM name."
  type        = string
  default     = "gitlab0"
}

variable "gitlab_fqdn" {
  description = "GitLab VM FQDN on the home network. The public GitLab hostname is set in Ansible."
  type        = string
  default     = "gitlab0.kbcb.tansanrao.net"
}

variable "gitlab_ipv4_address" {
  description = "GitLab static IPv4 address; keep the Ansible inventory and connector0 backends in sync."
  type        = string
  default     = "10.10.40.24"
}

variable "gitlab_mac_address" {
  description = "Stable locally administered MAC address."
  type        = string
  default     = "02:CA:5A:40:00:24"
}

variable "gitlab_ssh_port" {
  description = "Admin OpenSSH port. Port 22 belongs to gitlab-sshd; keep the Ansible inventory in sync."
  type        = number
  default     = 2022
}

variable "gitlab_cpu_cores" {
  description = "GitLab vCPU count."
  type        = number
  default     = 12
}

variable "gitlab_memory_mb" {
  description = "GitLab dedicated memory in MiB."
  type        = number
  default     = 24576
}

variable "gitlab_root_disk_gb" {
  description = "GitLab OS disk size in GiB; may be increased, never shrunk."
  type        = number
  default     = 40
}

variable "gitlab_data_disk_gb" {
  description = "GitLab data disk (/var/opt/gitlab) size in GiB; may be increased, never shrunk."
  type        = number
  default     = 300
}

variable "gitlab_datastore_id" {
  description = "SSD-backed datastore; null inherits vm_datastore_id."
  type        = string
  default     = null
}
