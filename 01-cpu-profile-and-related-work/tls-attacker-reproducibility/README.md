# Comparing Methods of Related Work and This Work

We use TLS-Attacker to compare our measurement method and the measurement method of Niere et al.:

```text
Niklas Niere, Felix Lange, Nico Heitmann, and Juraj Somorovsky. 2025. Encrypted
Client Hello (ECH) in Censorship Circumvention. In Free and Open Communications on the Internet (FOCI). 64–73.
```

## Build Instructions

The `*.jar` files and `lib/` in this directory are pre-built artifacts.
You can build them from source with `make build-jars`.

We use the version released prior to the publication of Niere et al.:

- Source: <https://github.com/tls-attacker/TLS-Attacker.git>
- Ref: tag `v7.5.1`, commit `f6f08283c6c94901fc956814b29518b79f03e552`
- Build command (from the repo root): `mvn clean install -DskipTests=true`
- Requirements: `JDK`, `maven`

## Tests Included

Each row is a `workflowTrace` XML sending a ClientHello; `evaluate.py` classifies the server's reply as an alert, an unrecognized EncryptedExtensions, or a clean handshake and compares the test cases described below.

| Test                                     | Content                                                                                                                                                                                                                                                                 |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TLS-grease.xml`                         | ClientHello with TLS GREASE extension (RFC 8701), no ECH. "ordinary unrecognized extension" compared against `parsable-ech-extension.xml`.                                                                                                                              |
| `parsable-ech-extension.xml`             | ClientHello with ECH extension (`0xfe0d`) and a well-formed ECH payload (config_id, HPKE key share, ciphertext). A different reaction from `TLS-grease.xml` is evidence the server processes the ECH extension, but not random extensions. (**Method of this work**)    |
| `niere-unknown-extension-with-value.xml` | ClientHello with an unknown, non-ECH extension type (`0x01ff`) carrying a 5-byte payload. "unrecognized extension with content" compared against `unparsable-ech-as-raw-extension.xml`.                                                                                 |
| `unparsable-ech-as-raw-extension.xml`    | ClientHello with ECH extension (`0xfe0d`) but a garbage 5-byte payload instead of a valid ECH structure. An anomaly here vs. `niere-unknown-extension-with-value.xml` is evidence the server recognizes the extension type `0xfe0d`.                                    |

## Running the Tests

```sh
make all
```

Runs `nginx apache evaluate` in sequence: builds or pulls every server variant (stock nginx and httpd, the locally-built `*-ech` images, and `nginx-boringssl`), runs all four workflows from the table above against each, then classifies the results and prints the result table (also written to `results/summary.tsv`).

Requirements: `JDK`, `podman`

Split into its parts:

```sh
make pull       # optional: pre-fetch the stock nginx/httpd images first
make nginx      # populate results/nginx/<version>/<variant>/
make apache     # populate results/apache/<version>/<variant>/
make evaluate   # classify results/, print the result table, write results/summary.tsv
```
