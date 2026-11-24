# Disposable Ubuntu 26.04 VM for testing cloud-init, such as the GitHub SSH
# keys in github-keys.tf. Set test_vm_enabled = true to create it and back to
# false to destroy it. It reuses connector0's cloud-init templates and image.

variable "test_vm_enabled" {
  description = "Create the disposable test VM."
  type        = bool
  default     = false
}

locals {
  test_vm = {
    name        = "sshtest0"
    fqdn        = "sshtest0.kbcb.tansanrao.net"
    ipv4        = "10.10.40.29"
    mac_address = "02:CA:5A:40:00:29"
  }
}

resource "proxmox_virtual_environment_file" "test_vm_user_data" {
  count        = var.test_vm_enabled ? 1 : 0
  content_type = "snippets"
  datastore_id = var.snippets_datastore_id
  node_name    = var.proxmox_node_name

  source_raw {
    data = templatefile("${path.module}/cloud-init/connector-user-data.yaml.tftpl", {
      fqdn                = local.test_vm.fqdn
      hostname            = local.test_vm.name
      ssh_authorized_keys = local.github_ssh_keys
      ssh_username        = var.ssh_username
    })
    file_name = "${local.test_vm.name}-user-data.yaml"
  }
}

resource "proxmox_virtual_environment_file" "test_vm_network_data" {
  count        = var.test_vm_enabled ? 1 : 0
  content_type = "snippets"
  datastore_id = var.snippets_datastore_id
  node_name    = var.proxmox_node_name

  source_raw {
    data = templatefile("${path.module}/cloud-init/connector-network-config.yaml.tftpl", {
      dns_search_domains = jsonencode(local.dns_search_domains)
      dns_servers        = jsonencode(var.dns_servers)
      ipv4_cidr          = "${local.test_vm.ipv4}/24"
      ipv4_gateway       = "10.10.40.1"
      mac_address        = lower(local.test_vm.mac_address)
    })
    file_name = "${local.test_vm.name}-network-config.yaml"
  }
}

resource "proxmox_virtual_environment_vm" "test_vm" {
  count       = var.test_vm_enabled ? 1 : 0
  name        = local.test_vm.name
  description = "Disposable cloud-init test VM. Managed by OpenTofu."
  node_name   = var.proxmox_node_name
  tags        = ["opentofu", "test", "ubuntu-2604"]

  agent {
    enabled = true
  }

  cpu {
    cores = 1
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = 2048
  }

  disk {
    datastore_id = var.vm_datastore_id
    discard      = "on"
    import_from  = proxmox_download_file.ubuntu_2604_cloud_image.id
    interface    = "scsi0"
    iothread     = true
    size         = 10
    ssd          = true
  }

  initialization {
    datastore_id         = var.cloudinit_datastore_id
    network_data_file_id = proxmox_virtual_environment_file.test_vm_network_data[0].id
    user_data_file_id    = proxmox_virtual_environment_file.test_vm_user_data[0].id
  }

  network_device {
    bridge      = var.network_bridge
    mac_address = local.test_vm.mac_address
    vlan_id     = var.connector_vlan_id
  }

  operating_system {
    type = "l26"
  }

  serial_device {
    device = "socket"
  }

  scsi_hardware   = "virtio-scsi-single"
  on_boot         = false
  stop_on_destroy = true
  started         = true
}
