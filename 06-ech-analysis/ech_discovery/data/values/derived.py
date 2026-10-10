from ndpi.value_store import ValueStore, fmt_percent

from ech_discovery.data.ranges import ALL, TimeRange
from ech_discovery.data.values.common import RANGES_FOR_VALUES, key_fn, roles


def register_derived(
    store: ValueStore, ranges: tuple[TimeRange, ...] = RANGES_FOR_VALUES
) -> ValueStore:
    """Values computed from other (already collected) entries."""
    for time_range in ranges:
        key = key_fn(time_range)

        for role_key in roles:
            if time_range == ALL:
                continue
            store.register(
                key(f"measurement{role_key}Duration"),
                (
                    store[key(f"measurement{role_key}EndDate")].date()
                    - store[key(f"measurement{role_key}StartDate")].date()
                ).days
                + 1,
            )
        failed = store[key("echFailAfterProvidingRetryLast")]
        successful = store[key("echAcceptedSldLast")]
        store.register(
            key("echFailAfterProvidingRetryShareLast"),
            failed / (failed + successful) * 100,
            fmt=fmt_percent(digits=0),
        )

        store.register(
            key("echSupportEndOfMeasuremetOthers"),
            100
            - store[key("echSupportEndOfMeasurementLast")]
            - store[key("echSupportEndOfMeasurementNXDomainLast")]
            - store[key("echSupportEndOfMeasurementRetryEmptyLast")],
            fmt=fmt_percent(digits=1),
        )
    return store


def register_derived_durations(
    store: ValueStore,
) -> ValueStore:
    """Values computed from other (already collected) entries."""
    for role_key in roles:
        store.register(
            f"allMeasurement{role_key}Duration",
            store[f"mainMeasurement{role_key}Duration"]
            + store[f"followupMeasurement{role_key}Duration"],
        )
    return store
