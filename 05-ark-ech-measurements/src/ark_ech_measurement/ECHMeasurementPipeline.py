from datetime import timedelta
import scamper
import base64
from loguru import logger


class ECHMeasurementPipeline:
    def __init__(self, domain, url, inst, ctrl):
        self.domain = domain
        self.url = url
        self.inst = inst
        self.ctrl = ctrl
        self.stage = "AWAITING_HTTPS_RR"
        self.addr = None
        self.ech_retry_config = None
        self.results = {}
        self.done = False
        self.timeout = timedelta(seconds=4)

    def start(self):
        self.ctrl.do_dns(
            self.domain, qtype="HTTPS", inst=self.inst, wait_timeout=self.timeout
        )

    def advance(self, response: scamper.ScamperHost | scamper.ScamperHttp):
        if self.done:
            return
        if self.stage == "AWAITING_HTTPS_RR":
            self.ctrl.do_dns(
                self.domain, qtype="A", inst=self.inst, wait_timeout=self.timeout
            )
            self.stage = "AWAITING_DNS"

        elif self.stage == "AWAITING_DNS":
            if (response.stop_reason_str != "done") or (len(response.ans_addrs()) == 0):
                self.done = True
                raise RuntimeError(f"Could not resolve {self.domain}")
            self.addr = response.ans_addrs()[0]
            if self.url is None:
                self.url = f"https://{self.domain}/"

            self.ctrl.do_http(
                self.addr, self.url, inst=self.inst, limit_time=self.timeout
            )
            self.stage = "AWAITING_HTTP"

        elif self.stage == "AWAITING_HTTP":
            if response.stop_reason_str != "done":
                self.done = True
                raise RuntimeError(f"Could not connect to with http {self.domain}")
            self.ctrl.do_http(
                self.addr,
                self.url,
                ech_grease=True,
                inst=self.inst,
                limit_time=self.timeout,
            )
            self.stage = "AWAITING_GREASE"

        elif self.stage == "AWAITING_GREASE":
            if response.stop_reason_str != "done":
                self.done = True
                raise RuntimeError(
                    f"Could not connect to with ech grease {self.domain}"
                )
            if response.ech_retry_config is None:
                self.done = True
                return

            self.ech_retry_config = base64.b64encode(response.ech_retry_config).decode(
                "utf-8"
            )
            self.ctrl.do_http(
                self.addr,
                self.url,
                ech_config_list=self.ech_retry_config,
                inst=self.inst,
                limit_time=self.timeout,
            )
            self.stage = "AWAITING_ECH"

        elif self.stage == "AWAITING_ECH":
            if response.stop_reason_str != "done":
                self.done = True
                raise RuntimeError(f"Could not connect to with ech {self.domain}")
            self.done = True
