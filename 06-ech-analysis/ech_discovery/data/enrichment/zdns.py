import polars as pl
from ech_discovery.data.columns import Columns as C

ech_field = pl.col(C.ech).is_not_null()
