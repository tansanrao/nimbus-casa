output "connector_name" {
  description = "Connector VM name."
  value       = proxmox_virtual_environment_vm.connector.name
}

output "connector_ipv4_address" {
  description = "Connector VM static IPv4 address."
  value       = local.connector_ipv4_cidr
}

output "connector_vm_id" {
  description = "Connector VM ID."
  value       = proxmox_virtual_environment_vm.connector.vm_id
}

output "proxmox_release" {
  description = "Detected Proxmox VE point release."
  value       = data.proxmox_version.current.release
}
