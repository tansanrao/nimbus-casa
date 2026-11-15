locals {
  runner_admin_sources = join(",", var.runner_admin_sources)
}

# Bootstrap image only. Upgrade a running node with `task talos-runner:upgrade-node`,
# not by changing this version, which would only download a new image.
resource "proxmox_download_file" "talos_runner_image" {
  # Proxmox only decompresses downloads into ISO storage, so the raw image is
  # stored as an .img there and attached with file_id instead of import_from.
  content_type            = "iso"
  datastore_id            = var.image_datastore_id
  decompression_algorithm = "zst"
  file_name               = "talos-${var.runner_talos_image_version}-${substr(var.runner_talos_schematic_id, 0, 8)}-nocloud-amd64.img"
  node_name               = var.proxmox_node_name
  overwrite               = false
  url                     = "https://factory.talos.dev/image/${var.runner_talos_schematic_id}/${var.runner_talos_image_version}/nocloud-amd64.raw.zst"
}

resource "proxmox_virtual_environment_vm" "runner" {
  name        = var.runner_name
  description = "Nimbus Casa GitLab CI runner (single-node Talos). Untrusted workloads. Managed by OpenTofu."
  node_name   = var.proxmox_node_name
  tags        = ["opentofu", "gitlab-runner", "talos", "untrusted"]
  vm_id       = var.runner_vm_id

  agent {
    enabled = true
  }

  # Weighted below the default (100) so builds yield to every other guest.
  cpu {
    cores = var.runner_cpu_cores
    type  = "host"
    units = 50
  }

  memory {
    dedicated = var.runner_memory_mb
  }

  disk {
    datastore_id = coalesce(var.runner_datastore_id, var.vm_datastore_id)
    discard      = "on"
    file_id      = proxmox_download_file.talos_runner_image.id
    interface    = "scsi0"
    iothread     = true
    size         = var.runner_disk_gb
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
        address = "${var.runner_ipv4_address}/24"
        gateway = "10.10.40.1"
      }
    }
  }

  network_device {
    bridge      = var.network_bridge
    firewall    = true
    mac_address = var.runner_mac_address
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

# The VM firewall below only takes effect while the datacenter firewall is on.
# Both default policies stay ACCEPT so the host and every other guest behave as
# they did with the datacenter firewall off. No other guest has its VM-level
# firewall enabled, so only runner0 is filtered.
resource "proxmox_virtual_environment_cluster_firewall" "datacenter" {
  enabled        = true
  ebtables       = true
  input_policy   = "ACCEPT"
  output_policy  = "ACCEPT"
  forward_policy = "ACCEPT"

  depends_on = [proxmox_node_firewall.pve]
}

# The host firewall defaults to on once the datacenter firewall is enabled.
# Keep it off so management access to 10.10.1.20 cannot change.
resource "proxmox_node_firewall" "pve" {
  node_name = var.proxmox_node_name
  enabled   = false
}

# With ipfilter on, runner0 can only send from this address, so it cannot
# impersonate connector0 to reach GitLab's PROXY-protocol listeners.
resource "proxmox_virtual_environment_firewall_ipset" "runner_ipfilter" {
  node_name = var.proxmox_node_name
  vm_id     = proxmox_virtual_environment_vm.runner.vm_id
  name      = "ipfilter-net0"
  comment   = "Only addresses runner0 may send from"

  cidr {
    name = var.runner_ipv4_address
  }
}

resource "proxmox_virtual_environment_firewall_options" "runner" {
  node_name = var.proxmox_node_name
  vm_id     = proxmox_virtual_environment_vm.runner.vm_id

  enabled       = true
  dhcp          = false
  ipfilter      = true
  macfilter     = true
  ndp           = false
  radv          = false
  input_policy  = "DROP"
  output_policy = "ACCEPT"

  depends_on = [proxmox_virtual_environment_firewall_ipset.runner_ipfilter]
}

# runner0 may reach GitLab's HTTPS listener, the gateway's DNS and the public
# internet. Every other private, CGNAT, link-local and IPv6 destination is dropped.
resource "proxmox_virtual_environment_firewall_rules" "runner" {
  node_name = var.proxmox_node_name
  vm_id     = proxmox_virtual_environment_vm.runner.vm_id

  rule {
    type    = "in"
    action  = "ACCEPT"
    proto   = "tcp"
    dport   = "50000,6443"
    source  = local.runner_admin_sources
    comment = "Talos and Kubernetes APIs from admin hosts"
  }

  rule {
    type    = "in"
    action  = "ACCEPT"
    macro   = "Ping"
    source  = local.runner_admin_sources
    comment = "Ping from admin hosts"
  }

  rule {
    type    = "out"
    action  = "ACCEPT"
    proto   = "tcp"
    dest    = var.gitlab_ipv4_address
    dport   = "443"
    comment = "GitLab HTTPS, registry and Dependency Proxy"
  }

  rule {
    type    = "out"
    action  = "ACCEPT"
    macro   = "DNS"
    dest    = "10.10.40.1"
    comment = "Gateway DNS"
  }

  dynamic "rule" {
    for_each = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16", "::/0"]
    content {
      type    = "out"
      action  = "DROP"
      dest    = rule.value
      comment = "No private, CGNAT, link-local or IPv6 destinations"
    }
  }

  depends_on = [proxmox_virtual_environment_firewall_options.runner]
}
