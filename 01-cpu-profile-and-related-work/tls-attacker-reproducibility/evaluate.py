#!/usr/bin/env python3
"""Walk a results/ tree and report ECH-support verdict per (server, version, variant).

For each workflow output, classifies the server's reply as one of:
  - alert:<desc>     server sent a TLS Alert
  - unknown-ee       TLS-Attacker emitted an <UnknownHandshakeMessage> with
                     assumedType=8 (EncryptedExtensions).  This typically means
                     the EncryptedExtensions carried an ECH-specific extension
                     (e.g. encrypted_client_hello with retry_configs) that
                     TLS-Attacker's parser doesn't recognise.  That is a strong
                     sign the server actually processed the ECH extension.
  - ok               handshake completed without those anomalies
  - missing          no out.xml was produced for that workflow
  - parse-error      out.xml exists but isn't well-formed XML
"""

import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

WORKFLOWS = [
    "TLS-grease",
    "niere-unknown-extension-with-value",
    "parsable-ech-extension",
    "unparsable-ech-as-raw-extension",
]

SHORT_WF = {
    "TLS-grease": "grease",
    "niere-unknown-extension-with-value": "niere",
    "parsable-ech-extension": "parsable-ech",
    "unparsable-ech-as-raw-extension": "unparsable-ech",
}

# TLS AlertDescription byte values (RFC 8446 §6 + ECH draft).
ALERT_DESCRIPTIONS = {
    0: "close_notify",
    10: "unexpected_message",
    20: "bad_record_mac",
    21: "decryption_failed_RESERVED",
    22: "record_overflow",
    30: "decompression_failure",
    40: "handshake_failure",
    41: "no_certificate_RESERVED",
    42: "bad_certificate",
    43: "unsupported_certificate",
    44: "certificate_revoked",
    45: "certificate_expired",
    46: "certificate_unknown",
    47: "illegal_parameter",
    48: "unknown_ca",
    49: "access_denied",
    50: "decode_error",
    51: "decrypt_error",
    60: "export_restriction_RESERVED",
    70: "protocol_version",
    71: "insufficient_security",
    80: "internal_error",
    86: "inappropriate_fallback",
    90: "user_canceled",
    100: "no_renegotiation",
    109: "missing_extension",
    110: "unsupported_extension",
    111: "certificate_unobtainable",
    112: "unrecognized_name",
    113: "bad_certificate_status_response",
    114: "bad_certificate_hash_value",
    115: "unknown_psk_identity",
    116: "certificate_required",
    120: "no_application_protocol",
    121: "ech_required",
}
ALERT_LEVELS = {1: "warning", 2: "fatal"}

# TLS handshake message types we care about flagging when they appear inside
# an <UnknownHandshakeMessage> (i.e. TLS-Attacker couldn't parse the body).
# Type 8 = EncryptedExtensions is the ECH retry-config carrier.
HANDSHAKE_TYPE_ENCRYPTED_EXTENSIONS = 8


def parse_byte(s):
    """Parse a TLS-Attacker <originalValue> byte field.

    These come in as decimal ('2', '50'), hex with spaces ('00 32'), or
    plain hex ('32'). Returns int or None.
    """
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    parts = s.split()
    token = parts[0]
    if token.isdigit():
        v = int(token, 10)
        if v < 256:
            return v
    try:
        return int(token, 16)
    except ValueError:
        return None


def classify(outxml_path):
    """Examine one workflow trace.

    Returns a tuple. First element is the anomaly kind:
      ("alert", level_name, desc_name)
      ("unknown-ee",)
      ("ok",)
      ("parse-error",)
    """
    try:
        root = ET.parse(outxml_path).getroot()
    except (ET.ParseError, OSError):
        return ("parse-error",)

    for alert in root.iter("Alert"):
        lvl_byte = parse_byte(alert.findtext("level/originalValue"))
        desc_byte = parse_byte(alert.findtext("description/originalValue"))
        lvl = ALERT_LEVELS.get(
            lvl_byte, f"lvl{lvl_byte}" if lvl_byte is not None else "?"
        )
        desc = ALERT_DESCRIPTIONS.get(
            desc_byte, f"desc{desc_byte}" if desc_byte is not None else "?"
        )
        return ("alert", lvl, desc)

    # UnknownHandshakeMessage with assumedType=8 indicates an EncryptedExtensions
    # body that TLS-Attacker couldn't parse (most often: contains an ECH-specific
    # extension like encrypted_client_hello with retry_configs; from manual inspection).
    for msg in root.iter("UnknownHandshakeMessage"):
        t = parse_byte(msg.findtext("assumedType/originalValue"))
        if t == HANDSHAKE_TYPE_ENCRYPTED_EXTENSIONS:
            return ("unknown-ee",)

    return ("ok",)


def cell(state):
    """Render a per-workflow state for the table / TSV."""
    if state == "missing":
        return "missing"
    kind = state[0]
    if kind == "ok":
        return "-"
    if kind == "alert":
        return state[2]  # description ("decode_error", …)
    if kind == "unknown-ee":
        return "unk-ee"
    if kind == "parse-error":
        return "parse-error"
    return "?"


def is_anomaly(state):
    """True if this workflow's response was anything other than a clean handshake."""
    if state == "missing":
        return False
    return state[0] in ("alert", "unknown-ee")


def verdict(states):
    """
    Rules in priority order:
      1. unparsable-ech is anomalous but niere isn't → server recognises 0xFE0D.
         Refine the message with the kind of anomaly (alert vs unknown-ee).
      2. parsable-ech is anomalous but grease isn't → server parses ECH content.
      3. All four anomalies of the same kind → handshake broken (inconclusive).
      4. All missing → server unreachable.
      5. Otherwise → not ECH-aware.
    """
    s_grease = states.get("TLS-grease")
    s_niere = states.get("niere-unknown-extension-with-value")
    s_parsable = states.get("parsable-ech-extension")
    s_unparsable = states.get("unparsable-ech-as-raw-extension")

    if is_anomaly(s_unparsable) and not is_anomaly(s_niere):
        kind = s_unparsable[0]
        if kind == "alert":
            return f"ECH-aware (rejects 0xFE0D with {s_unparsable[2]})"
        if kind == "unknown-ee":
            return "ECH-aware (server sends ECH-tagged EncryptedExtensions)"

    if is_anomaly(s_parsable) and not is_anomaly(s_grease):
        kind = s_parsable[0]
        if kind == "alert":
            return f"ECH-aware (rejects parsable ECH with {s_parsable[2]})"
        if kind == "unknown-ee":
            return "ECH-aware (server processes parsable ECH)"

    if all(is_anomaly(states.get(w)) for w in WORKFLOWS):
        return "Handshake broken (all workflows anomalous): inconclusive"
    if all(states.get(w) == "missing" for w in WORKFLOWS):
        return "No output (server unreachable?)"
    return "Not ECH-aware"


def find_test_dirs(root):
    """Yield (server, version, variant, path) for every directory holding .done."""
    root = Path(root)
    for done in sorted(root.rglob(".done")):
        path = done.parent
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            continue
        if len(parts) != 3:
            continue
        server, version, variant = parts
        yield server, version, variant, path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results_dir", help="Path to the results/ directory")
    args = ap.parse_args(argv)

    rows = []
    for server, version, variant, path in find_test_dirs(args.results_dir):
        states = {}
        for wf in WORKFLOWS:
            outxml = path / f"{wf}.out.xml"
            states[wf] = classify(outxml) if outxml.exists() else "missing"
        v = verdict(states)
        # nginx's ssl_ech_file is #ifdef'd on SSL_OP_ECH_GREASE (a defo-OpenSSL
        # macro); BoringSSL doesn't define it, so the directive is parsed and
        # silently skipped. ECH is therefore never active in this variant, so
        if server == "nginx" and variant == "boringssl":
            v = "ECH NEVER ENABLED on BoringSSL (see server.log)"
        rows.append((server, version, variant, states, v))

    if not rows:
        print(
            f"No completed test results found under {args.results_dir}", file=sys.stderr
        )
        return 0

    short_headers = (
        ["server", "version", "variant"]
        + [SHORT_WF[w] for w in WORKFLOWS]
        + ["verdict"]
    )
    fmt_rows = [
        [server, version, variant] + [cell(states[w]) for w in WORKFLOWS] + [v]
        for server, version, variant, states, v in rows
    ]
    widths = [
        max(len(h), *(len(r[i]) for r in fmt_rows)) for i, h in enumerate(short_headers)
    ]

    def line(cols):
        return "  ".join(c.ljust(w) for c, w in zip(cols, widths))

    print(line(short_headers))
    print(line(["-" * w for w in widths]))
    for r in fmt_rows:
        print(line(r))

    headers = ["server", "version", "variant"] + WORKFLOWS + ["verdict"]
    summary_path = Path(args.results_dir) / "summary.tsv"
    with summary_path.open("w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(headers)
        for server, version, variant, states, v in rows:
            w.writerow(
                [server, version, variant]
                + [cell(states[wf]) for wf in WORKFLOWS]
                + [v]
            )
    print(f"\nWrote {summary_path}", file=sys.stderr)

    boringssl_rows = [r for r in rows if r[0] == "nginx" and r[2] == "boringssl"]
    if boringssl_rows:
        print("\nWARNING: nginx-BoringSSL rows did NOT exercise ECH.", file=sys.stderr)
        print(
            "  nginx's ssl_ech_file directive is #ifdef'd on SSL_OP_ECH_GREASE",
            file=sys.stderr,
        )
        print(
            "  (a defo-OpenSSL macro); BoringSSL doesn't define it, so the",
            file=sys.stderr,
        )
        print(
            "  directive is parsed, but does not cause different behavior. Confirm via this line",
            file=sys.stderr,
        )
        print("  in each variant's server.log:", file=sys.stderr)
        print(
            '    [warn] "ssl_ech_file" is not supported on this platform, ignored',
            file=sys.stderr,
        )
        print("  Affected logs:", file=sys.stderr)
        for server, version, variant, _states, _v in boringssl_rows:
            print(
                f"    {Path(args.results_dir) / server / version / variant / 'server.log'}",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
