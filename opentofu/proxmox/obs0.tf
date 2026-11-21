# Bootstrap image only. Upgrade a running node with
# `task talos:upgrade-node CLUSTER=obs0 IP=10.10.40.26`, not by changing this
# version, which would only download a new image.
resource "proxmox_download_file" "talos_obs0_image" {
  # Same image as runner0's, under its own file name so neither VM's resource
  # can delete the other's file.
  content_type            = "iso"
  datastore_id            = var.image_datastore_id
  decompression_algorithm = "zst"
  file_name               = "talos-obs0-${var.obs0_talos_image_version}-${substr(var.obs0_talos_schematic_id, 0, 8)}-nocloud-amd64.img"
  node_name               = var.proxmox_node_name
  overwrite               = false
  url                     = "https://factory.talos.dev/image/${var.obs0_talos_schematic_id}/${var.obs0_talos_image_version}/nocloud-amd64.raw.zst"
}

resource "proxmox_virtual_environment_vm" "obs0" {
  name        = var.obs0_name
  description = "Nimbus Casa monitoring (single-node Talos): Prometheus, Alertmanager, Grafana, VictoriaLogs, Gatus. Managed by OpenTofu."
  node_name   = var.proxmox_node_name
  tags        = ["opentofu", "monitoring", "talos"]
  vm_id       = var.obs0_vm_id

  agent {
    enabled = true
  }

  cpu {
    cores = var.obs0_cpu_cores
    type  = "host"
  }

  memory {
    dedicated = var.obs0_memory_mb
  }

  disk {
    datastore_id = coalesce(var.obs0_datastore_id, var.vm_datastore_id)
    discard      = "on"
    file_id      = proxmox_download_file.talos_obs0_image.id
    interface    = "scsi0"
    iothread     = true
    size         = var.obs0_system_disk_gb
    ssd          = true
  }

  # Talos's UserVolumeConfig selects this disk by its serial.
  disk {
    datastore_id = coalesce(var.obs0_datastore_id, var.vm_datastore_id)
    discard      = "on"
    file_format  = "raw"
    interface    = "scsi1"
    iothread     = true
    serial       = "obs0-data"
    size         = var.obs0_data_disk_gb
    ssd          = true
  }

  # Talos reads this NoCloud drive in maintenance mode; the machine config
  # applied by talhelper sets the same static address afterwards.
  initialization {
    datastore_id = var.cloudinit_datastore_id
    type         = "nocloud"

    dns {
      servers = ["10.10.40.1"]
    }

    ip_config {
      ipv4 {
        address = "${var.obs0_ipv4_address}/24"
        gateway = "10.10.40.1"
      }
    }
  }

  network_device {
    bridge      = var.network_bridge
    mac_address = var.obs0_mac_address
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
    # The image only seeds the first boot; a newer one must not rebuild the VM.
    ignore_changes = [
      disk[0].file_id,
    ]

    precondition {
      condition     = can(regex("^(8|9)\\.", data.proxmox_version.current.release))
      error_message = "This configuration is intentionally limited to Proxmox VE 8.x or 9.x."
    }
  }
}
