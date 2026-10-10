# ECH Client and Server Profiling & TLS-Attacker Reproducibility

Container images are built once and shared across:

- `performance-benchmarking/` ([README](performance-benchmarking/README.md)): CPU profiling of client (Go) and server implementations (Apache httpd and nginx)
- `tls-attacker-reproducibility/` ([README](tls-attacker-reproducibility/README.md)): comparing this work and Niere et al.'s (FOCI 2025) ECH code support measurement method

- Shared build config: `containers.mk`
- Image sources: `containers/`

We use `podman` for creating containers.

If possible we use official container images.
ECH support is not built into the official container images at this moment.
For `nginx` we adapt the Dockerfile of the official container images to enable ECH support and enable performance profiling.
For `apache-httpd` we use the [defo-project fork](https://github.com/defo-project/apache-httpd).

## Container Images

| Image                       | Web server                       | Version(s)                                                                                              | TLS library                     | TLS library ref            |
| --------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------- | -------------------------- |
| `localhost/nginx-ech`       | nginx (built from source)        | 1.29.4, 1.30.0, 1.31.0 (`tls-attacker-reproducibility`); 1.31.0 by default (`performance-benchmarking`) | OpenSSL (defo-project ECH fork) | `openssl-3.4.1-ECH` branch |
| `localhost/apache-ech`      | Apache httpd (defo-project fork) | `trunk` (2.5.x dev), pinned to commit `0043400`                                                         | OpenSSL (defo-project ECH fork) | `openssl-3.4.1-ECH` branch |
| `localhost/nginx-boringssl` | nginx (built from source)        | 1.29.4, 1.30.0, 1.31.0                                                                                  | Google BoringSSL                | tag `0.20260803.0`         |

`nginx-boringssl` is only used by `tls-attacker-reproducibility/` (BoringSSL has no configurable `ssl_ech_file` directive in nginx).
