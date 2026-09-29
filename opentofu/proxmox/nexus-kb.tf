resource "proxmox_download_file" "ubuntu_2404_cloud_image" {
  content_type        = "import"
  datastore_id        = var.image_datastore_id
  file_name           = "noble-server-cloudimg-amd64.qcow2"
  node_name           = var.proxmox_node_name
  overwrite           = true
  overwrite_unmanaged = false
  url                 = var.nexus_kb_cloud_image_url
}

resource "proxmox_virtual_environment_file" "nexus_kb_user_data" {
  content_type = "snippets"
  datastore_id = var.snippets_datastore_id
  node_name    = var.proxmox_node_name

  source_raw {
    data = templatefile("${path.module}/cloud-init/nexus_kb-user-data.yaml.tftpl", {
      fqdn                = var.nexus_kb_fqdn
      hostname            = var.nexus_kb_name
      ssh_authorized_keys = var.ssh_authorized_keys
      ssh_username        = var.ssh_username
    })
    file_name = "${var.nexus_kb_name}-user-data.yaml"
  }
}

resource "proxmox_virtual_environment_file" "nexus_kb_network_data" {
  content_type = "snippets"
  datastore_id = var.snippets_datastore_id
  node_name    = var.proxmox_node_name

  source_raw {
    data = templatefile("${path.module}/cloud-init/nexus_kb-network-config.yaml.tftpl", {
      dns_search_domains = jsonencode(local.dns_search_domains)
      dns_servers        = jsonencode(var.dns_servers)
      ipv4_cidr          = "${var.nexus_kb_ipv4_address}/${var.nexus_kb_ipv4_prefix}"
      ipv4_gateway       = var.nexus_kb_ipv4_gateway
      mac_address        = lower(var.nexus_kb_mac_address)
    })
    file_name = "${var.nexus_kb_name}-network-config.yaml"
  }
}

resource "proxmox_virtual_environment_vm" "nexus_kb" {
  name        = var.nexus_kb_name
  description = "Nimbus Casa Nexus production host. Managed by OpenTofu."
  node_name   = var.proxmox_node_name
  tags        = ["opentofu", "nexus-kb", "ubuntu-2404"]
  vm_id       = var.nexus_kb_vm_id

  agent {
    enabled = true
  }

  cpu {
    cores = var.nexus_kb_cpu_cores
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = var.nexus_kb_memory_mb
  }

  disk {
    datastore_id = coalesce(var.nexus_kb_datastore_id, var.vm_datastore_id)
    discard      = "on"
    import_from  = proxmox_download_file.ubuntu_2404_cloud_image.id
    interface    = "scsi0"
    iothread     = true
    size         = var.nexus_kb_disk_gb
    ssd          = true
  }

  initialization {
    datastore_id         = var.cloudinit_datastore_id
    network_data_file_id = proxmox_virtual_environment_file.nexus_kb_network_data.id
    user_data_file_id    = proxmox_virtual_environment_file.nexus_kb_user_data.id
  }

  network_device {
    bridge      = var.network_bridge
    mac_address = var.nexus_kb_mac_address
    vlan_id     = var.nexus_kb_vlan_id
  }

  operating_system {
    type = "l26"
  }

  serial_device {
    device = "socket"
  }

  scsi_hardware   = "virtio-scsi-single"
  on_boot         = true
  stop_on_destroy = true
  started         = true

  lifecycle {
    precondition {
      condition     = can(regex("^(8|9)\\.", data.proxmox_version.current.release))
      error_message = "This configuration is intentionally limited to Proxmox VE 8.x or 9.x."
    }
  }
}
