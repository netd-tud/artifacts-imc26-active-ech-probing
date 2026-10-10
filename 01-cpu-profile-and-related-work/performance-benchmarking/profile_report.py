#!/usr/bin/env python3
"""Compare the ECH-off vs ECH-on tests.

Reads, for each server under <results>/profile/<server>/{ech-off,ech-on}/:
  - client.json      (the Go ech-client summary: connection count + latency)
  - client-cpu.pprof  (the Go ech-client's own runtime/pprof CPU profile)
  - perf.data/symfs   (perf record: the server's call graph)
"""

import json
import os
import shutil
import subprocess
import sys

TESTS = ("ech-off", "ech-on")

# number configures indent, because the selected function is called by the preceding function
CLIENTHELLO_FUNCS = (
    ("tls_process_client_hello", 0),
    ("ossl_ech_early_decrypt", 1),
    ("tls_post_process_client_hello", 0),
    ("tls_construct_server_hello", 0),
    ("ossl_ech_calc_confirm", 1),
)
CLIENT_PPROF_FUNCS = (
    ("crypto/tls.(*Conn).clientHandshake", 0),
    ("crypto/tls.(*Conn).makeClientHello", 1),
    ("crypto/hpke.NewSender", 2),
    ("crypto/hpke.(*dhKEMPublicKey).encap", 3),
)
CLIENT_PPROF_SYMBOLS = tuple(name for name, _ in CLIENT_PPROF_FUNCS)


def parse_pprof_top(path, symbols):
    if not os.path.exists(path):
        return {}
    try:
        proc = subprocess.run(
            ["go", "tool", "pprof", "-top", "-nodecount=100000", path],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"  (could not run 'go tool pprof' on {path}: {e})", file=sys.stderr)
        return {}
    if proc.returncode != 0:
        print(
            f"  (go tool pprof failed on {path}: {proc.stderr.strip()})",
            file=sys.stderr,
        )
        return {}
    want = set(symbols)
    out = {}
    for line in proc.stdout.splitlines():
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        _flat, flatpct, _sumpct, _cum, cumpct, rest = parts
        if not (flatpct.endswith("%") and cumpct.endswith("%")):
            continue
        name = rest.split()[0]  # drop a trailing "(inline)" annotation, if any
        if name in want:
            try:
                out[name] = (float(flatpct.rstrip("%")), float(cumpct.rstrip("%")))
            except ValueError:
                continue
    return out


def perf_symbol_stats(perf_data, symfs, symbols, perf_bin=None, timeout=180):
    perf_bin = perf_bin or os.environ.get("PERF", "perf")
    if not (shutil.which(perf_bin) and os.path.exists(perf_data)):
        return 0, {}
    cmd = [perf_bin, "script", "-i", perf_data]
    if symfs and os.path.isdir(symfs):
        cmd += ["--symfs", symfs]
    cmd += ["-F", "event,ip,sym"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"  (could not run 'perf script' on {perf_data}: {e})", file=sys.stderr)
        return 0, {}
    if proc.returncode != 0:
        print(
            f"  (perf script failed on {perf_data}: {proc.stderr.strip()})",
            file=sys.stderr,
        )
        return 0, {}

    want = set(symbols)
    counts = {s: {"self": 0, "children": 0} for s in symbols}
    total = 0
    stack = []  # symbol names for the current sample, leaf (on-CPU) frame first

    def flush():
        nonlocal total
        if not stack:
            return
        total += 1
        for s in want.intersection(stack):
            counts[s]["children"] += 1
        if stack[0] in counts:
            counts[stack[0]]["self"] += 1

    for line in proc.stdout.splitlines():
        if not line.strip():
            flush()
            stack = []
        elif line[:1].isspace():
            # "\t    <addr> <symbol> [(inlined)]"
            parts = line.split(None, 2)
            if len(parts) >= 2:
                stack.append(parts[1])
        else:
            flush()  # new sample header line -- flush the previous one
            stack = []
    flush()
    return total, counts


def load_client(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def conn_count(client):
    return (client.get("ok", 0) or 0) + (client.get("warmup", 0) or 0)


def section(title, subtitle):
    print(f"\n{'-' * 78}\n {title}\n   {subtitle}\n{'-' * 78}")


def pct(off, on):
    if not off:
        return "n/a"
    return f"{(on - off) / off * 100:+.1f}%"


def report_server(server, base):
    client = {t: load_client(os.path.join(base, t, "client.json")) for t in TESTS}
    n = {t: conn_count(client[t]) for t in TESTS}
    has_perf_data = any(
        os.path.exists(os.path.join(base, t, "perf.data")) for t in TESTS
    )

    if not any(client.values()) and not has_perf_data:
        return False

    # BANNER
    print(
        f"\n{'=' * 78}\n {server.upper()}   (ECH-capable binary; ECH-off vs ECH-on)\n{'=' * 78}"
    )
    section(
        "CLIENT SIDE",
        "measured by the client itself and with pprof CPU profile",
    )
    if n["ech-off"] != n["ech-on"]:
        print(
            f" WARNING: the two tests ran a different number of connections "
            f"(off={n['ech-off']:,}  on={n['ech-on']:,}); the off→on numbers below "
            f"are not like-for-like."
        )
    ea, ok = client["ech-on"].get("ech_accepted", 0), client["ech-on"].get("ok", 0)
    if ok and ea == 0:
        print(
            " WARNING: ECH was never accepted on the ech-on test. Check the server config."
        )
    elif ok and ea != ok:
        print(
            f" WARNING: ECH was accepted on only {ea:,} of {ok:,} ech-on connections; "
            f"the ech-on profile mixes ECH and non-ECH handshakes."
        )

    # Handshake latency measured from within the client
    hoff = client["ech-off"].get("handshake_ms", {})
    hon = client["ech-on"].get("handshake_ms", {})
    if hoff and hon:
        print(f"\n Handshake latency (ms):")
        for k in ("mean", "p50", "p90", "p99", "max"):
            o, n2 = hoff.get(k), hon.get(k)
            if o is not None and n2 is not None:
                print(
                    f"   {k:<5} off={o:8.3f}  on={n2:8.3f}  Δ={n2 - o:+.3f}  ({pct(o, n2)})"
                )

    # Client CPU profile (cumulative is expressive)
    cpu = {t: os.path.join(base, t, "client-cpu.pprof") for t in TESTS}
    if all(os.path.exists(p) for p in cpu.values()):
        prof = {t: parse_pprof_top(cpu[t], CLIENT_PPROF_SYMBOLS) for t in TESTS}
        if all(prof.values()):
            print(f"\n CPU profile -- share of samples (cum%, incl. callees):")
            print(
                f"   {'function':<38}{'flat% (off → on)':>24}{'cum% (off → on, Δ)':>34}"
            )
            for sym, indent in CLIENT_PPROF_FUNCS:
                # a symbol missing from a profile was never sampled there
                # crypto/hpke.NewSender simply does not run on the ech-off test
                foff, coff2 = prof["ech-off"].get(sym, (0.0, 0.0))
                fon, con2 = prof["ech-on"].get(sym, (0.0, 0.0))
                short = sym.replace("crypto/tls.", "tls.").replace(
                    "crypto/hpke.", "hpke."
                )
                if indent:
                    short = f"{'  ' * indent}↳ {short}"
                flatstr = f"{foff:.2f}% → {fon:.2f}%"
                cumstr = f"{coff2:.2f}% → {con2:.2f}%  ({con2 - coff2:+.2f})"
                print(f"   {short:<38}{flatstr:>24}{cumstr:>34}")
        else:
            print(
                f"\n (could not read client CPU profiles with 'go tool pprof' -- is 'go' on PATH?)"
            )

        print(f"\n Manual inspection with:")
        for t in TESTS:
            print(f"   go tool pprof -http=:8081 {cpu[t]}")

    section(
        "SERVER SIDE",
        f"measured on the server with perf",
    )

    ch_names = [name for name, _ in CLIENTHELLO_FUNCS]
    ch = {
        t: perf_symbol_stats(
            os.path.join(base, t, "perf.data"), os.path.join(base, t, "symfs"), ch_names
        )
        for t in TESTS
    }
    toff, coff_counts = ch["ech-off"]
    ton, con_counts = ch["ech-on"]
    if toff and ton:
        print(f"\n CPU profile -- share of samples (cum%, incl. callees)")
        print(f"   total sampled cycles:  off={toff:,}  on={ton:,}")
        print(
            f"   {'function':<38}{'self% (off → on)':>24}{'children% (off → on, Δ)':>34}"
        )
        for name, indent in CLIENTHELLO_FUNCS:
            so = coff_counts.get(name, {}).get("self", 0)
            co = coff_counts.get(name, {}).get("children", 0)
            sn = con_counts.get(name, {}).get("self", 0)
            cn = con_counts.get(name, {}).get("children", 0)

            soff, son = so / toff * 100, sn / ton * 100
            coff2, con2 = co / toff * 100, cn / ton * 100
            label = f"{'  ' * indent}↳ {name}" if indent else name
            selfstr = f"{soff:.2f}% → {son:.2f}%"
            childstr = f"{coff2:.2f}% → {con2:.2f}%  ({con2 - coff2:+.2f})"
            print(f"   {label:<38}{selfstr:>24}{childstr:>34}")
    else:
        print(
            f"\n (skipping exact ClientHello/ServerHello ECH sample counts -- "
            f"'perf' or perf.data/symfs not available for {server}; "
            f"install perf or re-run 'make profile-{server}')"
        )

    on_data, off_data = (
        os.path.join(base, "ech-on", "perf.data"),
        os.path.join(base, "ech-off", "perf.data"),
    )
    on_symfs = os.path.join(base, "ech-on", "symfs")
    if os.path.exists(on_data):
        print(f"\n Manual inspection with:")
        print(f"   perf report -i {on_data} --symfs={on_symfs}")
        if os.path.exists(off_data):
            print(f"   perf diff --symfs={on_symfs} {off_data} {on_data}")
    return True


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "results/profile"
    if not os.path.isdir(base):
        print(
            f"no profile results at {base}; run `make profile` first", file=sys.stderr
        )
        return 1
    servers = sorted(
        d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))
    )
    any_done = False
    for server in servers:
        any_done |= report_server(server, os.path.join(base, server))
    if not any_done:
        print(f"no parseable tests under {base}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
