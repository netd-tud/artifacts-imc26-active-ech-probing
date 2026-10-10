resource "proxmox_virtual_environment_vm" "ech-quic" {
  name      = "ech-quic.research.${var.measurement_suffix}"
  node_name = var.ve_measurement_node

  started = true
  protection = true
  description = "Encrypted Client Hello + QUIC"
  tags = ["tf"]

  cpu {
    cores = 8
  }
  memory {
    dedicated = 4096
  }

  efi_disk {
    datastore_id = var.ve_measurement_os
    type         = "4m"
  }
  disk {
    datastore_id = var.ve_measurement_os
    import_from  = proxmox_virtual_environment_download_file.ubuntu_24_04_cloud.id
    interface    = "virtio0"
    iothread     = true
    size         = 20
  }
  
  disk {
    datastore_id = var.ve_measurement_data
    interface    = "virtio1"
    iothread     = true
    size         = 100
    serial       = "netd-data-disk"
  }
  provisioner "local-exec" {
    command = "cd ../config-management && make deploy PARAMS='--limit ${replace(self.name, ".${var.measurement_suffix}", "")}'"
  }

  agent {
    enabled = true
  }
  network_device {
    bridge = "vmbr0"
  }
  initialization {
    datastore_id = var.ve_measurement_data
    user_data_file_id = proxmox_virtual_environment_file.netd_cloud_config_v01.id
    dns {
      servers = ["REDACTED"]
    }
    ip_config {
      ipv4 {
        address = "REDACTED"
        gateway = "REDACTED"
      }
    }
  }
}
