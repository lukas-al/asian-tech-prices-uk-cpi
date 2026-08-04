from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "uk-tech-prices-matplotlib"),
)

import matplotlib.pyplot as plt

from uk_tech_prices.aggregate import (
    add_inflation_rates,
    construct_custom_aggregate,
    select_components,
)
from uk_tech_prices.backcast import backcast_cdids, build_uk_backcasts
from uk_tech_prices.ons import download_series, load_component_data, verify_snapshot
from uk_tech_prices.paths import (
    CHART_DIR,
    CONFIG_DIR,
    INTERIM_DIR,
    PROCESSED_DIR,
    RAW_ONS_DIR,
    TABLE_DIR,
    ensure_project_directories,
)


def load_basket(path: Path | None = None) -> pd.DataFrame:
    basket_path = path or CONFIG_DIR / "uk_tech_basket.csv"
    basket = pd.read_csv(basket_path, dtype={"coicop5_code": str})
    required = {
        "coicop5_code",
        "index_series_id",
        "weight_series_id",
        "include_core",
    }
    missing = required - set(basket.columns)
    if missing:
        raise ValueError(f"basket file is missing columns: {sorted(missing)}")
    return basket


def load_subaggregates(path: Path | None = None) -> dict[str, list[str]]:
    subaggregate_path = path or CONFIG_DIR / "uk_tech_subaggregates.csv"
    frame = pd.read_csv(subaggregate_path, dtype={"coicop5_code": str})
    return (
        frame.groupby("subaggregate", sort=False)["index_series_id"]
        .apply(list)
        .to_dict()
    )


def all_cdids(basket: pd.DataFrame) -> list[str]:
    return sorted(
        set(basket["index_series_id"].str.upper())
        | set(basket["weight_series_id"].str.upper())
    )


def download_uk_data(*, refresh: bool = False) -> pd.DataFrame:
    ensure_project_directories()
    basket = load_basket()
    cdids = sorted(set(all_cdids(basket)) | set(backcast_cdids()))
    return download_series(cdids, RAW_ONS_DIR, refresh=refresh)


def _build_one(
    name: str,
    basket: pd.DataFrame,
    indices: pd.DataFrame,
    weights: pd.DataFrame,
    component_ids: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected_indices, selected_weights = select_components(
        basket, indices, weights, component_ids
    )
    strict = construct_custom_aggregate(
        selected_indices, selected_weights, require_complete=True
    )
    available = construct_custom_aggregate(
        selected_indices, selected_weights, require_complete=False
    )
    strict_rates = add_inflation_rates(strict["index_2015_100"], name)
    diagnostics = strict.add_prefix(f"{name}_strict_").join(
        available.add_prefix(f"{name}_available_"), how="outer"
    )
    return strict_rates, diagnostics


def _save_charts(result: pd.DataFrame) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")

    index_columns = [column for column in result if column.endswith("_index")]
    fig, ax = plt.subplots(figsize=(11, 6))
    result[index_columns].plot(ax=ax, linewidth=1.8)
    ax.set_title("UK CPI technology-goods indices")
    ax.set_ylabel("2015 = 100")
    ax.set_xlabel("")
    ax.legend([column.removesuffix("_index").replace("_", " ") for column in index_columns])
    fig.tight_layout()
    fig.savefig(CHART_DIR / "uk_tech_indices.png", dpi=180)
    plt.close(fig)

    inflation_columns = [
        column for column in result if column.endswith("_12m_pct")
    ]
    fig, ax = plt.subplots(figsize=(11, 6))
    result[inflation_columns].plot(ax=ax, linewidth=1.6)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("UK CPI technology-goods inflation")
    ax.set_ylabel("12-month change, %")
    ax.set_xlabel("")
    ax.legend(
        [
            column.removesuffix("_12m_pct").replace("_", " ")
            for column in inflation_columns
        ]
    )
    fig.tight_layout()
    fig.savefig(CHART_DIR / "uk_tech_inflation.png", dpi=180)
    plt.close(fig)


def build_uk_indices() -> pd.DataFrame:
    ensure_project_directories()
    basket = load_basket()
    verify_snapshot(RAW_ONS_DIR)
    indices, weights_by_weight_id, metadata = load_component_data(basket, RAW_ONS_DIR)

    indices.to_csv(INTERIM_DIR / "ons_uk_component_indices.csv", index_label="date")
    weights_by_weight_id.to_csv(
        INTERIM_DIR / "ons_uk_component_weights.csv", index_label="year"
    )
    metadata.to_csv(INTERIM_DIR / "ons_uk_series_metadata.csv", index=False)

    core_ids = basket.loc[basket["include_core"], "index_series_id"].tolist()
    aggregate_specs = {
        "headline": core_ids,
        "ex_games": [cdid for cdid in core_ids if cdid != "L7H9"],
        **load_subaggregates(),
    }

    result_parts: list[pd.DataFrame] = []
    diagnostic_parts: list[pd.DataFrame] = []
    for name, component_ids in aggregate_specs.items():
        rates, diagnostics = _build_one(
            name, basket, indices, weights_by_weight_id, component_ids
        )
        result_parts.append(rates)
        diagnostic_parts.append(diagnostics)

    result = pd.concat(result_parts, axis=1).sort_index()
    diagnostics = pd.concat(diagnostic_parts, axis=1).sort_index()
    result.index.name = "date"
    diagnostics.index.name = "date"

    result.to_csv(PROCESSED_DIR / "uk_tech_indices.csv")
    diagnostics.to_csv(PROCESSED_DIR / "uk_tech_aggregation_diagnostics.csv")
    result.tail(24).to_csv(TABLE_DIR / "latest_uk_tech_indices.csv")
    _save_charts(result)
    build_uk_backcasts(result)
    return result


def run_all(*, refresh: bool = False) -> pd.DataFrame:
    download_uk_data(refresh=refresh)
    return build_uk_indices()
