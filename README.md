# Artifacts of Discovering Encrypted Client Hello Deployments by Active ECH Probing

This repository contains the artifacts for our study on Encrypted Client Hello deployment.

NOTE: If you use our tools, please cite our paper as follows:

> Jonas Mücke, Konstantin Gasser, Thomas C.
> Schmidt, and Matthias Wählisch. 2026.
> Discovering Encrypted Client Hello Deployments by Active ECH Probing.
> In Proceedings of the 2026 ACM Internet Measurement Conference (IMC '26).
> ACM, New York, NY, USA, 276–286.
> <https://doi.org/10.1145/3777912.3839832>

## Abstract

> We present a new measurement method to detect ECH deployments.
> This method leverages standard-compliant behavior of ECH servers.
> Prior measurements relied on DNS exposure and reported only one major ECH deployment (Cloudflare).
> Our measurements reveal yet undiscovered ECH deployments, including a large deployment at Meta.
> Meta servers support ECH, but ECH configuration is not exposed via the DNS.
> We also empirically study details such as the level of privacy improvement and latency impact of ECH.

| Directory                          | Contents                                                                                                                                                                                                                                                                         | README                                                                                                   |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `01-cpu-profile-and-related-work/` | ECH client and server CPU profiling and a comparison against related work [performance-benchmarking](01-cpu-profile-and-related-work/performance-benchmarking/README.md), [tls-attacker-reproducibility](01-cpu-profile-and-related-work/tls-attacker-reproducibility/README.md) | [README](01-cpu-profile-and-related-work/README.md)                                                      |
| `02-echtool/`                      | We develop `echtool` to allow fine-grained control over ECH handshakes (latest version at [netd-tud/echtool](https://github.com/netd-tud/echtool))                                                                                                                               | [README](https://github.com/netd-tud/echtool/blob/a6f78da989cb9fce9524582fbf090e05853b47a9/README.md)    |
| `03-measurement-vms-terraform/`    | Terraform for the Google Cloud and TUD vantage point VMs                                                                                                                                                                                                                         | [README](03-measurement-vms-terraform/README.md)                                                         |
| `04-ansible/`                      | Ansible roles and configuration for our scan from TUD and Google Cloud                                                                                                                                                                                                           | [README](04-ansible/README.md)                                                                           |
| `05-ark-ech-measurements/`         | Measurement and data preprocessing from CAIDA Ark vantage points ([Ark project](https://www.caida.org/projects/ark/))                                                                                                                                                            | [README](05-ark-ech-measurements/README.md)                                                              |
| `06-ech-analysis/`                 | Data processing, graph plotting                                                                                                                                                                                                                                                  | [README](06-ech-analysis/README.md)                                                                      |
| `07-zgrab-ech/`                    | zgrab2 modified to support ECH handshakes                                                                                                                                                                                                                                        | [README](https://github.com/netd-tud/zgrab2-ech/blob/779806ffbb3f859944abb464471654f519affbda/README.md) |

## Getting Started

Clone with submodules:

```sh
git clone --recurse-submodules git@github.com:netd-tud/artifacts-imc26-active-ech-probing.git
```

To reproduce our analysis follow the instructions in the individual README files listed above.
The main data processing of our paper is detailed in [`06-ech-analysis/README.md`](06-ech-analysis/README.md).
