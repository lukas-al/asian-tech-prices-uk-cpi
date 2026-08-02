from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def validate_inputs(indices: pd.DataFrame, weights: pd.DataFrame, base_year: int) -> None:
    if not isinstance(indices.index, pd.DatetimeIndex):
        raise TypeError("indices must have a pandas DatetimeIndex")
    if not indices.index.is_monotonic_increasing or indices.index.has_duplicates:
        raise ValueError("index dates must be unique and increasing")
    if indices.empty:
        raise ValueError("indices are empty")
    if set(indices.columns) != set(weights.columns):
        raise ValueError("indices and weights must have the same component columns")
    if base_year not in weights.index:
        raise ValueError(f"weights do not contain base year {base_year}")
    if (weights <= 0).any().any():
        raise ValueError("all component weights must be positive")


def construct_custom_aggregate(
    indices: pd.DataFrame,
    weights: pd.DataFrame,
    *,
    base_year: int = 2015,
    require_complete: bool = True,
) -> pd.DataFrame:
    """Construct an ONS-style custom CPI aggregate.

    Published component indices are first unchained. January price relatives use
    the previous December as their base; February to December use the current
    January. The component relatives are averaged with the applicable annual
    weights, chained together, and re-referenced so the base-year average is 100.

    The public MM23 component-weight CDIDs contain one observation per year. That
    annual weight is therefore used for all months in the year. The implementation
    can be extended to separate January and February-to-December weights if a
    historical double-weight dataset is added.
    """

    indices = indices.sort_index().copy()
    weights = weights.sort_index().copy()
    validate_inputs(indices, weights, base_year)

    first_date = pd.Timestamp(base_year, 1, 1)
    indices = indices.loc[indices.index >= first_date]
    if indices.empty or first_date not in indices.index:
        raise ValueError(f"indices must contain January {base_year}")

    rows: list[dict[str, float | int | pd.Timestamp]] = []
    previous_chained: float | None = None

    for date, current in indices.iterrows():
        year = int(date.year)
        month = int(date.month)
        if year not in weights.index:
            continue

        annual_weights = weights.loc[year].astype(float)
        if month == 1:
            if year == base_year:
                component_relatives = pd.Series(100.0, index=indices.columns)
            else:
                previous_december = date - pd.offsets.MonthBegin(1)
                if previous_december not in indices.index:
                    raise ValueError(f"missing previous December needed for {date:%Y-%m}")
                component_relatives = current / indices.loc[previous_december] * 100
        else:
            january = pd.Timestamp(year, 1, 1)
            if january not in indices.index:
                raise ValueError(f"missing January needed for {date:%Y-%m}")
            component_relatives = current / indices.loc[january] * 100

        available = component_relatives.notna() & annual_weights.notna()
        if require_complete and not available.all():
            missing = list(component_relatives.index[~available])
            rows.append(
                {
                    "date": date,
                    "unchained_index": np.nan,
                    "chained_index_jan2015_100": np.nan,
                    "components_available": int(available.sum()),
                    "weight_coverage": float(
                        annual_weights[available].sum() / annual_weights.sum()
                    ),
                    "missing_components": " ".join(missing),
                }
            )
            continue
        if not available.any():
            continue

        used_weights = annual_weights[available]
        unchained = float(
            np.average(component_relatives[available], weights=used_weights)
        )

        if date == first_date:
            chained = 100.0
        elif month == 1:
            if previous_chained is None:
                chained = np.nan
            else:
                chained = previous_chained * unchained / 100
        else:
            january_rows = [row for row in rows if row["date"] == pd.Timestamp(year, 1, 1)]
            january_chained = (
                float(january_rows[0]["chained_index_jan2015_100"])
                if january_rows
                else np.nan
            )
            chained = january_chained * unchained / 100

        rows.append(
            {
                "date": date,
                "unchained_index": unchained,
                "chained_index_jan2015_100": chained,
                "components_available": int(available.sum()),
                "weight_coverage": float(used_weights.sum() / annual_weights.sum()),
                "missing_components": "",
            }
        )
        if np.isfinite(chained):
            previous_chained = chained

    result = pd.DataFrame(rows).set_index("date").sort_index()
    base_mask = result.index.year == base_year
    base_average = result.loc[base_mask, "chained_index_jan2015_100"].mean()
    if not np.isfinite(base_average):
        raise ValueError(f"cannot calculate a complete {base_year} reference average")
    result["index_2015_100"] = result["chained_index_jan2015_100"] / base_average * 100
    return result


def select_components(
    basket: pd.DataFrame,
    index_data: pd.DataFrame,
    weight_data: pd.DataFrame,
    index_ids: Iterable[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected_index_ids = list(index_ids)
    mapping = basket.set_index("index_series_id")["weight_series_id"].to_dict()
    selected_weight_ids = [mapping[index_id] for index_id in selected_index_ids]

    selected_indices = index_data[selected_index_ids].copy()
    selected_weights = weight_data[selected_weight_ids].copy()
    selected_weights.columns = selected_index_ids
    return selected_indices, selected_weights


def add_inflation_rates(index: pd.Series, prefix: str) -> pd.DataFrame:
    frame = pd.DataFrame({f"{prefix}_index": index})
    frame[f"{prefix}_1m_pct"] = index.pct_change(fill_method=None) * 100
    frame[f"{prefix}_3m_annualised_pct"] = (
        (index / index.shift(3)) ** 4 - 1
    ) * 100
    frame[f"{prefix}_12m_pct"] = index.pct_change(12, fill_method=None) * 100
    return frame

