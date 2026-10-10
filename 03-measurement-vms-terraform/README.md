# Terraform of Measurement VMs

This folder documents the Terraform/OpenTofu configuration of the measurement VMs used to collect data from our vantage points in TU Dresden and Google Cloud.

The measurement VMs at TUD are created on a Proxmox machine with

```hcl
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.85.1"
    }
```
