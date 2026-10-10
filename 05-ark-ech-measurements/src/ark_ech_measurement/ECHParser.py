import base64
import scamper
import json
from urllib.parse import urlparse


def to_str(val) -> str | None:
    if val is not None:
        return str(val)
    return None


def parse_dns(measurement: scamper.ScamperHost) -> dict:

    answers = []
    for answer in measurement.ans():
        if answer.addr != None:
            answers += [str(answer.addr)]
        if answer.https != None:
            for param_index in range(answer.https.paramc):
                param = answer.https.param(param_index)
                if param.key == "ech":
                    answers += [base64.b64encode(param.val).decode("utf-8")]

    return {
        "inst": measurement.cycle.hostname,
        "dns_tx": to_str(measurement.tx),
        "dns_rx": to_str(measurement.rx),
        "ip.src": to_str(measurement.src),
        "ip.dst": to_str(measurement.dst),
        "qtype": measurement.qtype,
        "qclass": measurement.qclass,
        "qname": measurement.qname,
        "error": measurement.errmsg,
        "stop_reason": measurement.stop_reason_str,
        "rcode": measurement.rcode,
        "ancount": measurement.ancount,
        "udpsize": measurement.udpsize,
        "answer": ",".join(answers),
    }


def parse_http(measurement: scamper.ScamperHttp) -> dict:

    retry_config = (
        base64.b64encode(measurement.ech_retry_config).decode()
        if measurement.ech_retry_config
        else None
    )
    http_result = {
        "inst": measurement.cycle.hostname,
        "ip.src": str(measurement.src),
        "ip.dst": str(measurement.dst),
        "tcp.srcport": measurement.sport,
        "tcp.dstport": measurement.dport,
        "url": measurement.url,
        "status_code": measurement.status_code,
        "stop_reason": measurement.stop_reason_str,
        "ech_status": str(measurement.ech_status),
        "ech_retry_config": retry_config,
        "ech_outer_sni": measurement.ech_outer_sni,
        "hsrtt": to_str(measurement.hsrtt),
        # TODO: RTT is not exposed but contained in the file.
        # However it is lower than subtracting the tx and rx of the TLS transmissions -> TCP RTT
        "tls_rx": [],
        "tls_tx": [],
        "hdr_rx": [],
        "hdr_tx": [],
        "data_tx": [],
        "data_rx": [],
    }

    for buf in measurement.bufs():
        http_result[f"{buf.type_str}_{'tx' if buf.is_tx() else 'rx'}"] += [
            to_str(buf.timestamp)
        ]
    return http_result


def get_src(d: dict):
    return (
        d.get("dns_HTTPS_ip.src")
        or d.get("dns_A_ip.src")
        or d.get("ip.src")
        or d.get("ech_ip.src")
    )


def get_target(d: dict):
    return (
        d.get("dns_A_qname")
        or d.get("dns_HTTPS_qname")
        or urlparse(d.get("url") or d.get("ech_url")).netloc
    )


def read_file(filename: str) -> dict:
    results = {}
    https_request_count = {}
    with scamper.ScamperFile(filename) as file:
        for measurement in file:
            if isinstance(measurement, scamper.ScamperHost):
                parsed_dns_query = parse_dns(measurement)
                result = {
                    f"dns_{parsed_dns_query['qtype']}_{k}": v
                    for k, v in parsed_dns_query.items()
                }
            elif isinstance(measurement, scamper.ScamperHttp):
                result = parse_http(measurement)

            elif isinstance(measurement, scamper.ScamperList) or isinstance(
                measurement, scamper.ScamperCycle
            ):
                continue
            else:
                print("ignore unknown captured measurement")
                return measurement

            target_key = f"{get_target(result)}-{measurement.cycle.hostname}"

            if isinstance(measurement, scamper.ScamperHttp):
                if target_key in https_request_count:
                    https_request_count[target_key] += 1
                else:
                    https_request_count[target_key] = 0

                match https_request_count[target_key]:
                    case 0:
                        # No prefix pure tls
                        pass
                    case 1:
                        result = {f"grease_{k}": v for k, v in result.items()}
                    case 2:
                        result = {f"ech_{k}": v for k, v in result.items()}
                    case _:
                        print(result)
                        print("error, more https requests per target than possible")

            if target_key in results:
                for key in result:
                    if key in results[target_key]:
                        print(f"Overriding key {key}")
                results[target_key] = {
                    **results[target_key],
                    "target": get_target(result),
                    **result,
                }
            else:
                results[target_key] = result
    return results
