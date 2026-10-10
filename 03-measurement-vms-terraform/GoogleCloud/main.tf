provider "google" {
  project = "jmuecke-ech-imc-2026-06"
  region  = "europe-west10"
  zone    = "europe-west10-a"
}

data "google_compute_network" "default" {
  name = "default"
}

resource "google_compute_firewall" "allow-all-v4" {
  name     = "allow-all-v4"
  network  = data.google_compute_network.default.id
  priority = 0
  allow {
    protocol = "all"
  }
  source_ranges = ["0.0.0.0/0"]

}

resource "google_compute_firewall" "allow-all-v6" {
  name     = "allow-all-v6"
  network  = data.google_compute_network.default.id
  priority = 0
  allow {
    protocol = "all"
  }
  source_ranges = ["::/0"]

}

variable "regions" {
  type = list(string)
  # default = ["europe-west10"]
  default = ["europe-west10", "us-west2", "southamerica-east1", "asia-east2", "africa-south1", "australia-southeast1"]
}

variable "machine-type" {
  type    = string
  default = "e2-highcpu-4"
}

resource "google_compute_resource_policy" "daily_schedule" {
  for_each = toset(var.regions)
  name     = "daily-vm-schedule"
  region   = each.value

  instance_schedule_policy {
    vm_start_schedule {
      // Must start earlier than the measurements
      schedule = "0 4 * * *"
    }
    time_zone = "UTC"
  }
}

