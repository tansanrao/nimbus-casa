resource "proxmox_virtual_environment_file" "gitlab_user_data" {
  content_type = "snippets"
  datastore_id = var.snippets_datastore_id
  node_name    = var.proxmox_node_name

  source_raw {
    data = templatefile("${path.module}/cloud-init/gitlab-user-data.yaml.tftpl", {
      fqdn                = var.gitlab_fqdn
      hostname            = var.gitlab_name
      ssh_authorized_keys = var.ssh_authorized_keys
      ssh_port            = var.gitlab_ssh_port
      ssh_username        = var.ssh_username
    })
    file_name = "${var.gitlab_name}-user-data.yaml"
  }
}

resource "proxmox_virtual_environment_file" "gitlab_network_data" {
  content_type = "snippets"
  datastore_id = var.snippets_datastore_id
  node_name    = var.proxmox_node_name

  source_raw {
    data = templatefile("${path.module}/cloud-init/gitlab-network-config.yaml.tftpl", {
      dns_search_domains = jsonencode(local.dns_search_domains)
      dns_servers        = jsonencode(var.dns_servers)
      ipv4_cidr          = "${var.gitlab_ipv4_address}/24"
      ipv4_gateway       = "10.10.40.1"
      mac_address        = lower(var.gitlab_mac_address)
    })
    file_name = "${var.gitlab_name}-network-config.yaml"
  }
}

resource "proxmox_virtual_environment_vm" "gitlab" {
  name        = var.gitlab_name
  description = "Nimbus Casa GitLab (Omnibus). Managed by OpenTofu."
  node_name   = var.proxmox_node_name
  tags        = ["opentofu", "gitlab", "ubuntu-2404"]
  vm_id       = var.gitlab_vm_id

  agent {
    enabled = true
  }

  # Weighted above the default (100) so GitLab wins CPU contention against CI.
  cpu {
    cores = var.gitlab_cpu_cores
    type  = "host"
    units = 200
  }

  memory {
    dedicated = var.gitlab_memory_mb
  }

  disk {
    datastore_id = coalesce(var.gitlab_datastore_id, var.vm_datastore_id)
    discard      = "on"
    import_from  = proxmox_download_file.ubuntu_2404_cloud_image.id
    interface    = "scsi0"
    iothread     = true
    size         = var.gitlab_root_disk_gb
    ssd          = true
  }

  # Ansible formats this as /dev/disk/by-id/scsi-SQEMU_QEMU_HARDDISK_gitlab-data
  # and mounts it at /var/opt/gitlab before installing GitLab.
  disk {
    datastore_id = coalesce(var.gitlab_datastore_id, var.vm_datastore_id)
    discard      = "on"
    file_format  = "raw"
    interface    = "scsi1"
    iothread     = true
    serial       = "gitlab-data"
    size         = var.gitlab_data_disk_gb
    ssd          = true
  }

  initialization {
    datastore_id         = var.cloudinit_datastore_id
    network_data_file_id = proxmox_virtual_environment_file.gitlab_network_data.id
    user_data_file_id    = proxmox_virtual_environment_file.gitlab_user_data.id
  }

  network_device {
    bridge      = var.network_bridge
    mac_address = var.gitlab_mac_address
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
