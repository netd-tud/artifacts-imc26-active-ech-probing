from pathlib import Path

from ndpi.value_store import ValueStore

from ech_discovery.data import loaders as loader
from ech_discovery.data.ranges import TimeRange
from ech_discovery.data.values.common import RANGES_FOR_VALUES
from ech_discovery.data.values.derived import register_derived, register_derived_durations
from ech_discovery.data.values.per_range import register_for_range
from ech_discovery.data.values.shared import register_shared


def build_store(ranges: tuple[TimeRange, ...] = RANGES_FOR_VALUES) -> ValueStore:
    store = ValueStore()

    # lazyload and shared so that polars can apply all optimizations
    stats = loader.ech_stats()
    total_stats = loader.ech_total_stats()
    total_stats_all_locations = loader.ech_total_stats_all_locations()
    latency = loader.ech_latency_stats()

    register_shared(store, total_stats)
    for time_range in ranges:
        register_for_range(
            store, time_range, stats, total_stats, total_stats_all_locations, latency
        )

    return store


def create_tex_commands(
    path: Path, ranges: tuple[TimeRange, ...] = RANGES_FOR_VALUES
) -> ValueStore:
    store = build_store(ranges)
    store.collect()
    register_derived(store, ranges)
    register_derived_durations(store)
    store.write(path)
    return store
