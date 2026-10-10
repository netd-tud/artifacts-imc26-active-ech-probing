# Performance Assessment of ECH Implementations

We perform profiling of the server and the client side.
The client is always a Go client.
We use the latest real server implementations (apache httpd and nginx).

We run against both server variants with ECH support, once with ECH enabled and once without ECH configuration.
We profile the servers with `perf record` to attribute differences to specific function calls.
The client is profiled with `runtime/pprof` inside the Go application.
To minimize the impact of profiling, we perform two runs: one to profile the client side and one to profile the server side.

## Build Instructions

The Go `ech-client` can be configured to perform ECH and non-ECH handshakes.

- Go >= 1.24 (client-side ECH comes from the standard library `crypto/tls`/`Config.EncryptedClientHelloConfigList`)
- `perf`, `taskset`, `sudo`, `podman` must be installed

```sh
make build-ech-client
make build-nginx-ech
make build-apache-ech
```

Container images build automatically when you perform a profiling run with `make profile`.

## Tests Included

| Test      | Content                                                                                                                                                                                |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `profile` | Profile apache and nginx: Perform 50,000 TLS 1.3 connections from `ech-client` once without ECH and once with a valid ECH configuration. Repeated to profile client- and server-side.  |

We create a profile report from test output under `results/profile/<server>/<ech-off|ech-on>`.

Entire test suite: `make profile`.
Subcommands exist for specific implementations or generating a report:

```sh
make profile                        # nginx + apache, then the report
make profile-nginx                  # nginx only
make profile-apache                 # apache only
make profile-report                 # create report from existing results
```
