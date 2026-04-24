locals {
  connector_ipv4_cidr = "${var.connector_ipv4_address}/${var.connector_ipv4_prefix}"
  dns_search_domains  = compact([var.dns_domain])
}

data "proxmox_version" "current" {}

resource "proxmox_download_file" "ubuntu_2604_cloud_image" {
  content_type        = "import"
  datastore_id        = var.image_datastore_id
  file_name           = "resolute-server-cloudimg-amd64.qcow2"
  node_name           = var.proxmox_node_name
  overwrite           = true
  overwrite_unmanaged = false
  url                 = var.ubuntu_cloud_image_url
}

resource "proxmox_virtual_environment_file" "connector_user_data" {
  content_type = "snippets"
  datastore_id = var.snippets_datastore_id
  node_name    = var.proxmox_node_name

  source_raw {
    data = templatefile("${path.module}/cloud-init/connector-user-data.yaml.tftpl", {
      fqdn                = var.connector_fqdn
      hostname            = var.connector_name
      ssh_authorized_keys = var.ssh_authorized_keys
      ssh_username        = var.ssh_username
    })
    file_name = "${var.connector_name}-user-data.yaml"
  }
}

resource "proxmox_virtual_environment_file" "connector_network_data" {
  content_type = "snippets"
  datastore_id = var.snippets_datastore_id
  node_name    = var.proxmox_node_name

  source_raw {
    data = templatefile("${path.module}/cloud-init/connector-network-config.yaml.tftpl", {
      dns_search_domains = jsonencode(local.dns_search_domains)
      dns_servers        = jsonencode(var.dns_servers)
      ipv4_cidr          = local.connector_ipv4_cidr
      ipv4_gateway       = var.connector_ipv4_gateway
      mac_address        = lower(var.connector_mac_address)
    })
    file_name = "${var.connector_name}-network-config.yaml"
  }
}

resource "proxmox_virtual_environment_vm" "connector" {
  name        = var.connector_name
  description = "Nimbus Casa home connector. Managed by OpenTofu."
  node_name   = var.proxmox_node_name
  tags        = ["opentofu", "connector", "ubuntu-2604"]
  vm_id       = var.connector_vm_id

  agent {
    enabled = true
  }

  cpu {
    cores = var.connector_cpu_cores
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = var.connector_memory_mb
  }

  disk {
    datastore_id = var.vm_datastore_id
    discard      = "on"
    import_from  = proxmox_download_file.ubuntu_2604_cloud_image.id
    interface    = "scsi0"
    iothread     = true
    size         = var.connector_disk_gb
  }

  initialization {
    datastore_id         = var.cloudinit_datastore_id
    network_data_file_id = proxmox_virtual_environment_file.connector_network_data.id
    user_data_file_id    = proxmox_virtual_environment_file.connector_user_data.id
  }

  network_device {
    bridge      = var.network_bridge
    mac_address = var.connector_mac_address
    vlan_id     = var.connector_vlan_id
  }

  operating_system {
    type = "l26"
  }

  serial_device {
    device = "socket"
  }

  stop_on_destroy = true
  started         = true

  lifecycle {
    precondition {
      condition     = can(regex("^(8|9)\\.", data.proxmox_version.current.release))
      error_message = "This configuration is intentionally limited to Proxmox VE 8.x or 9.x."
    }
  }
}
