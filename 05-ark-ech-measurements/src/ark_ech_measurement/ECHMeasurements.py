import scamper
import base64
from loguru import logger


class ECHMeasurements:
    def __init__(self, ctrl: scamper.ScamperCtrl) -> None:
        self.ctrl = ctrl

    def dns_a(
        self,
        hostname: str,
        instance: scamper.ScamperInst | None = None,
        sync: bool = False,
    ) -> scamper.ScamperHost | scamper.ScamperTask:
        logger.info(f"Retrieving A record for {hostname} on {instance.shortname}")
        return self.ctrl.do_dns(hostname, sync=sync, inst=instance)

    def tls_no_ech(
        self,
        addr: str,
        url: str,
        instance: scamper.ScamperInst | None = None,
        sync: bool = False,
    ) -> scamper.ScamperHttp | scamper.ScamperTask:
        logger.info("Scheduling HTTP connection request without ECH")
        return self.ctrl.do_http(addr, url, sync=sync, inst=instance, limit_time=5)

    def tls_ech_grease(
        self,
        addr: str,
        url: str,
        instance: scamper.ScamperInst | None = None,
        sync: bool = False,
    ) -> scamper.ScamperHttp | scamper.ScamperTask:
        logger.info("Scheduling HTTP connection request with ECH grease")
        grease = self.ctrl.do_http(addr, url, ech_grease=True, sync=sync, inst=instance)
        return grease

    def tls_ech_with_retry_options(
        self,
        addr: str,
        url: str,
        ecl: str | None,
        instance: scamper.ScamperInst | None = None,
        sync: bool = False,
    ) -> scamper.ScamperHttp | scamper.ScamperTask:

        if ecl is None:
            grease = self.tls_ech_grease(addr, url, instance=instance, sync=True)
            if not grease.ech_retry_config:
                raise RuntimeError(f"No retry config for {url} retrieved")
            ecl = base64.b64encode(grease.ech_retry_config).decode("utf-8")

        logger.info("Scheduling HTTP connection with ECH")
        return self.ctrl.do_http(
            addr, url, ech_config_list=ecl, inst=instance, sync=sync
        )

    def measure_target(
        self,
        hostname: str,
        url: str | None,
        ecl: str | None,
        instance: str | None = None,
        sync: bool = False,
    ) -> dict:
        if sync:
            return self.measure_target_sync(hostname, url, ecl, instance, sync)
        else:
            raise Exception("Not implemented")

    def measure_target_sync(
        self,
        hostname: str,
        url: str | None,
        ecl: str | None,
        instance: str | None = None,
        sync: bool = False,
    ) -> dict:
        a_records = self.dns_a(hostname, instance, sync).ans_addrs()
        if len(a_records) == 0:
            raise RuntimeError(f"Could not resolve {hostname}")
        ip_addr = a_records[0]
        if url is None:
            url = f"https://{hostname}/"

        return {
            "dns": a_records,
            "tls_no_ech": self.tls_no_ech(ip_addr, url, instance, sync).status_code,
            # "tls_grease": str(self.tls_ech_grease(ip_addr, url).ech_status),
            "tls_ech": str(
                self.tls_ech_with_retry_options(
                    ip_addr, url, ecl, instance, sync
                ).ech_status
            ),
        }
