from typing import List
from urllib.parse import urlparse
import scamper


def filter_target_instances(
    ctrl: scamper.ScamperCtrl, instances: str
) -> List[scamper.ScamperVp]:
    target_instances = instances.split(",")

    if len(ctrl.vps()) > 0:
        target_instances = list(
            filter(lambda x: x.shortname in target_instances, ctrl.vps())
        )
    else:
        target_instances = [None]

    return target_instances


def filter_target_instances_primitive(
    ctrl: scamper.ScamperCtrl, primitives: List[str]
) -> List[scamper.ScamperVp]:
    target_instances = []

    if len(ctrl.vps()) > 0:
        for primitive in primitives:
            target_instances += list(filter(lambda x: primitive in x.tags, ctrl.vps()))
    else:
        target_instances = [None]

    return list(set(target_instances))


def get_target_from_measurement(
    measurement: scamper.ScamperHost | scamper.ScamperHttp,
) -> str:
    return (
        measurement.qname
        if isinstance(measurement, scamper.ScamperHost)
        else urlparse(measurement.url).netloc
    )
