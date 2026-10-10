resource "google_compute_instance" "ech" {
  name         = "ech-gc-${each.value}"
  machine_type = var.machine-type

  for_each = toset(var.regions)
  zone     = "${each.value}-a"

  boot_disk {
    initialize_params {
      image = "ubuntu-2404-lts-amd64"
      size  = 30
    }
  }
  # resource_policies = [google_compute_resource_policy.daily_schedule[each.key].id]

  network_interface {
    # A default network is created for all GCP projects
    network = data.google_compute_network.default.id

    access_config {
      public_ptr_domain_name = "ech.research.netd.cs.tu-dresden.de."
      network_tier           = "STANDARD"
    }
  }
  metadata = {
    role      = "ech"
    user-data = <<-EOF
         #cloud-config
         timezone: UTC
         ssh_pwauth: false
         users:
           - default
           - name: ansible
             groups: sudo
             sudo: ['ALL=(ALL) NOPASSWD:ALL']
             shell: /bin/bash
         package_update: true
         packages:
           - alacritty
           - kitty-terminfo
         runcmd:
           - mkdir -p /mnt/data01
           - echo "done" > /tmp/cloud-config.done
       EOF
  }


  provisioner "remote-exec" {
    inline = ["echo Wait until ssh is ready && while [ ! -f /var/lib/cloud/instance/boot-finished ]; do echo 'Waiting for cloud-init...'; sleep 1; done"]

    connection {
      type        = "ssh"
      user        = "ansible"
      private_key = file("/home/jonas/.ssh/id_ansible_ed25519")
      host        = self.network_interface[0].access_config[0].nat_ip
    }

  }


}

