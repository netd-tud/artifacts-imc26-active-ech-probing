import click

from ech_discovery.data.ranges import DATED_RANGES, DEFAULT_RANGES, RANGES


def range_option(default=DEFAULT_RANGES):
    return click.option(
        "--range",
        "range_names",
        multiple=True,
        type=click.Choice(RANGES),
        default=default,
        show_default=True,
        help="Measurement period(s) to aggregate",
    )


@click.group()
def aggregate():
    pass


@aggregate.command()
def multi_ech_domains():
    """Domain sets (multi-ECH, Cloudflare+Meta); range-independent."""
    from ech_discovery.data.aggregates.multi_ech import calculate_multi_ech_domains

    calculate_multi_ech_domains()


@aggregate.command()
def follow_domains():
    """Domains that accepted ECH on the follow date (follow-ech-domains); range-independent."""
    from ech_discovery.data.aggregates import errors

    errors.extract_follow_domains()


@aggregate.command()
@range_option(DATED_RANGES)
def public_names(range_names):
    """Per-measurement domain counts per public name, tagged by outcome (stats_)."""
    from ech_discovery.data.aggregates import public_names

    for name in range_names:
        public_names.aggregate_per_measurement(RANGES[name])


@aggregate.command()
@range_option(DATED_RANGES)
def public_names_total(range_names):
    """Domain counts per public name across TCP and QUIC (total_stats_)."""
    from ech_discovery.data.aggregates import public_names

    for name in range_names:
        public_names.aggregate_totals(RANGES[name])


@aggregate.command()
@range_option(DATED_RANGES)
def latency(range_names):
    """Handshake duration percentiles and measurement duration per measurement
    (latency-stats_, meas-duration_)."""
    from ech_discovery.data.aggregates import latency

    for name in range_names:
        latency.aggregate_latency_per_measurement(RANGES[name])


@aggregate.command()
@range_option(DATED_RANGES)
def sld_counts(range_names):
    """Per-measurement count of SLDs that accepted ECH, per role and location (sld-count_)."""
    from ech_discovery.data.aggregates import measurement

    for name in range_names:
        measurement.aggregate_per_measurement(RANGES[name])


@aggregate.command()
@range_option()
@click.option(
    "--freq",
    default=None,
    help=(
        "Group by windows of this width (e.g. 5m) instead of by measurement run "
        "(timing_statistics_fine_<freq>_<range>)."
    ),
)
def timing(range_names, freq):
    """With/without-ECH handshake timing differences (timing_statistics_<range>)."""
    from ech_discovery.data.aggregates import latency

    for name in range_names:
        latency.aggregate_timing_diff_histogram_per_measurement_and_public_name(
            RANGES[name], freq=freq
        )


@aggregate.command()
@range_option()
@click.option(
    "--freq",
    default=None,
    help=(
        "Group by windows of this width (e.g. 5m) instead of by measurement run "
        "(timing_statistics_fine_<freq>_<range>)."
    ),
)
def timing_dispersion(range_names, freq):
    """Std/median absolute deviation/IQR of the with/without-ECH handshake timing difference
    (timing_dispersion_<range>)."""
    from ech_discovery.data.aggregates import latency

    for name in range_names:
        latency.aggregate_timing_diff_dispersion_per_measurement(RANGES[name], freq=freq)


@aggregate.command()
@range_option()
def timing_dispersion_time_of_day(range_names):
    """Std/median absolute deviation/IQR of the with/without-ECH handshake timing difference,
    per hour of day with all days in the range folded together
    (timing_dispersion_time_of_day_<range>)."""
    from ech_discovery.data.aggregates import latency

    for name in range_names:
        latency.aggregate_timing_diff_dispersion_per_hour_of_day(RANGES[name])


@aggregate.command()
@range_option()
def ech_config_id_per_time_and_public_name(range_names):
    """Per-minute domain counts by config id, public name, role and location, TCP+QUIC+zdns
    (ech_config_id_per_time_and_public_name_<range>)."""
    from ech_discovery.data.aggregates import config_ids

    for name in range_names:
        config_ids.ech_config_id_per_time_and_public_name(RANGES[name])


@aggregate.command()
def retry_configs_first_seen():
    """Per-measurement first-occurrence timestamps of retry configs (retry-configs-first-seen_)."""
    from ech_discovery.data.aggregates import retry_configs

    retry_configs.aggregate_per_measurement()


@aggregate.command()
def error_stats():
    """Error reasons of followed domains (error_statistics_followed_domains); range-independent."""
    from ech_discovery.data.aggregates import errors

    errors.aggregate_error_stats()


@aggregate.command()
def follow_error_asn():
    """Failed follow requests per (measurement, location, error reason, ASN) (follow_error_asn);
    range-independent."""
    from ech_discovery.data.aggregates import errors

    errors.agg_follow_error_asn()


@aggregate.command()
def cdn_domains():
    """Per-domain CDN attribution from the input list's A-record IPs (cdn_domains);
    range-independent."""
    from ech_discovery.data.aggregates import cdn

    cdn.agg_cdn_domains()


@aggregate.command()
@range_option()
def paper(range_names):
    """All aggregates feeding `data values generate` (paper numbers)."""
    from ech_discovery.data.aggregates import (
        ark,
        cdn,
        dns_status,
        errors,
        measurement,
        multi_ech,
        public_names,
    )

    for name in range_names:
        time_range = RANGES[name]
        click.echo(f"[{name}] dns_status")
        dns_status.agg_dns_status(time_range)
        click.echo(f"[{name}] quic_only_domains")
        public_names.agg_quic_only_domains(time_range)
        click.echo(f"[{name}] meta_fbsbx_domains")
        public_names.agg_meta_fbsbx_domains(time_range)

    # range-independent
    click.echo("follow_error_tlds")
    errors.agg_follow_error_tlds()
    click.echo("follow_error_asn")
    errors.agg_follow_error_asn()
    click.echo("retry_provided")
    errors.agg_retry_provided()
    click.echo("cdn_domains")
    cdn.agg_cdn_domains()
    click.echo("accepted_sld")
    measurement.agg_accepted_sld()
    click.echo("cf_meta_ns_location")
    multi_ech.agg_cf_meta_ns_location()
    click.echo("ark_timing")
    ark.agg_ark_timing()
