from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "uk-tech-prices-matplotlib"),
)

import matplotlib.pyplot as plt

from uk_tech_prices.aggregate import add_inflation_rates, construct_custom_aggregate
from uk_tech_prices.ons import parse_ons_csv, verify_snapshot
from uk_tech_prices.paths import (
    CHART_DIR,
    CONFIG_DIR,
    PROCESSED_DIR,
    RAW_ONS_DIR,
    RAW_ONS_ITEMS_DIR,
    ensure_project_directories,
)

ITEM_ARCHIVE_URL = (
    "https://www.ons.gov.uk/file?uri=%2Feconomy%2Finflationandpriceindices%2Fadhocs%2F"
    "10673retailpriceindexrpiconsumerpricesindexincludingowneroccupiershousingcosts"
    "cpihandconsumerpriceinflationcpiitemindicesandcorrespondingweights%2F"
    "itemindicesandcorrespondingweights.xlsx"
)
ITEM_ARCHIVE_FILE = "itemindicesandcorrespondingweights.xlsx"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backcast_cdids() -> list[str]:
    mapping = pd.read_csv(CONFIG_DIR / "uk_tech_backcast_components.csv")
    return sorted(
        set(mapping["index_series_id"].str.upper())
        | set(mapping["weight_series_id"].str.upper())
    )


def download_item_archive(*, refresh: bool = False, timeout: int = 180) -> pd.DataFrame:
    """Freeze the ONS 1996–2019 item-index and item-weight archive."""
    ensure_project_directories()
    path = RAW_ONS_ITEMS_DIR / ITEM_ARCHIVE_FILE
    manifest_path = RAW_ONS_ITEMS_DIR / "manifest.csv"
    old = (
        pd.read_csv(manifest_path, dtype=str)
        if manifest_path.exists()
        else pd.DataFrame()
    )
    if refresh or not path.exists():
        response = requests.get(
            ITEM_ARCHIVE_URL,
            headers={"User-Agent": "uk-tech-prices/0.1 (reproducible research)"},
            timeout=timeout,
        )
        response.raise_for_status()
        if not response.content.startswith(b"PK"):
            raise RuntimeError("ONS item archive did not return an XLSX workbook")
        path.write_bytes(response.content)
        retrieved_at = datetime.now(UTC).isoformat()
    elif not old.empty and "retrieved_at_utc" in old:
        retrieved_at = str(old["retrieved_at_utc"].iloc[0])
    else:
        retrieved_at = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
    manifest = pd.DataFrame(
        [
            {
                "file": ITEM_ARCHIVE_FILE,
                "retrieved_at_utc": retrieved_at,
                "source_url": ITEM_ARCHIVE_URL,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
                "coverage": "January 1996 to August 2019",
            }
        ]
    )
    manifest.to_csv(manifest_path, index=False)
    return manifest


def verify_item_archive(directory: Path = RAW_ONS_ITEMS_DIR) -> Path:
    manifest_path = directory / "manifest.csv"
    path = directory / ITEM_ARCHIVE_FILE
    if not manifest_path.exists() or not path.exists():
        raise FileNotFoundError(
            "missing ONS item archive; run `uv run uk-tech download-backcast` first"
        )
    manifest = pd.read_csv(manifest_path, dtype=str)
    expected = manifest.loc[manifest["file"].eq(ITEM_ARCHIVE_FILE), "sha256"]
    if expected.empty or _sha256(path) != expected.iloc[0]:
        raise ValueError("invalid ONS item archive snapshot: checksum mismatch")
    return path


def load_item_archive(path: Path | None = None) -> pd.DataFrame:
    workbook = path or verify_item_archive()
    data = pd.read_excel(workbook, engine="calamine")
    required = {
        "Item ID",
        "Index Date",
        "Base Date",
        "Item Description",
        "CPI(H) Index",
        "CPI Weight",
    }
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"ONS item archive is missing columns: {sorted(missing)}")
    for column in ("Item ID", "Index Date", "Base Date"):
        data[column] = pd.to_numeric(data[column], errors="coerce").astype("Int64")
    for column in ("CPI(H) Index", "CPI Weight"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data


def _weighted_ratio(
    current: pd.DataFrame,
    previous: pd.DataFrame | None,
) -> tuple[float, int, float]:
    columns = ["Item ID", "CPI(H) Index", "CPI Weight"]
    current = current[columns].dropna().loc[lambda frame: frame["CPI Weight"] > 0]
    if previous is None:
        if current.empty:
            return np.nan, 0, 0.0
        ratio = np.average(current["CPI(H) Index"] / 100, weights=current["CPI Weight"])
        return float(ratio), len(current), float(current["CPI Weight"].sum())
    merged = current.merge(
        previous[["Item ID", "CPI(H) Index"]].dropna(),
        on="Item ID",
        suffixes=("_current", "_previous"),
    )
    if merged.empty:
        return np.nan, 0, 0.0
    numerator = np.average(
        merged["CPI(H) Index_current"], weights=merged["CPI Weight"]
    )
    denominator = np.average(
        merged["CPI(H) Index_previous"], weights=merged["CPI Weight"]
    )
    return float(numerator / denominator), len(merged), float(merged["CPI Weight"].sum())


def build_mobile_item_index(
    item_data: pd.DataFrame | None = None,
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """Chain a handset-only CPI index from item relatives and item weights."""
    if item_data is None:
        item_data = load_item_archive()
    mapping = pd.read_csv(CONFIG_DIR / "uk_tech_item_mapping.csv")
    selected = item_data.loc[item_data["Item ID"].isin(mapping["item_id"])].copy()
    selected = selected.loc[selected["CPI Weight"].gt(0)]
    if selected.empty:
        raise ValueError("no positive-weight mobile items found in ONS archive")

    first_year = int(selected["Index Date"].min() // 100)
    last_period = int(selected["Index Date"].max())
    last_date = pd.Timestamp(last_period // 100, last_period % 100, 1)
    dates = pd.date_range(f"{first_year}-01-01", last_date, freq="MS")
    chained = 100.0
    rows = [
        {
            "date": dates[0],
            "monthly_relative": 1.0,
            "mobile_item_index": chained,
            "items_available": 0,
            "item_weight": np.nan,
        }
    ]
    for date in dates[1:]:
        period = date.year * 100 + date.month
        if date.month == 1:
            december_base = (date.year - 1) * 100 + 12
            current = selected.loc[
                selected["Index Date"].eq(period)
                & selected["Base Date"].eq(december_base)
            ]
            if not current.empty:
                ratio, count, weight = _weighted_ratio(current, None)
            else:
                january_base = (date.year - 1) * 100 + 1
                current = selected.loc[
                    selected["Index Date"].eq(period)
                    & selected["Base Date"].eq(january_base)
                ]
                previous = selected.loc[
                    selected["Index Date"].eq(period - 89)
                    & selected["Base Date"].eq(january_base)
                ]
                ratio, count, weight = _weighted_ratio(current, previous)
        else:
            january_base = date.year * 100 + 1
            current = selected.loc[
                selected["Index Date"].eq(period)
                & selected["Base Date"].eq(january_base)
            ]
            if date.month == 2:
                ratio, count, weight = _weighted_ratio(current, None)
            else:
                previous = selected.loc[
                    selected["Index Date"].eq(period - 1)
                    & selected["Base Date"].eq(january_base)
                ]
                ratio, count, weight = _weighted_ratio(current, previous)
        if np.isfinite(ratio):
            chained *= ratio
        else:
            chained = np.nan
        rows.append(
            {
                "date": date,
                "monthly_relative": ratio,
                "mobile_item_index": chained,
                "items_available": count,
                "item_weight": weight,
            }
        )
    diagnostics = pd.DataFrame(rows).set_index("date")
    index = diagnostics["mobile_item_index"].dropna()
    annual_weight = diagnostics["item_weight"].groupby(diagnostics.index.year).median()
    annual_weight = annual_weight.loc[annual_weight.gt(0)]
    index.name = "mobile_item_index"
    annual_weight.name = "mobile_item_weight"
    return index, annual_weight, diagnostics


def _load_parent_components(selection_column: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    verify_snapshot(RAW_ONS_DIR)
    mapping = pd.read_csv(CONFIG_DIR / "uk_tech_backcast_components.csv")
    mapping = mapping.loc[mapping[selection_column]]
    indices = {}
    weights = {}
    for row in mapping.itertuples(index=False):
        indices[row.index_series_id] = parse_ons_csv(
            RAW_ONS_DIR / f"{row.index_series_id}.csv"
        ).monthly
        weights[row.index_series_id] = parse_ons_csv(
            RAW_ONS_DIR / f"{row.weight_series_id}.csv"
        ).annual
    return pd.DataFrame(indices), pd.DataFrame(weights)


def _bridge_one(
    *,
    name: str,
    selection_column: str,
    current: pd.Series,
    mobile_index: pd.Series,
    mobile_weight: pd.Series,
) -> tuple[pd.DataFrame, dict[str, object]]:
    parent_indices, parent_weights = _load_parent_components(selection_column)
    parent_indices = parent_indices.loc["1996-01-01":]
    parent_weights = parent_weights.loc[1996:]
    class_only = construct_custom_aggregate(
        parent_indices,
        parent_weights,
        base_year=1996,
        require_complete=True,
    )["chained_index_jan2015_100"].dropna()

    mobile_start_year = max(2005, int(mobile_weight.index.min()))
    combined_indices = parent_indices.join(mobile_index, how="inner").loc[
        f"{mobile_start_year}-01-01":
    ]
    combined_weights = parent_weights.copy()
    combined_weights["mobile_item_index"] = mobile_weight
    combined_weights = combined_weights.loc[mobile_start_year:].dropna()
    combined_indices = combined_indices.loc[
        combined_indices.index.year.isin(combined_weights.index)
    ]
    combined = construct_custom_aggregate(
        combined_indices,
        combined_weights,
        base_year=mobile_start_year,
        require_complete=True,
    )["chained_index_jan2015_100"].dropna()
    join_date = pd.Timestamp(mobile_start_year, 1, 1)
    combined *= class_only.loc[join_date] / combined.loc[join_date]
    bridge = pd.concat([class_only.loc[: join_date - pd.offsets.MonthBegin(1)], combined])

    splice_date = pd.Timestamp("2015-01-01")
    scaled_bridge = bridge * current.loc[splice_date] / bridge.loc[splice_date]
    extended = pd.concat(
        [scaled_bridge.loc[: splice_date - pd.offsets.MonthBegin(1)], current.loc[splice_date:]]
    )
    rates = add_inflation_rates(extended, f"historical_{name}")

    overlap = pd.concat(
        [
            add_inflation_rates(scaled_bridge, "bridge")["bridge_12m_pct"],
            add_inflation_rates(current, "current")["current_12m_pct"],
        ],
        axis=1,
    ).loc["2016-01-01":"2019-08-01"].dropna()
    difference = overlap["bridge_12m_pct"] - overlap["current_12m_pct"]
    validation = {
        "aggregate": name,
        "backcast_start": extended.first_valid_index(),
        "splice_date": splice_date,
        "overlap_end": overlap.index.max(),
        "overlap_n": len(overlap),
        "annual_rate_correlation": overlap["bridge_12m_pct"].corr(
            overlap["current_12m_pct"]
        ),
        "annual_rate_mae_pp": difference.abs().mean(),
        "annual_rate_rmse_pp": np.sqrt(np.mean(difference**2)),
        "annual_rate_bias_pp": difference.mean(),
    }
    return rates, validation


def build_uk_backcasts(current: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build and validate linked pre-COICOP5 UK technology CPI histories."""
    if current is None:
        current = pd.read_csv(
            PROCESSED_DIR / "uk_tech_indices.csv", parse_dates=["date"]
        ).set_index("date")
    mobile_index, mobile_weight, mobile_diagnostics = build_mobile_item_index()
    specs = (
        (
            "targeted_hardware",
            "include_targeted_hardware",
            current["targeted_hardware_index"],
        ),
        ("ex_games", "include_ex_games", current["ex_games_index"]),
    )
    parts = []
    validation_rows = []
    for name, selection_column, current_index in specs:
        rates, validation = _bridge_one(
            name=name,
            selection_column=selection_column,
            current=current_index.dropna(),
            mobile_index=mobile_index,
            mobile_weight=mobile_weight,
        )
        parts.append(rates)
        validation_rows.append(validation)
    result = pd.concat(parts, axis=1).sort_index()
    result.index.name = "date"
    result.to_csv(PROCESSED_DIR / "uk_tech_indices_extended.csv")
    pd.DataFrame(validation_rows).to_csv(
        PROCESSED_DIR / "uk_tech_backcast_validation.csv", index=False
    )
    mobile_diagnostics.to_csv(PROCESSED_DIR / "uk_mobile_item_backcast_diagnostics.csv")
    _save_backcast_chart(result, mobile_index=mobile_index)
    return result


def _save_backcast_chart(
    result: pd.DataFrame,
    *,
    mobile_index: pd.Series,
) -> None:
    parent_indices, _ = _load_parent_components("include_ex_games")
    feature_specs = (
        ("D7EN", "Audio-visual equipment", "-"),
        ("D7EO", "Photo and optical goods", "--"),
        ("D7EP", "Information-processing equipment", "-."),
        ("D7ES", "Recording media", ":"),
    )

    fig, ax = plt.subplots(figsize=(12.5, 6.2))
    for column, label, linestyle in feature_specs:
        feature = parent_indices[column].pct_change(12, fill_method=None) * 100
        ax.plot(
            feature.index,
            feature,
            color="#6f7f8d",
            linewidth=1.0,
            linestyle=linestyle,
            alpha=0.28,
            label=label,
            zorder=1,
        )
    mobile_rate = mobile_index.pct_change(12, fill_method=None) * 100
    ax.plot(
        mobile_rate.index,
        mobile_rate,
        color="#8a6f82",
        linewidth=1.0,
        linestyle="--",
        alpha=0.28,
        label="Handset items",
        zorder=1,
    )
    ax.plot(
        result.index,
        result["historical_targeted_hardware_12m_pct"],
        color="#205493",
        linewidth=2.0,
        label="Targeted hardware",
        zorder=3,
    )
    ax.plot(
        result.index,
        result["historical_ex_games_12m_pct"],
        color="#d17a22",
        linewidth=2.8,
        label="UK tech-goods aggregate",
        zorder=4,
    )
    splice = pd.Timestamp("2015-01-01")
    ax.axvspan(result.index.min(), splice, color="#dbe7f2", alpha=0.45)
    ax.axvline(splice, color="#555555", linewidth=0.9, linestyle="--")
    ax.axhline(0, color="black", linewidth=0.7)
    ax.set_xlim(result.index.min(), result.index.max())
    ax.text(
        pd.Timestamp("2005-01-01"),
        ax.get_ylim()[1] * 0.88,
        "Classification-bridged history",
        ha="center",
        color="#425b72",
        fontsize=9,
    )
    ax.set_title("UK tech-goods aggregate and the ONS inputs used to reconstruct it")
    ax.set_ylabel("Twelve-month inflation, %")
    ax.legend(frameon=False, ncol=3, loc="lower left", fontsize=8.5)
    fig.text(
        0.5,
        0.02,
        "Transparent lines show the component inputs. Before 2015, ONS parent classes are "
        "chained, with handset items added from 2005; validated COICOP5 aggregates are used "
        "thereafter.",
        ha="center",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.15, top=0.90)
    fig.savefig(CHART_DIR / "uk_tech_backcast.png", dpi=180)
    plt.close(fig)
