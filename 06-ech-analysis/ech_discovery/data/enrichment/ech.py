import polars as pl

from ech_discovery.data.columns import Columns as C
from ech_discovery.data.mapper import Strings

# nordvpn's per-domain randomly generated public names
EXAMPLE_PUBLIC_NAME = r"^[A-Za-z0-9]{8}\.example\.com$"
EXAMPLE_PUBLIC_NAME_MERGED = "*.example.com"
NORDVPN_TARGET = ".nordvpn.com"


def is_example_public_name(col: str = C.ech_public_name) -> pl.Expr:
    return pl.col(col).str.contains(EXAMPLE_PUBLIC_NAME)


def is_nordvpn_target(col: str = C.target) -> pl.Expr:
    return pl.col(col).str.ends_with(NORDVPN_TARGET)


# Default selection and preselection for specific cases
ech_accepted = pl.col(C.ech_accepted)

retry_offered_but_not_accepted = (
    (pl.col(C.ech_accepted).is_null() | (pl.col(C.ech_accepted) == False))  # noqa: E712
    & pl.col(C.retry_configs).is_not_null()
    & (pl.col(C.retry_configs).list.len() > 0)
)


def config_field(field: str, col: str = C.retry_configs) -> pl.Expr:
    """`field` of every ECH configuration in `col`, as one list per row."""
    return pl.col(col).list.eval(pl.element().struct.field(field))


def replace_nordvpn_public_name(
    df: pl.LazyFrame | pl.DataFrame,
    target_col: str = C.target,
    ech_public_name_cond: pl.Expr = is_example_public_name(),
    insert_col: str = C.ech_public_name,
) -> pl.LazyFrame | pl.DataFrame:
    """Replace content in {insert_col} with `*.example.com` if {target_col} ends with `.nordvpn.com` and matches the condition"""
    return df.with_columns(
        pl.when(is_nordvpn_target(target_col) & ech_public_name_cond)
        .then(pl.lit(EXAMPLE_PUBLIC_NAME_MERGED))
        .otherwise(insert_col)
        .alias(insert_col)
    )


def _agg_per_measurement(
    df, col=C.target_sld, group_by=[C.measurement, C.role, C.location], additional_cols=[]
):
    ret = (
        df.with_columns(
            # Any on additional columns, otherwise true and false may happen and domains may be counted multiple times
            pl.col(additional_cols).fill_null(False).any().over(*group_by, col)
            if additional_cols
            else []
        )
        .group_by(*group_by, *additional_cols)
        .agg(pl.col(col).drop_nulls().n_unique())
        .sort(col)
    )
    if len(additional_cols) > 0:
        return ret.with_columns(
            # No join match = no ECH in DNS
            pl.col(*additional_cols).fill_null(False)
        )

    return ret


def agg_public_names_per_measurement(
    df,
    col=C.target_sld,
    group_by=[C.ech_public_name, C.measurement, C.role, C.location],
    additional_cols=[Strings.ech_in_dns],
):
    return _agg_per_measurement(df, col, group_by, additional_cols)


def agg_slds_per_measurement(
    df,
    col=C.target_sld,
    group_by=[C.measurement, C.role, C.location],
    additional_cols=[],
):
    return _agg_per_measurement(df, col, group_by, additional_cols)


def agg_timing_differences(
    df,
    every="100i",
    group_by=[
        C.measurement,
        C.ech_public_name,
        C.role,
        C.location,
    ],
    transform_to_ms=True,
):
    transform_ms = None
    if transform_to_ms:
        transform_ms = pl.col(C.hs_duration_diff) / 1_000

    return (
        (
            df.sort([*group_by, C.hs_duration_diff])
            .group_by_dynamic(
                C.hs_duration_diff,
                every=every,
                group_by=group_by,
            )
            .agg(pl.len())
            .collect()
        )
        .upsample(C.hs_duration_diff, every=every, group_by=group_by)
        .with_columns(
            pl.col(group_by).forward_fill(),
            pl.col(C.len).fill_null(0),
        )
        .with_columns(transform_ms)
        .with_columns(
            (100 * pl.col(C.len) / pl.col(C.len).sum()).over(group_by).alias(C.len_percent)
        )
        .sort(C.hs_duration_diff)
        .with_columns(pl.col(C.len, C.len_percent).cum_sum().name.suffix("-cum").over(group_by))
    )
